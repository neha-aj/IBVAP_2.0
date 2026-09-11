"""Owns the set of running per-camera `FrameConsumer`s, reconciling against
Camera Management Service's camera list on a polling interval -- the same
discovery/restart pattern fire-smoke-service's own `reconcile_manager.py`
uses. No DB session factory here either -- this service has no database.

Each camera gets its own `PoseLandmarkerModel` instance (not one shared
model across all cameras), mirroring fire-smoke-service's one-
`FireSmokeService`-per-camera pattern -- and for a real additional reason
here: MediaPipe's `PoseLandmarker` in `IMAGE` running mode is not
documented as safe for concurrent calls from multiple threads against a
single instance, and each camera's frames are decoded/classified on their
own worker thread (`app/services/pose_service.py`'s `asyncio.to_thread`).
One model instance per camera avoids that hazard entirely, at the cost of
each camera holding its own copy of the (CPU-only, no GPU memory
contention) model weights."""

from __future__ import annotations

import asyncio

import httpx
import redis.asyncio as redis

from ibvap_common.logging import get_logger
from ibvap_common.redis_streams import build_redis_client

from app.core.config import Settings
from app.inference.pose_landmarker import PoseLandmarkerModel
from app.services.pose_service import PoseService
from app.streaming.camera_client import CameraClient
from app.streaming.frame_consumer import FrameConsumer
from app.streaming.pose_publisher import PosePublisher

logger = get_logger(__name__)


class ReconcileManager:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._consumers: dict[str, FrameConsumer] = {}
        self._models: dict[str, PoseLandmarkerModel] = {}
        self._redis: redis.Redis = build_redis_client(settings)
        self._http = httpx.AsyncClient()
        self._camera_client = CameraClient(self._http, settings)
        self._publisher = PosePublisher(self._redis)
        self._poll_task: asyncio.Task | None = None
        self._stopped = False

    @property
    def active_consumer_count(self) -> int:
        return len(self._consumers)

    async def start(self) -> None:
        self._stopped = False
        await self._reconcile()
        self._poll_task = asyncio.create_task(self._poll_loop(), name="pose-poll-loop")

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
        for model in self._models.values():
            await asyncio.to_thread(model.close)
        self._models.clear()
        await self._http.aclose()
        await self._redis.aclose()

    async def _poll_loop(self) -> None:
        while not self._stopped:
            await asyncio.sleep(self._settings.camera_refresh_interval_seconds)
            try:
                await self._reconcile()
            except Exception as exc:
                logger.warning("pose_camera_list_poll_failed", error=str(exc))

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
                stale_model = self._models.pop(camera_id, None)
                if stale_model is not None:
                    await asyncio.to_thread(stale_model.close)
                logger.info("pose_consumer_restarting", camera_id=camera_id)

            model = await asyncio.to_thread(
                PoseLandmarkerModel,
                model_path=self._settings.pose_model_path,
                max_poses=self._settings.max_poses_per_frame,
                min_pose_confidence=self._settings.min_pose_confidence,
                torso_vertical_max_degrees=self._settings.torso_vertical_max_degrees,
                torso_horizontal_min_degrees=self._settings.torso_horizontal_min_degrees,
                knee_bend_max_degrees=self._settings.knee_bend_max_degrees,
            )
            self._models[camera_id] = model
            pose_service = PoseService(publisher=self._publisher, detect=model.detect)
            consumer = FrameConsumer(
                camera_id=camera_id,
                redis_client=self._redis,
                pose_service=pose_service,
                group_name=self._settings.consumer_group_name,
                read_count=self._settings.frames_read_count,
                block_ms=self._settings.frames_block_ms,
                sample_interval_seconds=self._settings.sample_interval_seconds,
            )
            consumer.start()
            self._consumers[camera_id] = consumer
            logger.info("pose_consumer_started", camera_id=camera_id)

        removed_ids = set(self._consumers) - seen_ids
        for camera_id in removed_ids:
            await self._consumers.pop(camera_id).stop()
            stale_model = self._models.pop(camera_id, None)
            if stale_model is not None:
                await asyncio.to_thread(stale_model.close)
            logger.info("pose_consumer_stopped", camera_id=camera_id, reason="camera_removed")
