"""Subscribes once to every bridged Redis Pub/Sub channel (SAS §5.4 step 5,
§8) and routes each message to the right topic's subscribers -- global
channels (`event.new`, `alert.new`, `alert.updated`, `system.health`) go to
the `events`/`alerts`/`system` topics; per-camera channels
(`camera.status_changed`, `detection.new`) go to that camera's `camera:{id}`
topic only, since detections in particular are far too high-frequency to
blast to clients who aren't looking at that camera."""

from __future__ import annotations

import asyncio
import json

import redis.asyncio as redis

from ibvap_common.logging import get_logger
from ibvap_common.redis_pubsub import subscribe

from app.core.config import Settings
from app.ws.connection_manager import ConnectionManager
from app.ws.topics import camera_topic

logger = get_logger(__name__)

_GLOBAL_TOPIC_BY_CHANNEL = {
    "event.new": "events",
    "alert.new": "alerts",
    "alert.updated": "alerts",
    "system.health": "system",
}
_PER_CAMERA_CHANNELS = {"camera.status_changed", "detection.new"}


class PubSubBridge:
    def __init__(self, redis_client: redis.Redis, connection_manager: ConnectionManager, settings: Settings) -> None:
        self._redis = redis_client
        self._manager = connection_manager
        self._settings = settings
        self._task: asyncio.Task | None = None
        self._stop_requested = False

    def start(self) -> None:
        self._stop_requested = False
        self._task = asyncio.create_task(self._run(), name="pubsub-bridge")

    async def stop(self) -> None:
        self._stop_requested = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        pubsub = await subscribe(self._redis, *self._settings.bridged_channels)
        try:
            while not self._stop_requested:
                try:
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=2.0)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    logger.warning("pubsub_read_failed", error=str(exc))
                    await asyncio.sleep(1.0)
                    continue

                if message is None:
                    continue
                await self._dispatch(message["channel"], message["data"])
        finally:
            await pubsub.unsubscribe(*self._settings.bridged_channels)
            await pubsub.aclose()

    async def _dispatch(self, channel: bytes, raw: bytes) -> None:
        try:
            channel_name = channel.decode() if isinstance(channel, bytes) else channel
            payload = json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("pubsub_message_malformed", error=str(exc))
            return

        envelope = {"event": channel_name, "data": payload}

        global_topic = _GLOBAL_TOPIC_BY_CHANNEL.get(channel_name)
        if global_topic is not None:
            await self._manager.broadcast(global_topic, envelope)
            return

        if channel_name in _PER_CAMERA_CHANNELS:
            camera_id = payload.get("cameraId")
            if camera_id:
                await self._manager.broadcast(camera_topic(camera_id), envelope)
