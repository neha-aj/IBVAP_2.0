"""One `TrackConsumer` per camera, run as an asyncio task. Reads
`cam:{id}:tracks` via its own Redis Streams consumer group -- independent
of event-alert-service's own group on the same stream (SAS §11: multiple
consumer groups per stream is the supported pattern for this) -- and runs
each event through every `ReidService` it's given (Phase 2 M17: one for
`person`, one for `vehicle`; each filters to its own `object_type`
internally and no-ops for the other kind)."""

from __future__ import annotations

import asyncio
import json

import redis.asyncio as redis
from prometheus_client import Counter

from ibvap_common.logging import correlation_id_context, get_logger
from ibvap_common.redis_streams import ensure_consumer_group, xack, xread_group

from app.schemas.internal import TrackEvent
from app.services.reid_service import ReidService

logger = get_logger(__name__)

_TRACK_EVENTS_PROCESSED = Counter(
    "reid_track_events_processed_total", "Track lifecycle events run through Re-ID", ["camera_id"]
)
_EMBEDDINGS_EXTRACTED = Counter(
    "reid_embeddings_extracted_total",
    "Embeddings successfully extracted and persisted",
    ["camera_id", "object_type"],
)


class TrackConsumer:
    def __init__(
        self,
        *,
        camera_id: str,
        redis_client: redis.Redis,
        reid_services: dict[str, ReidService],
        group_name: str,
        read_count: int,
        block_ms: int,
    ) -> None:
        self.camera_id = camera_id
        self._redis = redis_client
        self._reid_services = reid_services
        self._group_name = group_name
        self._read_count = read_count
        self._block_ms = block_ms
        self._stream_key = f"cam:{camera_id}:tracks"
        self._task: asyncio.Task | None = None
        self._stop_requested = False

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        self._stop_requested = False
        self._task = asyncio.create_task(self._run(), name=f"reid-consumer-{self.camera_id}")

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
                logger.warning("reid_stream_read_failed", camera_id=self.camera_id, error=str(exc))
                await asyncio.sleep(1.0)
                continue

            for message_id, fields in messages:
                await self._process_message(message_id, fields)

    async def _process_message(self, message_id: bytes, fields: dict[bytes, bytes]) -> None:
        try:
            raw = fields.get(b"event")
            if raw:
                track_event = TrackEvent(**json.loads(raw))
                with correlation_id_context(track_event.correlation_id):
                    _TRACK_EVENTS_PROCESSED.labels(camera_id=self.camera_id).inc()
                    for object_type, reid_service in self._reid_services.items():
                        embedding = await reid_service.process_track_event(track_event)
                        if embedding is not None:
                            _EMBEDDINGS_EXTRACTED.labels(camera_id=self.camera_id, object_type=object_type).inc()
        except Exception as exc:
            logger.warning("reid_processing_failed", camera_id=self.camera_id, error=str(exc))
        finally:
            await xack(self._redis, self._stream_key, self._group_name, message_id)
