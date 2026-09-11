"""One CameraWorker per camera, run as an asyncio task. OpenCV's
`VideoCapture.read()` is blocking, so the actual read loop runs in a worker
thread via `asyncio.to_thread`; this coroutine just orchestrates timing,
decimation, publishing, and status reporting around it (SAS §5.1).
"""

from __future__ import annotations

import asyncio
import hashlib
import time

import cv2
import httpx
import redis.asyncio as redis

from ibvap_common.logging import get_logger

from app.capture.base import FrameSource
from app.capture.factory import build_frame_source
from app.core.config import Settings
from app.preview.frame_cache import frame_cache
from app.preview.frame_ring_buffer import frame_ring_buffer
from app.streaming.frame_publisher import FramePublisher

logger = get_logger(__name__)


class CameraWorker:
    def __init__(
        self,
        *,
        camera_id: str,
        camera_type: str,
        source_url: str | None,
        settings: Settings,
        redis_client: redis.Redis,
        http_client: httpx.AsyncClient,
        modality: str | None = None,
        report_status: bool = True,
    ) -> None:
        self.camera_id = camera_id
        # Public so WorkerManager can detect a re-upload (new sourceUrl on an
        # already-running worker) and recreate this worker instead of
        # silently continuing to stream the old file forever.
        self.source_url = source_url
        self._camera_type = camera_type
        self._settings = settings
        self._redis = redis_client
        self._publisher = FramePublisher(
            redis_client, jpeg_quality=settings.jpeg_quality, maxlen=settings.frame_stream_maxlen
        )
        self._http = http_client
        # M11: both default to None/True, exactly preserving every existing
        # single-stream camera's behavior unchanged. A 'dual' camera's
        # second (thermal) worker is the only caller that ever passes
        # modality="thermal" (own frame stream + own preview-cache slot,
        # see _run/_capture_loop below) and report_status=False (the RGB
        # worker of the pair is the one that keeps driving this camera's
        # reported status/fps -- both workers PATCHing the same camera
        # every second would just have them overwrite each other).
        self._modality = modality
        self._should_report_status = report_status
        # M11: a 'dual' camera's second worker uses a distinct preview-cache
        # slot (see frame_cache calls below) so it doesn't fight the RGB
        # worker over the one live-preview entry for this camera_id.
        self._cache_key = camera_id if modality is None else f"{camera_id}:{modality}"
        self._task: asyncio.Task | None = None
        self._stop_requested = False
        self._reported_status: str | None = None
        # Evidence pre-roll: throttles FrameRingBuffer.push() to
        # preroll_sample_interval_seconds regardless of capture_fps -- see
        # that setting's own docstring for why (bounded memory).
        self._last_preroll_push_at = 0.0
        # Set at construction (not just inside the capture loop) so a worker
        # that's slow to open isn't immediately misread as stuck by
        # `seconds_since_last_frame` before it's had any chance to read a
        # frame at all.
        self._last_frame_at = time.monotonic()

    @property
    def is_running(self) -> bool:
        """False once the underlying task has exited (e.g. the source failed
        to open) so `WorkerManager` can detect and restart it on the next
        reconcile pass instead of leaving a dead entry in place forever.

        Deliberately NOT sufficient on its own to detect every dead worker:
        a blocking native call (OpenCV/FFmpeg's `VideoCapture.read()`, run in
        a worker thread via `asyncio.to_thread`) can hang forever without
        ever returning or raising -- observed live after long uptimes on a
        looping file source. `is_running` stays True the whole time (the
        task is genuinely still "running", just permanently blocked), so
        `WorkerManager` also checks `seconds_since_last_frame()` -- see that
        method's own docstring."""
        return self._task is not None and not self._task.done()

    def seconds_since_last_frame(self) -> float:
        """How long since this worker last actually produced a frame --
        `WorkerManager` uses this alongside `is_running` to catch a worker
        whose underlying blocking read has hung (not just crashed): Python
        can't forcibly stop a native call stuck in a worker thread, so the
        only real recovery is detecting "no progress for too long" from the
        outside and replacing the worker, leaving the stuck thread to leak
        rather than block forever (an accepted, documented tradeoff -- there
        is no way to truly kill it once OpenCV/FFmpeg is wedged)."""
        return time.monotonic() - self._last_frame_at

    def start(self) -> None:
        self._stop_requested = False
        self._task = asyncio.create_task(self._run(), name=f"camera-worker-{self.camera_id}")

    async def stop(self) -> None:
        self._stop_requested = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await frame_cache.clear(self._cache_key)
        await frame_ring_buffer.clear(self._cache_key)

    def _loop_generation_key(self) -> str:
        # Scoped by source_url (hashed -- it's a filesystem path, not a safe
        # Redis-key fragment) so a fresh upload to this camera starts a new
        # generation-0 count instead of inheriting whatever generation the
        # *previous* video had reached.
        source_fingerprint = hashlib.sha1((self.source_url or "").encode()).hexdigest()[:12]
        return f"cam:{self.camera_id}:{source_fingerprint}:loop_generation"

    async def _load_loop_generation(self) -> int:
        raw = await self._redis.get(self._loop_generation_key())
        return int(raw) if raw is not None else 0

    async def _run(self) -> None:
        initial_generation = await self._load_loop_generation()
        source = build_frame_source(
            camera_type=self._camera_type,
            source_url=self.source_url,
            settings=self._settings,
            initial_generation=initial_generation,
        )
        opened = await asyncio.to_thread(source.open)
        if not opened:
            logger.warning("camera_open_failed", camera_id=self.camera_id, type=self._camera_type)
            await self._report_status("offline", fps=0)
            return

        declared_fps = source.declared_fps
        await self._report_status("online", fps=round(declared_fps))

        try:
            await self._capture_loop(source, declared_fps)
        finally:
            await asyncio.to_thread(source.release)
            await self._report_status("offline", fps=0)

    async def _capture_loop(self, source: FrameSource, declared_fps: float) -> None:
        min_frame_interval = 1.0 / max(self._settings.capture_fps, 1)
        publish_interval = 1.0 / max(self._settings.inference_fps, 1)

        last_publish_at = 0.0
        self._last_frame_at = time.monotonic()
        frames_in_window = 0
        window_start = time.monotonic()
        measured_fps = declared_fps
        persisted_generation = source.loop_generation

        while not self._stop_requested:
            loop_start = time.monotonic()
            frame = await asyncio.to_thread(source.read)
            now = time.monotonic()

            if frame is None:
                if now - self._last_frame_at > self._settings.heartbeat_timeout_seconds:
                    logger.warning("camera_heartbeat_lost", camera_id=self.camera_id)
                    await self._report_status("offline", fps=0)
                await asyncio.sleep(min_frame_interval)
                continue

            self._last_frame_at = now
            frames_in_window += 1

            # Preview cache updates on every captured frame for a smooth live view.
            ok, encoded = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self._settings.jpeg_quality]
            )
            if ok:
                jpeg_bytes = encoded.tobytes()
                await frame_cache.set(self._cache_key, jpeg_bytes)
                # Evidence pre-roll: sampled well below capture_fps (see
                # preroll_sample_interval_seconds), additive alongside the
                # frame_cache write above -- doesn't touch the live preview.
                if now - self._last_preroll_push_at >= self._settings.preroll_sample_interval_seconds:
                    await frame_ring_buffer.push(
                        self._cache_key, jpeg_bytes, max_age_seconds=self._settings.preroll_buffer_seconds
                    )
                    self._last_preroll_push_at = now

            # Downsample to inference_fps for the Redis Stream (SAS §5.2 input).
            if now - last_publish_at >= publish_interval:
                await self._publisher.publish(
                    self.camera_id, frame, loop_generation=source.loop_generation, modality=self._modality
                )
                last_publish_at = now
                if source.loop_generation != persisted_generation:
                    persisted_generation = source.loop_generation
                    await self._redis.set(self._loop_generation_key(), persisted_generation)

            # Recompute measured FPS and camera status roughly once a second.
            if now - window_start >= 1.0:
                measured_fps = frames_in_window / (now - window_start)
                frames_in_window = 0
                window_start = now
                await self._update_status_from_fps(measured_fps, declared_fps)

            elapsed = time.monotonic() - loop_start
            await asyncio.sleep(max(0.0, min_frame_interval - elapsed))

    async def _update_status_from_fps(self, measured_fps: float, declared_fps: float) -> None:
        ratio = measured_fps / declared_fps if declared_fps > 0 else 1.0
        status = "online" if ratio >= self._settings.warning_fps_ratio else "warning"
        await self._report_status(status, fps=round(measured_fps))

    async def _report_status(self, status: str, *, fps: int) -> None:
        if not self._should_report_status:
            return
        # Always push fps (it changes often); only log on status transitions
        # to avoid noisy logs (SAS §10 structured logging).
        if status != self._reported_status:
            logger.info("camera_status_changed", camera_id=self.camera_id, status=status)
            self._reported_status = status
        try:
            await self._http.patch(
                f"{self._settings.camera_service_url}/internal/cameras/{self.camera_id}/status",
                json={"status": status, "fps": fps},
                headers={"X-Internal-Token": self._settings.internal_service_token},
                timeout=5.0,
            )
        except httpx.HTTPError as exc:
            logger.warning("camera_status_push_failed", camera_id=self.camera_id, error=str(exc))
