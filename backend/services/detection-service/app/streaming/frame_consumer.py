"""One `FrameConsumer` per camera, run as an asyncio task. Reads
`cam:{id}:frames` via a Redis Streams consumer group (SAS §5.2, §11
at-least-once processing), decodes each JPEG frame, runs inference in a
worker thread (IG §3: CPU-bound work never blocks the event loop), and
publishes the normalized detections.
"""

from __future__ import annotations

import asyncio

import cv2
import numpy as np
import redis.asyncio as redis
from prometheus_client import Counter

from ibvap_common.logging import correlation_id_context, get_logger
from ibvap_common.redis_streams import ensure_consumer_group, xack, xread_group

from app.inference.base import InferenceEngine
from app.streaming.detection_publisher import DetectionPublisher, to_detections

logger = get_logger(__name__)

_FRAMES_PROCESSED = Counter(
    "detection_frames_processed_total", "Frames run through inference", ["camera_id"]
)


class FrameConsumer:
    def __init__(
        self,
        *,
        camera_id: str,
        redis_client: redis.Redis,
        engine: InferenceEngine,
        publisher: DetectionPublisher,
        group_name: str,
        read_count: int,
        block_ms: int,
        modality: str | None = None,
    ) -> None:
        self.camera_id = camera_id
        self._redis = redis_client
        self._engine = engine
        self._publisher = publisher
        self._group_name = group_name
        self._read_count = read_count
        self._block_ms = block_ms
        # M11: None for every existing (single-stream) camera type --
        # `_stream_key` is exactly what it was before. A 'dual' camera's
        # second consumer passes modality="thermal" to read the parallel
        # stream Stream Ingestion's second capture worker writes to
        # (`FramePublisher.publish`'s own `modality` param, same naming).
        # `self.camera_id` is deliberately left as the real camera id either
        # way -- only the stream key changes, so publishing/logging/consumer
        # naming below stay associated with the actual camera.
        self._stream_key = f"cam:{camera_id}:frames" if modality is None else f"cam:{camera_id}:frames:{modality}"
        self._task: asyncio.Task | None = None
        self._stop_requested = False

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        self._stop_requested = False
        self._task = asyncio.create_task(self._run(), name=f"frame-consumer-{self.camera_id}")

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
                logger.warning("frame_read_failed", camera_id=self.camera_id, error=str(exc))
                await asyncio.sleep(1.0)
                continue

            for message_id, fields in messages:
                await self._process_message(message_id, fields)

    async def _process_message(self, message_id: bytes, fields: dict[bytes, bytes]) -> None:
        correlation_id = (fields.get(b"correlationId") or b"").decode()
        with correlation_id_context(correlation_id):
            try:
                jpeg_bytes = fields.get(b"jpeg")
                if jpeg_bytes:
                    loop_generation = int(fields.get(b"loopGeneration", b"0") or b"0")
                    frame = await asyncio.to_thread(_decode_jpeg, jpeg_bytes)
                    if frame is not None:
                        height, width = frame.shape[:2]
                        raw_detections = await asyncio.to_thread(self._engine.infer, frame)
                        detections = to_detections(
                            camera_id=self.camera_id,
                            raw_detections=raw_detections,
                            frame_width=width,
                            frame_height=height,
                        )
                        await self._publisher.publish(self.camera_id, detections, loop_generation=loop_generation)
                        _FRAMES_PROCESSED.labels(camera_id=self.camera_id).inc()
            except Exception as exc:
                logger.warning(
                    "frame_inference_failed", camera_id=self.camera_id, error=str(exc)
                )
            finally:
                # Ack even on failure -- a single malformed/undecodable frame
                # should never block the stream forever (SAS §11: degrade
                # gracefully rather than crash or stall).
                await xack(self._redis, self._stream_key, self._group_name, message_id)


def _decode_jpeg(jpeg_bytes: bytes) -> np.ndarray | None:
    array = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    return cv2.imdecode(array, cv2.IMREAD_COLOR)
