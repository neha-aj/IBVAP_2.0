"""Owns the set of running `TrackConsumer`s (one per camera) plus the
single global `StatusConsumer`, reconciling against the Camera Management
Service's camera list on a polling interval -- the same discovery/restart
pattern every other pipeline stage (Ingestion, Detection, Tracking) uses.
"""

from __future__ import annotations

import asyncio

import httpx
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ibvap_common.logging import get_logger
from ibvap_common.redis_streams import build_redis_client

from app.core.config import Settings
from app.rules.engine import RuleEngine
from app.streaming.camera_client import CameraClient
from app.streaming.pubsub_publisher import PubSubPublisher
from app.streaming.recording_client import RecordingClient
from app.streaming.snapshot_client import SnapshotClient
from app.streaming.status_consumer import StatusConsumer
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
        self._snapshot_client = SnapshotClient(self._http, settings)
        self._recording_client = RecordingClient(self._http, settings)
        self._rule_engine = RuleEngine(
            settings, self._camera_client.get_zones, self._camera_client.get_zone_lines,
            self._camera_client.get_camera_info,
        )
        self._publisher = PubSubPublisher(
            self._redis, self._camera_client, self._snapshot_client, self._recording_client, session_factory,
            settings,
        )
        self._status_consumer = StatusConsumer(
            redis_client=self._redis,
            session_factory=session_factory,
            rule_engine=self._rule_engine,
            publisher=self._publisher,
        )
        self._poll_task: asyncio.Task | None = None
        self._stopped = False

    @property
    def active_consumer_count(self) -> int:
        return len(self._consumers)

    @property
    def publisher(self) -> PubSubPublisher:
        """Exposed for `POST /internal/events` (doc08 §4's shared ingestion
        path for Category B AI services) -- reuses this same publisher
        rather than each new AI service needing its own persist/publish
        wiring."""
        return self._publisher

    async def start(self) -> None:
        self._stopped = False
        self._status_consumer.start()
        await self._reconcile()
        self._poll_task = asyncio.create_task(self._poll_loop(), name="event-alert-poll-loop")

    async def stop(self) -> None:
        self._stopped = True
        if self._poll_task is not None:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        await self._status_consumer.stop()
        await asyncio.gather(*(c.stop() for c in self._consumers.values()))
        self._consumers.clear()
        await self._http.aclose()
        await self._redis.aclose()

    async def _poll_loop(self) -> None:
        while not self._stopped:
            await asyncio.sleep(self._settings.camera_refresh_interval_seconds)
            try:
                await self._reconcile()
            except Exception as exc:  # noqa: BLE001
                logger.warning("camera_list_poll_failed", error=str(exc))

    async def _fetch_camera_ids(self) -> list[str]:
        response = await self._http.get(
            f"{self._settings.camera_service_url}/internal/cameras",
            headers={"X-Internal-Token": self._settings.internal_service_token},
            timeout=10.0,
        )
        response.raise_for_status()
        return [config["id"] for config in response.json()]

    async def _reconcile(self) -> None:
        camera_ids = await self._fetch_camera_ids()
        seen_ids = set(camera_ids)

        for camera_id in camera_ids:
            existing = self._consumers.get(camera_id)
            if existing is not None:
                if existing.is_running:
                    continue
                await existing.stop()
                del self._consumers[camera_id]
                logger.info("track_consumer_restarting", camera_id=camera_id)

            consumer = TrackConsumer(
                camera_id=camera_id,
                redis_client=self._redis,
                session_factory=self._session_factory,
                rule_engine=self._rule_engine,
                publisher=self._publisher,
                group_name=self._settings.consumer_group_name,
                read_count=self._settings.tracks_read_count,
                block_ms=self._settings.tracks_block_ms,
            )
            consumer.start()
            self._consumers[camera_id] = consumer
            logger.info("track_consumer_started", camera_id=camera_id)

        removed_ids = set(self._consumers) - seen_ids
        for camera_id in removed_ids:
            await self._consumers.pop(camera_id).stop()
            logger.info("track_consumer_stopped", camera_id=camera_id, reason="camera_removed")
