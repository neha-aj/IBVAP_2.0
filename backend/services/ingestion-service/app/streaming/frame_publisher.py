import time

import cv2
import numpy as np
import redis.asyncio as redis
from prometheus_client import Counter

from ibvap_common.logging import CORRELATION_ID_FIELD, new_correlation_id
from ibvap_common.redis_streams import xadd_capped

_FRAMES_PUBLISHED = Counter(
    "ingestion_frames_published_total", "Frames published to a camera's Redis Stream", ["camera_id"]
)


class FramePublisher:
    """Publishes decimated, JPEG-encoded frames to `cam:{id}:frames`
    (SAS §5.1/§5.2 -- this is the exact stream the Detection Service (M4)
    will consume from)."""

    def __init__(self, redis_client: redis.Redis, *, jpeg_quality: int, maxlen: int) -> None:
        self._redis = redis_client
        self._jpeg_quality = jpeg_quality
        self._maxlen = maxlen

    @staticmethod
    def _stream_key(camera_id: str, modality: str | None) -> str:
        return f"cam:{camera_id}:frames" if modality is None else f"cam:{camera_id}:frames:{modality}"

    async def discard_backlog(self, camera_id: str, *, modality: str | None = None) -> None:
        """Drops every frame still queued on this camera's stream. Called
        when an operator pauses the camera: consumers only ever read new
        entries (`>`), so this just deletes work they haven't started -- the
        same thing the `maxlen` cap already does on every publish. Without
        it, an analysis service that's behind real time would keep working
        through up to `maxlen` queued frames after the pause, i.e. keep
        "analysing" a camera the operator believes is stopped."""
        await self._redis.xtrim(self._stream_key(camera_id, modality), maxlen=0)

    async def publish(
        self, camera_id: str, frame: np.ndarray, *, loop_generation: int = 0, modality: str | None = None
    ) -> None:
        ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self._jpeg_quality])
        if not ok:
            return
        # M11: `modality` is None for every existing (single-stream) camera
        # type -- stream key is unchanged. A 'dual' camera's second
        # (thermal) worker passes modality="thermal" so its frames land on
        # their own stream instead of overwriting the RGB one; `cameraId`
        # below stays the real camera id either way, so detection-service's
        # fusion step can still associate both streams' detections with the
        # one logical camera.
        stream_key = self._stream_key(camera_id, modality)
        await xadd_capped(
            self._redis,
            stream_key,
            {
                "cameraId": camera_id,
                "timestamp": str(time.time()),
                "jpeg": encoded.tobytes(),
                # 0 for every live source and for a file source's first
                # play-through; increments each time a looping file source
                # restarts. Threaded through detection/tracking so the
                # Event/Alert Service can recognize "this is a replay,
                # already counted" rather than treating it as brand new
                # activity every loop (see ADR note in `capture/base.py`).
                "loopGeneration": str(loop_generation),
                # This frame originates the pipeline run for itself -- there's
                # no inbound HTTP request to inherit an id from -- so every
                # downstream stage (SAS §10) can trace one frame's journey
                # through detection/tracking/event-alert by this id alone.
                CORRELATION_ID_FIELD: new_correlation_id(),
            },
            maxlen=self._maxlen,
        )
        _FRAMES_PUBLISHED.labels(camera_id=camera_id).inc()
