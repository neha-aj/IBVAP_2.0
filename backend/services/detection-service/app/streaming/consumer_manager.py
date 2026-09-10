"""Owns the set of running `FrameConsumer`s and reconciles it against the
Camera Management Service's camera list on a polling interval -- the same
discovery pattern Stream Ingestion's `WorkerManager` uses (M3), so newly
created/deleted cameras are picked up without restarting the service, and a
consumer whose task died gets restarted on the next pass instead of being
stuck forever.
"""

from __future__ import annotations

import asyncio

import httpx
import redis.asyncio as redis

from ibvap_common.logging import get_logger
from ibvap_common.redis_streams import build_redis_client

from app.core.config import Settings
from app.inference.base import InferenceEngine
from app.inference.fusion_merger import FusionMerger, FusionSettings, ModalityFeed
from app.streaming.detection_publisher import DetectionPublisher
from app.streaming.frame_consumer import FrameConsumer

logger = get_logger(__name__)


class ConsumerManager:
    def __init__(self, settings: Settings, engine: InferenceEngine) -> None:
        self._settings = settings
        self._engine = engine
        self._consumers: dict[str, FrameConsumer] = {}
        self._redis: redis.Redis = build_redis_client(settings)
        self._publisher = DetectionPublisher(
            self._redis,
            stream_maxlen=settings.detections_stream_maxlen,
            current_ttl_seconds=settings.current_detections_ttl_seconds,
        )
        self._http = httpx.AsyncClient()
        self._poll_task: asyncio.Task | None = None
        self._stopped = False

    @property
    def active_consumer_count(self) -> int:
        return len(self._consumers)

    async def start(self) -> None:
        self._stopped = False
        await self._reconcile()
        self._poll_task = asyncio.create_task(self._poll_loop(), name="detection-poll-loop")

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
                logger.warning("camera_list_poll_failed", error=str(exc))

    async def _fetch_camera_configs(self) -> list[dict]:
        response = await self._http.get(
            f"{self._settings.camera_service_url}/internal/cameras",
            headers={"X-Internal-Token": self._settings.internal_service_token},
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()

    async def _reconcile(self) -> None:
        configs = await self._fetch_camera_configs()
        seen_keys: set[str] = set()

        for config in configs:
            camera_id = config["id"]
            camera_type = config["type"]

            if camera_type == "dual":
                # M11: one 'dual' camera gets two FrameConsumers (RGB +
                # thermal) sharing one FusionMerger, tracked under compound
                # keys in `self._consumers` so both coexist -- every other
                # camera type below keeps the exact one-consumer-per-
                # camera_id behavior this loop always had.
                seen_keys.add(f"{camera_id}:rgb")
                seen_keys.add(f"{camera_id}:thermal")
                await self._reconcile_dual_pair(camera_id)
            else:
                seen_keys.add(camera_id)
                await self._reconcile_single(consumer_key=camera_id, camera_id=camera_id)

        removed_keys = set(self._consumers) - seen_keys
        for consumer_key in removed_keys:
            await self._consumers.pop(consumer_key).stop()
            logger.info("frame_consumer_stopped", camera_id=consumer_key, reason="camera_removed")

    async def _reconcile_single(self, *, consumer_key: str, camera_id: str) -> None:
        """Exactly the original one-consumer-per-camera reconcile logic,
        factored out only so `_reconcile_dual_pair` can share the
        create/restart mechanics without duplicating them -- every
        non-'dual' camera's behavior here is unchanged from before M11."""
        existing = self._consumers.get(consumer_key)
        if existing is not None:
            if existing.is_running:
                return
            await existing.stop()
            del self._consumers[consumer_key]
            logger.info("frame_consumer_restarting", camera_id=consumer_key)

        self._start_consumer(consumer_key=consumer_key, camera_id=camera_id, publisher=self._publisher, modality=None)

    async def _reconcile_dual_pair(self, camera_id: str) -> None:
        rgb_key, thermal_key = f"{camera_id}:rgb", f"{camera_id}:thermal"
        rgb = self._consumers.get(rgb_key)
        thermal = self._consumers.get(thermal_key)
        if rgb is not None and rgb.is_running and thermal is not None and thermal.is_running:
            return  # both halves healthy -- nothing to do

        # Either half missing or dead -- recreate both together against a
        # fresh FusionMerger rather than trying to keep one half alive fed
        # by a merger the other half has stopped submitting to.
        for key, existing in ((rgb_key, rgb), (thermal_key, thermal)):
            if existing is not None:
                await existing.stop()
                self._consumers.pop(key, None)
        logger.info("frame_consumer_restarting", camera_id=camera_id)

        merger = FusionMerger(
            camera_id=camera_id,
            publisher=self._publisher,
            settings=FusionSettings(
                frame_sync_tolerance_ms=self._settings.fusion_frame_sync_tolerance_ms,
                low_conf_threshold=self._settings.fusion_low_conf_threshold,
                confidence_boost=self._settings.fusion_confidence_boost,
                suppress_threshold=self._settings.fusion_suppress_threshold,
                min_iou=self._settings.fusion_min_iou,
            ),
        )
        self._start_consumer(
            consumer_key=rgb_key, camera_id=camera_id,
            publisher=ModalityFeed(merger, modality="rgb"), modality=None,
        )
        self._start_consumer(
            consumer_key=thermal_key, camera_id=camera_id,
            publisher=ModalityFeed(merger, modality="thermal"), modality="thermal",
        )

    def _start_consumer(
        self, *, consumer_key: str, camera_id: str, publisher: DetectionPublisher | ModalityFeed, modality: str | None
    ) -> None:
        consumer = FrameConsumer(
            camera_id=camera_id,
            redis_client=self._redis,
            engine=self._engine,
            publisher=publisher,
            group_name=self._settings.consumer_group_name,
            read_count=self._settings.frames_read_count,
            block_ms=self._settings.frames_block_ms,
            modality=modality,
        )
        consumer.start()
        self._consumers[consumer_key] = consumer
        logger.info("frame_consumer_started", camera_id=consumer_key)
