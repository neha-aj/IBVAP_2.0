"""Subscribes once to the global `camera.status_changed` Pub/Sub channel
(camera-service publishes this on every real status transition -- SAS §5.4
step 1) and drives the offline-alert rule. Unlike `TrackConsumer`, this is
not per-camera: it's one subscription covering every camera.
"""

from __future__ import annotations

import asyncio
import json

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ibvap_common.logging import get_logger
from ibvap_common.redis_pubsub import subscribe

from app.rules.engine import RuleEngine
from app.streaming.pubsub_publisher import PubSubPublisher

logger = get_logger(__name__)


class StatusConsumer:
    def __init__(
        self,
        *,
        redis_client: redis.Redis,
        session_factory: async_sessionmaker[AsyncSession],
        rule_engine: RuleEngine,
        publisher: PubSubPublisher,
    ) -> None:
        self._redis = redis_client
        self._session_factory = session_factory
        self._rule_engine = rule_engine
        self._publisher = publisher
        self._task: asyncio.Task | None = None
        self._stop_requested = False

    def start(self) -> None:
        self._stop_requested = False
        self._task = asyncio.create_task(self._run(), name="camera-status-consumer")

    async def stop(self) -> None:
        self._stop_requested = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        pubsub = await subscribe(self._redis, "camera.status_changed")
        try:
            while not self._stop_requested:
                try:
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=2.0)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning("status_subscribe_failed", error=str(exc))
                    await asyncio.sleep(1.0)
                    continue

                if message is None:
                    continue
                await self._process_message(message["data"])
        finally:
            await pubsub.unsubscribe("camera.status_changed")
            await pubsub.aclose()

    async def _process_message(self, raw: bytes) -> None:
        try:
            payload = json.loads(raw)
            camera_id, status = payload["cameraId"], payload["status"]
            drafts = await self._rule_engine.handle_camera_status_changed(camera_id, status)
            async with self._session_factory() as session:
                for draft in drafts:
                    await self._publisher.persist_and_publish(session, draft)
        except Exception as exc:
            logger.warning("camera_status_rule_failed", error=str(exc))
