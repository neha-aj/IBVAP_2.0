"""Orchestrates PPE Detection (doc09 §2.8) for one track at a time: on
each person track update inside a `requires_ppe` zone, fetch the current
frame, crop the person region, and run the vest heuristic on it.
`classify_fn` is injected (not hardcoded to
`app.inference.ppe_heuristics.classify_ppe`) so this orchestration logic
is unit-testable without real image processing -- same injectable-
inference pattern this project's other Category B services use (ANPR,
Re-ID, Fire/Smoke, Tamper).

Debounce/escalation state is kept per (camera_id, track_id): a few
consecutive missing-PPE reads are required before the first (medium-
severity) violation fires (a person passing briefly through frame
shouldn't alert on one bad crop), and a second, high-severity violation
fires if the same track stays out of compliance for much longer (doc09
§2.8: "escalate to high for repeated violations by the same track within
a session"). Coming back into compliance (or leaving the requires_ppe
zone, or the track ending) resets the streak, so a fresh violation episode
alerts again from scratch rather than staying silenced forever.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import cv2
import numpy as np

from ibvap_common.logging import get_logger

from app.core.config import Settings
from app.inference import preprocessing
from app.inference.ppe_heuristics import classify_ppe
from app.rules.zone_geometry import any_zone_requires_ppe
from app.schemas.internal import TrackEvent
from app.streaming.camera_client import CameraClient
from app.streaming.event_client import EventClient

logger = get_logger(__name__)

ClassifyFn = Callable[..., list[str]]


@dataclass
class _TrackState:
    consecutive_violations: int = 0
    alerted_medium: bool = False
    alerted_high: bool = False

    def reset(self) -> None:
        self.consecutive_violations = 0
        self.alerted_medium = False
        self.alerted_high = False


class PPEService:
    def __init__(
        self,
        *,
        settings: Settings,
        camera_client: CameraClient,
        event_client: EventClient,
        classify_fn: ClassifyFn = classify_ppe,
    ) -> None:
        self._settings = settings
        self._camera_client = camera_client
        self._event_client = event_client
        self._classify_fn = classify_fn
        self._track_state: dict[tuple[str, str], _TrackState] = {}

    async def process_track_event(self, event: TrackEvent) -> list[str] | None:
        """Returns the missing-PPE items reported this call (a new
        violation event was just sent), or None if nothing fired --
        wrong object type, not in a requires_ppe zone, frame/crop
        unavailable, compliant, or still within the debounce window."""
        key = (event.camera_id, event.track_id)

        if event.event == "track.lost":
            self._track_state.pop(key, None)
            return None
        if event.object_type != "person" or event.bbox is None:
            return None
        if event.event not in ("track.started", "track.updated"):
            return None

        zones = await self._camera_client.get_zones(event.camera_id)
        if not any_zone_requires_ppe(event.bbox, zones):
            self._track_state.pop(key, None)
            return None

        frame_bytes = await self._camera_client.get_current_frame(event.camera_id)
        if frame_bytes is None:
            return None
        frame = cv2.imdecode(np.frombuffer(frame_bytes, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return None

        crop = preprocessing.crop_bbox_percent(
            frame, x=event.bbox.x, y=event.bbox.y, width=event.bbox.width, height=event.bbox.height,
        )
        if crop.size == 0 or min(crop.shape[:2]) < self._settings.person_crop_min_size_px:
            return None

        missing = self._classify_fn(crop, vest_min_coverage_fraction=self._settings.vest_min_coverage_fraction)
        state = self._track_state.setdefault(key, _TrackState())

        if not missing:
            state.reset()
            return None

        state.consecutive_violations += 1

        if not state.alerted_medium:
            if state.consecutive_violations < self._settings.violation_debounce_updates:
                return None
            state.alerted_medium = True
            await self._event_client.report_violation(
                camera_id=event.camera_id, missing_items=missing, severity="medium"
            )
            logger.info("ppe_violation_detected", camera_id=event.camera_id, track_id=event.track_id, severity="medium")
            return missing

        if not state.alerted_high and state.consecutive_violations >= self._settings.escalation_violation_updates:
            state.alerted_high = True
            await self._event_client.report_violation(
                camera_id=event.camera_id, missing_items=missing, severity="high"
            )
            logger.info("ppe_violation_detected", camera_id=event.camera_id, track_id=event.track_id, severity="high")
            return missing

        return None
