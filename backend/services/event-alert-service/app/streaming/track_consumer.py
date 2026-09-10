"""One `TrackConsumer` per camera, run as an asyncio task. Reads
`cam:{id}:tracks` (published by Tracking Service, M5) via a Redis Streams
consumer group (SAS §5.4 step 1, §11 at-least-once processing), runs each
event through the rule engine, and persists+publishes whatever fires.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json

import redis.asyncio as redis
from prometheus_client import Counter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ibvap_common.logging import correlation_id_context, get_logger
from ibvap_common.redis_streams import ensure_consumer_group, xack, xread_group

from app.repositories.track_repo import TrackRepository
from app.rules.engine import RuleEngine
from app.schemas.internal import TrackEvent
from app.streaming.pubsub_publisher import PubSubPublisher

logger = get_logger(__name__)

_TRACK_EVENTS_PROCESSED = Counter(
    "event_alert_track_events_processed_total", "Track lifecycle events run through the rule engine", ["camera_id"]
)
_RULES_FIRED = Counter(
    "event_alert_rules_fired_total", "Rule firings that produced an event/alert draft", ["event_type"]
)


class TrackConsumer:
    def __init__(
        self,
        *,
        camera_id: str,
        redis_client: redis.Redis,
        session_factory: async_sessionmaker[AsyncSession],
        rule_engine: RuleEngine,
        publisher: PubSubPublisher,
        group_name: str,
        read_count: int,
        block_ms: int,
    ) -> None:
        self.camera_id = camera_id
        self._redis = redis_client
        self._session_factory = session_factory
        self._rule_engine = rule_engine
        self._publisher = publisher
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
        self._task = asyncio.create_task(self._run(), name=f"track-consumer-{self.camera_id}")

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
                logger.warning("track_read_failed", camera_id=self.camera_id, error=str(exc))
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
                    now = dt.datetime.now(dt.UTC)
                    async with self._session_factory() as session:
                        drafts = await self._rule_engine.handle_track_event(
                            track_event, TrackRepository(session), now
                        )
                        _TRACK_EVENTS_PROCESSED.labels(camera_id=self.camera_id).inc()
                        for draft in drafts:
                            await self._publisher.persist_and_publish(session, draft)
                            _RULES_FIRED.labels(event_type=draft.event_type).inc()
        except Exception as exc:
            logger.warning("rule_evaluation_failed", camera_id=self.camera_id, error=str(exc))
        finally:
            # Ack even on failure -- one malformed message must never stall
            # the stream forever (SAS §11: degrade gracefully, don't crash).
            await xack(self._redis, self._stream_key, self._group_name, message_id)
