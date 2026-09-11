"""Orchestrates posture classification for one sampled frame: runs the pose
model/classifier, publishes the resulting readings, and returns nothing
persisted anywhere -- there is deliberately no repository, no DB model, no
persistence layer in this service at all (see `app/core/config.py`'s own
docstring note). `detect` is an injected callable (not hardcoded to
`PoseLandmarkerModel.detect`) so this orchestration logic is unit-testable
without a real MediaPipe model/image, the same injectable-inference pattern
fire-smoke-service's `FireSmokeService` uses for `fire_score`/`smoke_score`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import numpy as np

from ibvap_common.logging import get_logger

from app.schemas.pose import PoseReading
from app.streaming.pose_publisher import PosePublisher

logger = get_logger(__name__)

DetectFn = Callable[[np.ndarray], list[PoseReading]]


class PoseService:
    def __init__(
        self,
        *,
        publisher: PosePublisher,
        detect: DetectFn,
    ) -> None:
        self._publisher = publisher
        self._detect = detect

    async def process_frame(self, camera_id: str, frame: np.ndarray) -> list[PoseReading]:
        """Returns the list of `PoseReading`s found in this frame (possibly
        empty) after publishing them -- the return value is only used by
        the frame consumer for metrics, never stored anywhere."""
        # Real MediaPipe model inference is CPU-bound and blocking (unlike
        # fire-smoke-service's cheap cv2 color-mask heuristics) -- offloaded
        # to a worker thread the same way `frame_consumer.py` already
        # offloads JPEG decode, so one camera's pose inference never stalls
        # the shared asyncio event loop other cameras' consumers also run
        # on.
        readings = await asyncio.to_thread(self._detect, frame)
        await self._publisher.publish(camera_id, readings)
        if readings:
            logger.debug(
                "pose_readings_published", camera_id=camera_id, count=len(readings),
                postures=[r.posture for r in readings],
            )
        return readings
