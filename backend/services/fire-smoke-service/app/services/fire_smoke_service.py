"""Orchestrates Fire & Smoke Detection (doc09 §2.6), plus a Blood
Detection heuristic added on the same terms: runs all three heuristics on
a sampled frame and reports a detection through the shared internal event
contract. `fire_score`/`smoke_score`/`blood_score` are injected callables
(not hardcoded to `app.inference.heuristics`) so this orchestration logic
is unit-testable without real image processing -- same pattern as every
other Category B service's injectable-inference design this session
(ANPR's `detect_plate`/`read_plate`, Re-ID's `embed`).
"""

from __future__ import annotations

import time
from collections.abc import Callable

import numpy as np

from ibvap_common.logging import get_logger

from app.core.config import Settings
from app.inference import heuristics
from app.streaming.event_client import EventClient

logger = get_logger(__name__)

ScoreFn = Callable[[np.ndarray], float]


class FireSmokeService:
    def __init__(
        self,
        *,
        settings: Settings,
        event_client: EventClient,
        fire_score: ScoreFn = heuristics.fire_score,
        smoke_score: ScoreFn = heuristics.smoke_score,
        blood_score: ScoreFn = heuristics.blood_score,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._event_client = event_client
        self._fire_score = fire_score
        self._smoke_score = smoke_score
        self._blood_score = blood_score
        self._now = now
        # (camera_id, event_type) -> monotonic time of last alert. Process-
        # local only, same as event-alert-service's own rule-engine
        # in-memory state -- one replica per camera-shard makes this safe
        # (SAS §11).
        self._last_alert_at: dict[tuple[str, str], float] = {}

    async def process_frame(self, camera_id: str, frame: np.ndarray) -> str | None:
        """Returns the event_type that fired ("Fire Detected"/"Smoke
        Detected"/"Blood Detected"), or None if nothing crossed threshold
        (or a real hit was suppressed by the per-camera cooldown)."""
        fire = self._fire_score(frame)
        if fire >= self._settings.fire_min_area_fraction and await self._maybe_alert(
            camera_id, "Fire Detected", fire
        ):
            return "Fire Detected"

        smoke = self._smoke_score(frame)
        if smoke >= self._settings.smoke_min_area_fraction and await self._maybe_alert(
            camera_id, "Smoke Detected", smoke
        ):
            return "Smoke Detected"

        blood = self._blood_score(frame)
        if blood >= self._settings.blood_min_area_fraction and await self._maybe_alert(
            camera_id, "Blood Detected", blood
        ):
            return "Blood Detected"

        return None

    async def _maybe_alert(self, camera_id: str, event_type: str, coverage: float) -> bool:
        key = (camera_id, event_type)
        now = self._now()
        last = self._last_alert_at.get(key)
        if last is not None and (now - last) < self._settings.alert_cooldown_seconds:
            return False  # doc09 §2.6: only suppresses *repeat* alerts, never the first one
        self._last_alert_at[key] = now
        await self._event_client.report_detection(camera_id=camera_id, event_type=event_type, coverage=coverage)
        logger.info(
            "fire_smoke_detected", camera_id=camera_id, event_type=event_type, coverage=round(coverage, 4)
        )
        return True
