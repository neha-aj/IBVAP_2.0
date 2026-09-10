"""One `DetectionConsumer` per camera, run as an asyncio task. Reads
`cam:{id}:detections` (published by Detection Service, M4) via a Redis
Streams consumer group (SAS §5.3, §11 at-least-once processing), feeds each
frame's detections through this camera's `ByteTrackRunner`, and publishes
the result. Mirrors Detection Service's `frame_consumer.FrameConsumer`
structure/lifecycle (`is_running` + restartability) exactly.
"""

from __future__ import annotations

import asyncio
import json

import redis.asyncio as redis
from prometheus_client import Counter

from ibvap_common.logging import correlation_id_context, get_logger
from ibvap_common.redis_streams import ensure_consumer_group, xack, xread_group

from app.schemas.detection import Detection
from app.streaming.track_publisher import TrackPublisher
from app.tracking.track_manager import TrackManager

logger = get_logger(__name__)

_DETECTIONS_PROCESSED = Counter(
    "tracking_detections_processed_total", "Detection batches run through the tracker", ["camera_id"]
)


class DetectionConsumer:
    def __init__(
        self,
        *,
        camera_id: str,
        redis_client: redis.Redis,
        track_manager: TrackManager,
        publisher: TrackPublisher,
        group_name: str,
        read_count: int,
        block_ms: int,
    ) -> None:
        self.camera_id = camera_id
        self._redis = redis_client
        self._track_manager = track_manager
        self._publisher = publisher
        self._group_name = group_name
        self._read_count = read_count
        self._block_ms = block_ms
        self._stream_key = f"cam:{camera_id}:detections"
        self._task: asyncio.Task | None = None
        self._stop_requested = False

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        self._stop_requested = False
        self._task = asyncio.create_task(self._run(), name=f"detection-consumer-{self.camera_id}")

    async def stop(self) -> None:
        self._stop_requested = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._track_manager.remove_camera(self.camera_id)

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
                logger.warning("detection_read_failed", camera_id=self.camera_id, error=str(exc))
                await asyncio.sleep(1.0)
                continue

            for message_id, fields in messages:
                await self._process_message(message_id, fields)

    async def _process_message(self, message_id: bytes, fields: dict[bytes, bytes]) -> None:
        correlation_id = (fields.get(b"correlationId") or b"").decode()
        with correlation_id_context(correlation_id):
            try:
                raw = fields.get(b"detections")
                detections = [Detection(**item) for item in json.loads(raw)] if raw else []
                loop_generation = int(fields.get(b"loopGeneration", b"0") or b"0")

                tracked, events = self._track_manager.update(
                    self.camera_id, detections, loop_generation=loop_generation
                )
                await self._publisher.publish(self.camera_id, tracked_detections=tracked, events=events)
                _DETECTIONS_PROCESSED.labels(camera_id=self.camera_id).inc()
            except Exception as exc:
                logger.warning("tracking_update_failed", camera_id=self.camera_id, error=str(exc))
            finally:
                # Ack even on failure -- one malformed message must never
                # stall the stream forever (SAS §11: degrade, don't crash).
                await xack(self._redis, self._stream_key, self._group_name, message_id)
