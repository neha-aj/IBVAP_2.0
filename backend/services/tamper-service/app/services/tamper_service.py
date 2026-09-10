"""Orchestrates Camera Tamper Detection (doc09 §2.5) for one camera: each
sampled frame is compared against the camera's rolling baseline,
classified, and debounced before ever reporting an alert. `classify_fn` is
injected (not hardcoded to `app.inference.tamper_detector.classify_deviation`)
so this orchestration logic is unit-testable without real image
processing -- same injectable-inference pattern this session's other
Category B services use (ANPR, Re-ID, Fire/Smoke).
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from ibvap_common.logging import get_logger

from app.core.config import Settings
from app.inference.tamper_detector import TamperBaseline, classify_deviation
from app.streaming.event_client import EventClient

logger = get_logger(__name__)

ClassifyFn = Callable[..., str | None]


class TamperService:
    def __init__(
        self,
        *,
        camera_id: str,
        settings: Settings,
        event_client: EventClient,
        baseline: TamperBaseline | None = None,
        classify_fn: ClassifyFn = classify_deviation,
    ) -> None:
        self._camera_id = camera_id
        self._settings = settings
        self._event_client = event_client
        self._baseline = baseline or TamperBaseline(alpha=settings.baseline_ema_alpha)
        self._classify_fn = classify_fn
        self._deviation_streak = 0
        self._alerted = False

    async def process_frame(self, frame: np.ndarray) -> str | None:
        """Returns the tamper category reported ("covered"/"defocused"/
        "redirected"), or None if nothing fired this frame (no deviation,
        deviation still within the debounce window, or already alerted
        for the current ongoing tamper episode)."""
        reading = self._baseline.compare(frame)
        category = self._classify_fn(
            reading,
            covered_correlation_threshold=self._settings.covered_correlation_threshold,
            redirected_correlation_threshold=self._settings.redirected_correlation_threshold,
            defocus_edge_ratio_threshold=self._settings.defocus_edge_ratio_threshold,
        )

        if category is None:
            self._deviation_streak = 0
            self._alerted = False
            # Only adapt the baseline on frames judged normal -- see
            # TamperBaseline's own docstring for why a tampered frame must
            # never be absorbed as "the new normal."
            self._baseline.update(frame)
            return None

        self._deviation_streak += 1
        if self._deviation_streak < self._settings.debounce_frames or self._alerted:
            return None  # doc09 §2.5: debounce -- and never repeat-alert mid-episode

        self._alerted = True
        await self._event_client.report_tamper(camera_id=self._camera_id, category=category)
        logger.info("camera_tamper_detected", camera_id=self._camera_id, category=category)
        return category
