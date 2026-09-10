from __future__ import annotations

import asyncio

import httpx
import redis.asyncio as redis

from ibvap_common.logging import get_logger
from ibvap_common.redis_streams import build_redis_client

from app.core.config import Settings
from app.workers.camera_worker import CameraWorker

logger = get_logger(__name__)


class WorkerManager:
    """Owns the set of running `CameraWorker`s and reconciles it against the
    Camera Management Service's camera list on a polling interval, so newly
    created/deleted cameras (via the Cameras page or the upload endpoint)
    are picked up without restarting the ingestion service."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._workers: dict[str, CameraWorker] = {}
        self._redis: redis.Redis = build_redis_client(settings)
        self._http = httpx.AsyncClient()
        self._poll_task: asyncio.Task | None = None
        self._stopped = False

    async def start(self) -> None:
        self._stopped = False
        await self._reconcile()
        self._poll_task = asyncio.create_task(self._poll_loop(), name="ingestion-poll-loop")

    @property
    def active_worker_count(self) -> int:
        return len(self._workers)

    async def stop(self) -> None:
        self._stopped = True
        if self._poll_task is not None:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        await asyncio.gather(*(w.stop() for w in self._workers.values()))
        self._workers.clear()
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
                # M11: one logical camera, two simultaneous capture workers
                # (RGB + thermal) -- tracked under compound keys so both can
                # coexist in `self._workers` (which is otherwise one entry
                # per camera_id, unchanged for every other type below).
                seen_keys.add(f"{camera_id}:rgb")
                seen_keys.add(f"{camera_id}:thermal")
                await self._reconcile_worker(
                    worker_key=f"{camera_id}:rgb", camera_id=camera_id, camera_type=camera_type,
                    source_url=config.get("sourceUrl"), modality=None, report_status=True,
                )
                await self._reconcile_worker(
                    worker_key=f"{camera_id}:thermal", camera_id=camera_id, camera_type=camera_type,
                    source_url=config.get("thermalSourceUrl"), modality="thermal", report_status=False,
                )
            else:
                seen_keys.add(camera_id)
                await self._reconcile_worker(
                    worker_key=camera_id, camera_id=camera_id, camera_type=camera_type,
                    source_url=config.get("sourceUrl"), modality=None, report_status=True,
                )

        # Stop workers for cameras (or camera/modality pairs) that no longer exist.
        removed_keys = set(self._workers) - seen_keys
        for worker_key in removed_keys:
            await self._workers.pop(worker_key).stop()
            logger.info("camera_worker_stopped", camera_id=worker_key, reason="camera_removed")

    async def _reconcile_worker(
        self,
        *,
        worker_key: str,
        camera_id: str,
        camera_type: str,
        source_url: str | None,
        modality: str | None,
        report_status: bool,
    ) -> None:
        """Same reconcile-one-worker logic the loop above always ran
        per-camera, factored out so it can run once (unchanged behavior)
        for every existing single-stream camera type, or twice -- once per
        modality -- for a 'dual' camera (M11) without duplicating the
        stuck/restart/skip-if-no-source handling."""
        existing = self._workers.get(worker_key)
        if existing is not None:
            stuck_seconds = existing.seconds_since_last_frame()
            is_stuck = stuck_seconds > self._settings.stuck_worker_timeout_seconds
            if existing.is_running and existing.source_url == source_url and not is_stuck:
                return  # already running the current source -- nothing to do
            # Either the task exited (e.g. source failed to open), a new
            # file was uploaded to this camera, or the worker is stuck
            # (see CameraWorker.seconds_since_last_frame's own docstring)
            # -- stop it so it's recreated below against the current
            # config instead of silently continuing to stream a stale/
            # failed/hung source.
            await existing.stop()
            del self._workers[worker_key]
            if is_stuck:
                logger.warning(
                    "camera_worker_stuck_restarting", camera_id=worker_key, idle_seconds=round(stuck_seconds),
                )
            else:
                logger.info("camera_worker_restarting", camera_id=worker_key)

        if camera_type == "file" and not source_url:
            return  # no video uploaded yet -- nothing to open
        if camera_type == "dual" and not source_url:
            # A 'dual' camera missing one of its two URLs (shouldn't happen
            # given camera-service's own create-time validation, but a
            # partial config update could still leave one blank) -- skip
            # just this modality's worker rather than failing the other.
            return

        worker = CameraWorker(
            camera_id=camera_id,
            camera_type=camera_type,
            source_url=source_url,
            settings=self._settings,
            redis_client=self._redis,
            http_client=self._http,
            modality=modality,
            report_status=report_status,
        )
        worker.start()
        self._workers[worker_key] = worker
        logger.info("camera_worker_started", camera_id=worker_key, type=camera_type)
