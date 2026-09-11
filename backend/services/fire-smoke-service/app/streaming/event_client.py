"""Reports a fire/smoke/blood detection to Event/Alert Service's shared
internal event contract (Phase 2 doc08 §4) -- same pattern as ANPR's own
EventClient (M15). doc09 §2.6: severity is always `critical` and
`requiresReview` is always true (a fire/smoke/blood detection always needs
a human to look, unlike a routine ANPR plate read) -- which also means
"Blood Detected" automatically gets the same snapshot + full video-clip
proof as "Fire Detected"/"Smoke Detected" through event-alert-service's
existing generic critical-severity recording pipeline, with no separate
wiring needed here."""

from __future__ import annotations

import httpx

from ibvap_common.logging import correlated_headers, get_logger

from app.core.config import Settings

logger = get_logger(__name__)


class EventClient:
    def __init__(self, http_client: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http_client
        self._settings = settings

    async def report_detection(self, *, camera_id: str, event_type: str, coverage: float) -> None:
        description = (
            f"{event_type} -- covers ~{coverage * 100:.0f}% of frame "
            "(early-warning heuristic, confirm visually before acting)"
        )
        try:
            response = await self._http.post(
                f"{self._settings.event_alert_service_url}/internal/events",
                json={
                    "sourceService": "fire-smoke-service",
                    "eventType": event_type,
                    "cameraId": camera_id,
                    "objectType": None,
                    "severity": "critical",
                    "requiresReview": True,
                    "description": description,
                },
                headers={"X-Internal-Token": self._settings.internal_service_token, **correlated_headers()},
                timeout=5.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            # Best-effort, same reasoning as every other service's event
            # reporting (SAS §11) -- there's no local persistence here to
            # fall back on (this service has no DB), so a failed report
            # just means this one detection is lost, not retried.
            logger.warning("fire_smoke_event_report_failed", camera_id=camera_id, error=str(exc))
