"""One `FrameConsumer` per camera, run as an asyncio task. Reads
`cam:{id}:frames` via its own Redis Streams consumer group -- independent
of detection-service's own group on the same stream (SAS §11: multiple
consumer groups per stream is the supported pattern for this) -- throttles
to `settings.sample_interval_seconds` (doc09 §2.5: "1fps is sufficient"),
and runs each sampled frame through this camera's `TamperService`.
"""

from __future__ import annotations

import asyncio
import time

import cv2
import numpy as np
import redis.asyncio as redis
from prometheus_client import Counter

from ibvap_common.logging import correlation_id_context, get_logger
from ibvap_common.redis_streams import ensure_consumer_group, xack, xread_group

from app.services.tamper_service import TamperService

logger = get_logger(__name__)

_FRAMES_SAMPLED = Counter(
    "tamper_frames_sampled_total", "Frames actually run through the tamper baseline check", ["camera_id"]
)
_TAMPER_DETECTED = Counter(
    "tamper_detections_reported_total", "Camera tamper detections reported", ["camera_id", "category"]
)


class FrameConsumer:
    def __init__(
        self,
        *,
        camera_id: str,
        redis_client: redis.Redis,
        tamper_service: TamperService,
        group_name: str,
        read_count: int,
        block_ms: int,
        sample_interval_seconds: float,
    ) -> None:
        self.camera_id = camera_id
        self._redis = redis_client
        self._service = tamper_service
        self._group_name = group_name
        self._read_count = read_count
        self._block_ms = block_ms
        self._sample_interval_seconds = sample_interval_seconds
        self._stream_key = f"cam:{camera_id}:frames"
        self._task: asyncio.Task | None = None
        self._stop_requested = False
        self._last_sampled_at = 0.0

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        self._stop_requested = False
        self._task = asyncio.create_task(self._run(), name=f"tamper-consumer-{self.camera_id}")

    async def stop(self) -> None:
        self._stop_requested = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        await ensure_consumer_group(self._redis, self._stream_key, self._group_name)
        consumer_name = f"consumer-{self.camera_id}"

        while not self._stop_requested:
            try:
                messages = await xread_group(
                    self._redis,
                    group_name=self._group_name,
                    consumer_name=consumer_name,
                    stream_key=self._stream_key,
                    count=self._read_count,
                    block_ms=self._block_ms,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("tamper_stream_read_failed", camera_id=self.camera_id, error=str(exc))
                await asyncio.sleep(1.0)
                continue

            for message_id, fields in messages:
                await self._process_message(message_id, fields)

    async def _process_message(self, message_id: bytes, fields: dict[bytes, bytes]) -> None:
        try:
            now = time.monotonic()
            if now - self._last_sampled_at < self._sample_interval_seconds:
                return  # ack'd in `finally` -- deliberately skipped, not queued
            self._last_sampled_at = now

            correlation_id = (fields.get(b"correlationId") or b"").decode()
            with correlation_id_context(correlation_id):
                jpeg_bytes = fields.get(b"jpeg")
                if not jpeg_bytes:
                    return
                frame = await asyncio.to_thread(_decode_jpeg, jpeg_bytes)
                if frame is None:
                    return
                _FRAMES_SAMPLED.labels(camera_id=self.camera_id).inc()
                category = await self._service.process_frame(frame)
                if category is not None:
                    _TAMPER_DETECTED.labels(camera_id=self.camera_id, category=category).inc()
        except Exception as exc:
            logger.warning("tamper_processing_failed", camera_id=self.camera_id, error=str(exc))
        finally:
            await xack(self._redis, self._stream_key, self._group_name, message_id)


def _decode_jpeg(jpeg_bytes: bytes) -> np.ndarray | None:
    array = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    return cv2.imdecode(array, cv2.IMREAD_COLOR)
