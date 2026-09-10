"""Owns the set of running per-camera `TrackConsumer`s, reconciling against
Camera Management Service's camera list on a polling interval -- the same
discovery/restart pattern every other pipeline stage uses."""

from __future__ import annotations

import asyncio

import httpx
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ibvap_common.logging import get_logger
from ibvap_common.redis_streams import build_redis_client

from app.core.config import Settings
from app.inference.embedder import ImageEmbedder
from app.models.person_embedding import PersonEmbedding
from app.models.vehicle_embedding import VehicleEmbedding
from app.repositories.embedding_repo import EmbeddingRepository
from app.services.reid_service import ReidService
from app.streaming.camera_client import CameraClient
from app.streaming.media_client import MediaClient
from app.streaming.track_consumer import TrackConsumer

logger = get_logger(__name__)


class ReconcileManager:
    def __init__(self, settings: Settings, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._consumers: dict[str, TrackConsumer] = {}
        self._redis: redis.Redis = build_redis_client(settings)
        self._http = httpx.AsyncClient()
        self._camera_client = CameraClient(self._http, settings)
        self._media_client = MediaClient(self._http, settings)
        self._embedder = ImageEmbedder()
        self._poll_task: asyncio.Task | None = None
        self._stopped = False

    @property
    def active_consumer_count(self) -> int:
        return len(self._consumers)

    @property
    def camera_client(self) -> CameraClient:
        """Exposed for the search API routes -- resolving a match's camera
        name reuses this same client rather than each route building one."""
        return self._camera_client

    def build_person_reid_service(self, session: AsyncSession) -> ReidService:
        return ReidService(
            settings=self._settings,
            embedding_repo=EmbeddingRepository(session, PersonEmbedding),
            camera_client=self._camera_client,
            media_client=self._media_client,
            embed=self._embedder.embed,
            object_type="person",
            embedding_factory=PersonEmbedding,
            crop_min_size=self._settings.person_crop_min_size_px,
        )

    def build_vehicle_reid_service(self, session: AsyncSession) -> ReidService:
        """Phase 2 M17 -- same embedder instance as person Re-ID (see
        embedder.py's own docstring for why), a different table."""
        return ReidService(
            settings=self._settings,
            embedding_repo=EmbeddingRepository(session, VehicleEmbedding),
            camera_client=self._camera_client,
            media_client=self._media_client,
            embed=self._embedder.embed,
            object_type="vehicle",
            embedding_factory=VehicleEmbedding,
            crop_min_size=self._settings.vehicle_crop_min_size_px,
        )

    async def start(self) -> None:
        self._stopped = False
        await self._reconcile()
        self._poll_task = asyncio.create_task(self._poll_loop(), name="reid-poll-loop")

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
                logger.warning("reid_camera_list_poll_failed", error=str(exc))

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
                logger.info("reid_consumer_restarting", camera_id=camera_id)

            # One consumer per camera runs the message through both the
            # person and vehicle Re-ID services (Phase 2 M17) -- each
            # service already filters on `object_type` internally and no-ops
            # cheaply for the other kind, so this is one Redis read per
            # message rather than a second consumer group duplicating reads
            # of the same stream.
            consumer = TrackConsumer(
                camera_id=camera_id,
                redis_client=self._redis,
                reid_services={
                    "person": _SessionScopedReidService(self._session_factory, self.build_person_reid_service),
                    "vehicle": _SessionScopedReidService(self._session_factory, self.build_vehicle_reid_service),
                },
                group_name=self._settings.consumer_group_name,
                read_count=self._settings.tracks_read_count,
                block_ms=self._settings.tracks_block_ms,
            )
            consumer.start()
            self._consumers[camera_id] = consumer
            logger.info("reid_consumer_started", camera_id=camera_id)

        removed_ids = set(self._consumers) - seen_ids
        for camera_id in removed_ids:
            await self._consumers.pop(camera_id).stop()
            logger.info("reid_consumer_stopped", camera_id=camera_id, reason="camera_removed")


class _SessionScopedReidService:
    """A fresh DB session per message, not one shared across a consumer's
    whole lifetime -- same reasoning as anpr-service's identical wrapper
    (SAS §11: a session outliving a single unit of work risks a stale
    transaction wedging the consumer)."""

    def __init__(self, session_factory, build_reid_service) -> None:
        self._session_factory = session_factory
        self._build_reid_service = build_reid_service

    async def process_track_event(self, event):
        async with self._session_factory() as session:
            service = self._build_reid_service(session)
            return await service.process_track_event(event)
