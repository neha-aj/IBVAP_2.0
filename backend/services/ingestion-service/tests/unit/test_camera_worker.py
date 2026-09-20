import asyncio
import time

import httpx
import numpy as np
import pytest
import redis.asyncio as redis

from app.capture.file_source import FileFrameSource
from app.core.config import Settings
from app.workers.camera_worker import CameraWorker


def _settings(**overrides) -> Settings:
    defaults = {
        "postgres_user": "u", "postgres_password": "p", "postgres_db": "d", "jwt_secret": "s",
        "internal_service_token": "t",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _worker() -> CameraWorker:
    return CameraWorker(
        camera_id="CAM-01", camera_type="file", source_url="/videos/a.mp4",
        settings=_settings(), redis_client=redis.Redis(), http_client=httpx.AsyncClient(),
    )


def test_seconds_since_last_frame_starts_near_zero() -> None:
    """Set at construction (not only once the capture loop starts reading)
    so a worker that's slow to open isn't immediately misread as stuck."""
    worker = _worker()
    assert worker.seconds_since_last_frame() < 1.0


def test_seconds_since_last_frame_reflects_time_since_last_update() -> None:
    worker = _worker()
    worker._last_frame_at = time.monotonic() - 45.0
    assert worker.seconds_since_last_frame() >= 45.0


def test_default_modality_and_report_status_are_unchanged_from_before_m11() -> None:
    """Every existing single-stream camera constructs a CameraWorker without
    passing modality/report_status at all -- both must default to exactly
    the pre-M11 behavior (own cache slot keyed by camera_id, status
    reporting on)."""
    worker = _worker()
    assert worker._modality is None
    assert worker._should_report_status is True
    assert worker._cache_key == "CAM-01"


def test_dual_camera_thermal_worker_gets_its_own_cache_key_and_no_status_reporting() -> None:
    worker = CameraWorker(
        camera_id="CAM-DUAL-01", camera_type="dual", source_url="rtsp://thermal/stream",
        settings=_settings(), redis_client=redis.Redis(), http_client=httpx.AsyncClient(),
        modality="thermal", report_status=False,
    )
    assert worker._modality == "thermal"
    assert worker._should_report_status is False
    # Distinct from the RGB worker's cache slot ("CAM-DUAL-01") so the two
    # don't overwrite each other's live-preview frame.
    assert worker._cache_key == "CAM-DUAL-01:thermal"
    # The real camera id is preserved for status/correlation purposes even
    # though this worker is never the one that reports status.
    assert worker.camera_id == "CAM-DUAL-01"


class _FakeRedis:
    """Just enough of redis.asyncio.Redis for the pause check."""

    def __init__(self, paused_ids: set[str] | None = None, *, fail: bool = False) -> None:
        self.paused_ids = paused_ids or set()
        self.fail = fail

    async def sismember(self, key: str, member: str) -> bool:
        if self.fail:
            raise ConnectionError("redis down")
        return member in self.paused_ids


def _worker_with(redis_client) -> CameraWorker:
    return CameraWorker(
        camera_id="CAM-01", camera_type="file", source_url="/videos/a.mp4",
        settings=_settings(), redis_client=redis_client, http_client=httpx.AsyncClient(),
    )


@pytest.mark.asyncio
async def test_is_paused_reflects_membership_of_the_paused_set() -> None:
    fake = _FakeRedis({"CAM-01"})
    worker = _worker_with(fake)
    assert await worker._is_paused() is True

    # Resume: takes effect at the next poll, not on every call.
    fake.paused_ids.clear()
    assert await worker._is_paused() is True
    worker._pause_checked_at = 0.0
    assert await worker._is_paused() is False


@pytest.mark.asyncio
async def test_is_paused_is_false_for_a_camera_not_in_the_set() -> None:
    worker = _worker_with(_FakeRedis({"SOME-OTHER-CAM"}))
    assert await worker._is_paused() is False


@pytest.mark.asyncio
async def test_is_paused_keeps_last_known_state_when_redis_fails() -> None:
    """A Redis blip must never flip a paused camera back on (or stop an
    unpaused one) -- capture just carries on in whatever state it was in."""
    fake = _FakeRedis({"CAM-01"})
    worker = _worker_with(fake)
    assert await worker._is_paused() is True

    fake.fail = True
    worker._pause_checked_at = 0.0
    assert await worker._is_paused() is True


class _CountingFileSource(FileFrameSource):
    def __init__(self) -> None:
        self.reads = 0
        self._loop_generation = 0

    @property
    def declared_fps(self) -> float:
        return 30.0

    def read(self):
        self.reads += 1
        return np.zeros((8, 8, 3), dtype=np.uint8)


class _RecordingPublisher:
    def __init__(self) -> None:
        self.published = 0
        self.discarded = 0

    async def discard_backlog(self, *args, **kwargs) -> None:
        self.discarded += 1

    async def publish(self, *args, **kwargs) -> None:
        self.published += 1


@pytest.mark.asyncio
async def test_paused_file_camera_reads_nothing_and_publishes_nothing_then_resumes() -> None:
    fake = _FakeRedis({"CAM-01"})
    worker = _worker_with(fake)
    publisher = _RecordingPublisher()
    worker._publisher = publisher
    worker._should_report_status = False  # no camera-service to PATCH in a unit test
    worker._stop_requested = False
    source = _CountingFileSource()

    task = asyncio.create_task(worker._capture_loop(source, 30.0))
    await asyncio.sleep(0.3)
    assert source.reads == 0  # file playback is frozen exactly where it was
    assert publisher.published == 0  # nothing reaches the analysis pipeline
    assert publisher.discarded == 1  # frames already queued are dropped once, at the moment of pausing

    fake.paused_ids.clear()
    await asyncio.sleep(1.0)  # > the 0.5s pause poll
    worker._stop_requested = True
    await asyncio.wait_for(task, timeout=3)
    assert source.reads > 0
    assert publisher.published > 0


class _RecordingCache:
    def __init__(self) -> None:
        self.set_keys: list[str] = []
        self.cleared: list[str] = []

    async def set(self, key: str, data: bytes) -> None:
        self.set_keys.append(key)

    async def clear(self, key: str) -> None:
        self.cleared.append(key)


class _KwargsRecordingPublisher(_RecordingPublisher):
    def __init__(self) -> None:
        super().__init__()
        self.derived_flags: list[bool] = []

    async def publish(self, *args, **kwargs) -> None:
        self.derived_flags.append(kwargs.get("derived_thermal", False))
        await super().publish(*args, **kwargs)


async def _run_worker_briefly(worker: CameraWorker, monkeypatch) -> _RecordingCache:
    import app.workers.camera_worker as module

    cache = _RecordingCache()
    monkeypatch.setattr(module, "frame_cache", cache)
    worker._should_report_status = False
    worker._stop_requested = False
    task = asyncio.create_task(worker._capture_loop(_CountingFileSource(), 30.0))
    await asyncio.sleep(0.4)
    worker._stop_requested = True
    await asyncio.wait_for(task, timeout=3)
    return cache


@pytest.mark.asyncio
async def test_worker_renders_a_thermal_preview_and_flags_frames_when_deriving(monkeypatch) -> None:
    worker = _worker_with(_FakeRedis())
    worker.derive_thermal = True
    worker._publisher = _KwargsRecordingPublisher()

    cache = await _run_worker_briefly(worker, monkeypatch)

    assert "CAM-01" in cache.set_keys and "CAM-01:thermal" in cache.set_keys
    assert worker._publisher.derived_flags and all(worker._publisher.derived_flags)


@pytest.mark.asyncio
async def test_worker_writes_no_thermal_preview_by_default(monkeypatch) -> None:
    worker = _worker_with(_FakeRedis())
    worker._publisher = _KwargsRecordingPublisher()

    cache = await _run_worker_briefly(worker, monkeypatch)

    assert "CAM-01:thermal" not in cache.set_keys
    assert worker._publisher.derived_flags and not any(worker._publisher.derived_flags)
