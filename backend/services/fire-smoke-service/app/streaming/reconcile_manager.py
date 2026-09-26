"""Owns the set of running per-camera `FrameConsumer`s, reconciling against
Camera Management Service's camera list on a polling interval -- the same
discovery/restart pattern every other pipeline stage uses. No DB session
factory here (unlike anpr-service/reid-service's identical-looking
manager) -- this service has no database."""

from __future__ import annotations

import asyncio

import httpx
import redis.asyncio as redis

from ibvap_common.logging import get_logger
from ibvap_common.redis_streams import build_redis_client

from app.core.config import Settings
from app.inference import yolo_scorer
from app.services.fire_smoke_service import FireSmokeService
from app.streaming.camera_client import CameraClient
from app.streaming.event_client import EventClient
from app.streaming.frame_consumer import FrameConsumer

logger = get_logger(__name__)


class ReconcileManager:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._consumers: dict[str, FrameConsumer] = {}
        self._redis: redis.Redis = build_redis_client(settings)
        self._http = httpx.AsyncClient()
        self._camera_client = CameraClient(self._http, settings)
        self._event_client = EventClient(self._http, settings)
        self._poll_task: asyncio.Task | None = None
        self._stopped = False
        # One shared model instance for every camera's FireSmokeService
        # (see yolo_scorer.py) -- None if disabled or the weights file
        # couldn't be loaded, in which case every camera below falls back
        # to the original heuristics.
        self._trained_scorer = (
            yolo_scorer.load_if_enabled(
                model_path=settings.fire_smoke_model_path,
                confidence_threshold=settings.fire_smoke_model_confidence_threshold,
            )
            if settings.use_trained_fire_smoke_model
            else None
        )

    @property
    def active_consumer_count(self) -> int:
        return len(self._consumers)

    async def start(self) -> None:
        self._stopped = False
        await self._reconcile()
        self._poll_task = asyncio.create_task(self._poll_loop(), name="fire-smoke-poll-loop")

    async def stop(self) -> None:
        self._stopped = True
        if self._poll_task is not None:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        await asyncio.gather(*(c.stop() for c in self._consumers.values()))
        self._consumers.clear()
        await self._http.aclose()
        await self._redis.aclose()

    async def _poll_loop(self) -> None:
        while not self._stopped:
            await asyncio.sleep(self._settings.camera_refresh_interval_seconds)
            try:
                await self._reconcile()
            except Exception as exc:
                logger.warning("fire_smoke_camera_list_poll_failed", error=str(exc))

    async def _reconcile(self) -> None:
        camera_ids = await self._camera_client.list_camera_ids()
        seen_ids = set(camera_ids)

        for camera_id in camera_ids:
            existing = self._consumers.get(camera_id)
            if existing is not None:
                if existing.is_running:
                    continue
                await existing.stop()
                del self._consumers[camera_id]
                logger.info("fire_smoke_consumer_restarting", camera_id=camera_id)

            # One FireSmokeService instance per camera -- each holds its own
            # per-event-type cooldown state, so a camera with a stuck fire
            # alert doesn't affect any other camera's cooldown clock. Only
            # fire/smoke swap to the trained model when available; blood
            # has no trained equivalent and always uses the heuristic.
            fire_smoke_service = (
                FireSmokeService(
                    settings=self._settings,
                    event_client=self._event_client,
                    fire_score=self._trained_scorer.fire_score,
                    smoke_score=self._trained_scorer.smoke_score,
                )
                if self._trained_scorer is not None
                else FireSmokeService(settings=self._settings, event_client=self._event_client)
            )
            consumer = FrameConsumer(
                camera_id=camera_id,
                redis_client=self._redis,
                fire_smoke_service=fire_smoke_service,
                group_name=self._settings.consumer_group_name,
                read_count=self._settings.frames_read_count,
                block_ms=self._settings.frames_block_ms,
                sample_interval_seconds=self._settings.sample_interval_seconds,
            )
            consumer.start()
            self._consumers[camera_id] = consumer
            logger.info("fire_smoke_consumer_started", camera_id=camera_id)

        removed_ids = set(self._consumers) - seen_ids
        for camera_id in removed_ids:
            await self._consumers.pop(camera_id).stop()
            logger.info("fire_smoke_consumer_stopped", camera_id=camera_id, reason="camera_removed")
