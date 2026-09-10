"""Owns the set of running per-camera `DetectionConsumer`s, reconciling
against Camera Management Service's camera list on a polling interval --
the same discovery/restart pattern every other pipeline stage uses."""

from __future__ import annotations

import asyncio

import httpx
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ibvap_common.logging import get_logger
from ibvap_common.redis_streams import build_redis_client

from app.core.config import Settings
from app.inference.ocr import read_plate_text
from app.inference.plate_detector import PlateDetector
from app.repositories.plate_read_repo import PlateReadRepository
from app.repositories.watchlist_repo import WatchlistRepository
from app.services.plate_service import PlateService
from app.streaming.camera_client import CameraClient
from app.streaming.detection_consumer import DetectionConsumer
from app.streaming.event_client import EventClient
from app.streaming.media_client import MediaClient

logger = get_logger(__name__)


class ReconcileManager:
    def __init__(self, settings: Settings, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._consumers: dict[str, DetectionConsumer] = {}
        self._redis: redis.Redis = build_redis_client(settings)
        self._http = httpx.AsyncClient()
        self._camera_client = CameraClient(self._http, settings)
        self._media_client = MediaClient(self._http, settings)
        self._event_client = EventClient(self._http, settings)
        self._plate_detector = PlateDetector(settings.haar_cascade_name)
        self._poll_task: asyncio.Task | None = None
        self._stopped = False

    @property
    def active_consumer_count(self) -> int:
        return len(self._consumers)

    def _build_plate_service(self, session: AsyncSession) -> PlateService:
        return PlateService(
            settings=self._settings,
            plate_repo=PlateReadRepository(session),
            watchlist_repo=WatchlistRepository(session),
            camera_client=self._camera_client,
            media_client=self._media_client,
            event_client=self._event_client,
            detect_plate=self._plate_detector.detect,
            read_plate=lambda crop: read_plate_text(crop, min_confidence=self._settings.min_ocr_confidence),
        )

    async def start(self) -> None:
        self._stopped = False
        await self._reconcile()
        self._poll_task = asyncio.create_task(self._poll_loop(), name="anpr-poll-loop")

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
                logger.warning("anpr_camera_list_poll_failed", error=str(exc))

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
                logger.info("anpr_consumer_restarting", camera_id=camera_id)

            # Each consumer gets its own session (via a per-message session,
            # created fresh in DetectionConsumer's own processing loop would
            # be more correct long-term, but PlateService's repos are cheap
            # to rebuild per detection -- see the per-message session used
            # here) -- consistent with how the rest of this pipeline scopes
            # a DB session per unit of work, not per consumer's lifetime.
            consumer = DetectionConsumer(
                camera_id=camera_id,
                redis_client=self._redis,
                plate_service=_SessionScopedPlateService(self._session_factory, self._build_plate_service),
                group_name=self._settings.consumer_group_name,
                read_count=self._settings.detections_read_count,
                block_ms=self._settings.detections_block_ms,
            )
            consumer.start()
            self._consumers[camera_id] = consumer
            logger.info("anpr_consumer_started", camera_id=camera_id)

        removed_ids = set(self._consumers) - seen_ids
        for camera_id in removed_ids:
            await self._consumers.pop(camera_id).stop()
            logger.info("anpr_consumer_stopped", camera_id=camera_id, reason="camera_removed")


class _SessionScopedPlateService:
    """`DetectionConsumer` holds one long-lived `PlateService`, but every
    other consumer in this codebase opens a fresh DB session per message
    (SAS §11 -- a session outliving a single unit of work risks a stale
    transaction wedging the whole consumer). This wraps that: a real
    `PlateService` is built against a fresh session for each call, not
    shared across messages."""

    def __init__(self, session_factory, build_plate_service) -> None:
        self._session_factory = session_factory
        self._build_plate_service = build_plate_service

    async def process_vehicle_detection(self, detection):
        async with self._session_factory() as session:
            service = self._build_plate_service(session)
            return await service.process_vehicle_detection(detection)
