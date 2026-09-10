"""M11 §7's local-only alerting fallback (`EDGE_LOCAL_RULES=true`): a
minimal subset of event-alert-service's real rule engine -- zone-intrusion
and count-threshold only (offline-alert is explicitly excluded by §7,
since it's meaningless locally) -- run against the local outbox so a site
can still raise a local alert during a full connectivity outage.

Deliberately scoped down from the design doc's own "synced to central
events/alerts once the link is restored, deduplicated by a client-
generated idempotency key" (disclosed, not silent): that sync target is
event-alert-service's `POST /internal/events` contract, which has no
idempotency-key field or dedup logic today -- adding one is a real change
to a *different* service's files, and this milestone's own PR4 checklist
(§10) lists detection-service files only (edge_outbox.py, sync_worker.py,
config.py). This module implements the actual rule *evaluation* and
persists fired alerts locally (`EdgeOutbox.record_local_alert`, already
keyed by `idempotency_key` so it's ready to sync once that endpoint
exists); wiring a deduplicated central copy is the one integration step
left for whoever extends event-alert-service to accept it.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from app.inference.edge_outbox import EdgeOutbox
from app.schemas.detection import Detection


def point_in_polygon(x: float, y: float, polygon: list[tuple[float, float]]) -> bool:
    """Standard ray-casting point-in-polygon test. `polygon` points and
    (x, y) are percent-of-frame coordinates -- the same units
    `Detection.bbox` already uses, and the same units zones are stored in
    (camera-service's own `Zone.polygon`)."""
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _bbox_center(det: Detection) -> tuple[float, float]:
    return (det.bbox.x + det.bbox.width / 2, det.bbox.y + det.bbox.height / 2)


class LocalRuleEngine:
    """One instance per edge-profile detection-service process (not one
    per camera -- rolling-window state below is keyed by camera_id
    internally, same pattern as event-alert-service's own per-camera rule
    state)."""

    def __init__(
        self,
        *,
        count_threshold: int,
        count_window_seconds: float,
        zones_by_camera: dict[str, list[dict]] | None = None,
    ) -> None:
        self._count_threshold = count_threshold
        self._count_window_seconds = count_window_seconds
        self._zones_by_camera = zones_by_camera or {}
        self._recent_detection_times: dict[str, deque[float]] = defaultdict(deque)

    def evaluate(self, *, camera_id: str, detections: list[Detection]) -> list[dict]:
        """Returns zero or more fired-alert dicts (idempotency_key,
        event_type, description, severity) for this batch of detections --
        a pure function of (camera_id, detections, wall-clock now) plus
        this engine's own rolling-window state, so it's directly
        unit-testable without a real outbox, clock, or event loop."""
        now = time.monotonic()
        alerts: list[dict] = []

        window = self._recent_detection_times[camera_id]
        for _ in detections:
            window.append(now)
        cutoff = now - self._count_window_seconds
        while window and window[0] < cutoff:
            window.popleft()
        if len(window) > self._count_threshold:
            # Coarse idempotency key (camera + current minute): re-firing
            # every single frame while still over threshold would just
            # flood local_alerts with near-duplicates -- one alert per
            # camera per minute the threshold stays exceeded is enough for
            # an edge site's own local notification purposes.
            alerts.append(
                {
                    "idempotency_key": f"{camera_id}:count-threshold:{int(now // 60)}",
                    "camera_id": camera_id,
                    "event_type": "Count Threshold Exceeded",
                    "description": (
                        f"{len(window)} detections in the last {self._count_window_seconds:.0f}s "
                        f"(local edge rule, threshold {self._count_threshold})"
                    ),
                    "severity": "medium",
                }
            )

        zones = self._zones_by_camera.get(camera_id, [])
        for det in detections:
            cx, cy = _bbox_center(det)
            for zone in zones:
                if zone.get("zone_type") != "restricted":
                    continue
                if point_in_polygon(cx, cy, zone["polygon"]):
                    alerts.append(
                        {
                            "idempotency_key": f"{camera_id}:zone:{zone.get('id')}:{det.id}",
                            "camera_id": camera_id,
                            "event_type": "Restricted Zone Entry",
                            "description": (
                                f"{det.type} entered zone '{zone.get('name', '?')}' (local edge rule)"
                            ),
                            "severity": "high",
                        }
                    )

        return alerts

    async def evaluate_and_record(self, *, camera_id: str, detections: list[Detection], outbox: EdgeOutbox) -> int:
        """Evaluates then persists any fired alerts via `EdgeOutbox`'s own
        idempotency-key dedup -- returns how many were newly recorded (as
        opposed to already-seen re-fires `record_local_alert` no-ops on)."""
        fired = self.evaluate(camera_id=camera_id, detections=detections)
        recorded = 0
        for alert in fired:
            was_new = await outbox.record_local_alert(
                idempotency_key=alert["idempotency_key"],
                camera_id=alert["camera_id"],
                event_type=alert["event_type"],
                description=alert["description"],
                severity=alert["severity"],
            )
            if was_new:
                recorded += 1
        return recorded
