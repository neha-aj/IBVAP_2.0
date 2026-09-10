"""Covers the stuck-worker watchdog added to `WorkerManager._reconcile()` --
a hung `CameraWorker` (blocked forever inside a native video-read call, so
`is_running` stays True) must still get replaced once it's produced no
frames for longer than `stuck_worker_timeout_seconds`. Existing behavior
(healthy workers left alone, dead workers restarted) is covered too, so a
regression in either direction would show up here."""

from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.workers.worker_manager import WorkerManager


def _settings(**overrides) -> Settings:
    defaults = {
        "postgres_user": "u", "postgres_password": "p", "postgres_db": "d", "jwt_secret": "s",
        "internal_service_token": "t", "stuck_worker_timeout_seconds": 30,
    }
    defaults.update(overrides)
    return Settings(**defaults)


class FakeWorker:
    def __init__(self, *, is_running: bool, source_url: str | None, idle_seconds: float) -> None:
        self.is_running = is_running
        self.source_url = source_url
        self._idle_seconds = idle_seconds
        self.stop_called = False

    def seconds_since_last_frame(self) -> float:
        return self._idle_seconds

    async def stop(self) -> None:
        self.stop_called = True


def _config(camera_id: str = "CAM-01", source_url: str = "/videos/a.mp4") -> dict:
    return {"id": camera_id, "type": "file", "sourceUrl": source_url}


@pytest.mark.asyncio
async def test_reconcile_leaves_healthy_running_worker_alone() -> None:
    manager = WorkerManager(_settings())
    fake = FakeWorker(is_running=True, source_url="/videos/a.mp4", idle_seconds=1.0)
    manager._workers["CAM-01"] = fake
    manager._fetch_camera_configs = AsyncMock(return_value=[_config()])

    await manager._reconcile()

    assert fake.stop_called is False
    assert manager._workers["CAM-01"] is fake
    await manager.stop()


@pytest.mark.asyncio
async def test_reconcile_replaces_worker_whose_task_already_died() -> None:
    """Pre-existing behavior (not the new watchdog) -- must still work."""
    manager = WorkerManager(_settings())
    fake = FakeWorker(is_running=False, source_url="/videos/a.mp4", idle_seconds=1.0)
    manager._workers["CAM-01"] = fake
    manager._fetch_camera_configs = AsyncMock(return_value=[_config()])

    await manager._reconcile()

    assert fake.stop_called is True
    assert manager._workers["CAM-01"] is not fake
    await manager.stop()


@pytest.mark.asyncio
async def test_reconcile_replaces_stuck_worker_even_though_is_running_true() -> None:
    """The actual bug this watchdog fixes: a hung native read leaves
    `is_running` True forever, so only `seconds_since_last_frame` can catch
    it."""
    manager = WorkerManager(_settings(stuck_worker_timeout_seconds=30))
    fake = FakeWorker(is_running=True, source_url="/videos/a.mp4", idle_seconds=999.0)
    manager._workers["CAM-01"] = fake
    manager._fetch_camera_configs = AsyncMock(return_value=[_config()])

    await manager._reconcile()

    assert fake.stop_called is True
    assert manager._workers["CAM-01"] is not fake
    await manager.stop()


@pytest.mark.asyncio
async def test_reconcile_does_not_flag_worker_within_stuck_threshold() -> None:
    manager = WorkerManager(_settings(stuck_worker_timeout_seconds=30))
    fake = FakeWorker(is_running=True, source_url="/videos/a.mp4", idle_seconds=29.0)
    manager._workers["CAM-01"] = fake
    manager._fetch_camera_configs = AsyncMock(return_value=[_config()])

    await manager._reconcile()

    assert fake.stop_called is False
    assert manager._workers["CAM-01"] is fake
    await manager.stop()


def _dual_config(
    camera_id: str = "CAM-DUAL-01", source_url: str = "rtsp://rgb/stream", thermal_url: str = "rtsp://thermal/stream"
) -> dict:
    return {"id": camera_id, "type": "dual", "sourceUrl": source_url, "thermalSourceUrl": thermal_url}


@pytest.mark.asyncio
async def test_reconcile_starts_two_workers_for_a_dual_camera() -> None:
    """M11: one 'dual' camera config must produce exactly two CameraWorkers
    -- one per modality -- under compound keys, existing single-stream
    cameras' one-worker-per-camera_id behavior (covered by every test above)
    left completely alone."""
    manager = WorkerManager(_settings())
    manager._fetch_camera_configs = AsyncMock(return_value=[_dual_config()])

    await manager._reconcile()

    assert set(manager._workers) == {"CAM-DUAL-01:rgb", "CAM-DUAL-01:thermal"}
    rgb_worker = manager._workers["CAM-DUAL-01:rgb"]
    thermal_worker = manager._workers["CAM-DUAL-01:thermal"]
    # Both workers report the real camera id (for status/correlation) even
    # though they're tracked under different keys internally.
    assert rgb_worker.camera_id == "CAM-DUAL-01"
    assert thermal_worker.camera_id == "CAM-DUAL-01"
    assert rgb_worker.source_url == "rtsp://rgb/stream"
    assert thermal_worker.source_url == "rtsp://thermal/stream"
    # Only the RGB worker of the pair drives this camera's reported
    # status/fps -- both PATCHing every second would just clobber each other.
    assert rgb_worker._should_report_status is True
    assert thermal_worker._should_report_status is False
    assert rgb_worker._modality is None
    assert thermal_worker._modality == "thermal"
    await manager.stop()


@pytest.mark.asyncio
async def test_reconcile_leaves_healthy_dual_camera_workers_alone() -> None:
    manager = WorkerManager(_settings())
    rgb_fake = FakeWorker(is_running=True, source_url="rtsp://rgb/stream", idle_seconds=1.0)
    thermal_fake = FakeWorker(is_running=True, source_url="rtsp://thermal/stream", idle_seconds=1.0)
    manager._workers["CAM-DUAL-01:rgb"] = rgb_fake
    manager._workers["CAM-DUAL-01:thermal"] = thermal_fake
    manager._fetch_camera_configs = AsyncMock(return_value=[_dual_config()])

    await manager._reconcile()

    assert rgb_fake.stop_called is False
    assert thermal_fake.stop_called is False
    assert manager._workers["CAM-DUAL-01:rgb"] is rgb_fake
    assert manager._workers["CAM-DUAL-01:thermal"] is thermal_fake
    await manager.stop()


@pytest.mark.asyncio
async def test_reconcile_stops_both_dual_workers_when_camera_removed() -> None:
    manager = WorkerManager(_settings())
    rgb_fake = FakeWorker(is_running=True, source_url="rtsp://rgb/stream", idle_seconds=1.0)
    thermal_fake = FakeWorker(is_running=True, source_url="rtsp://thermal/stream", idle_seconds=1.0)
    manager._workers["CAM-DUAL-01:rgb"] = rgb_fake
    manager._workers["CAM-DUAL-01:thermal"] = thermal_fake
    manager._fetch_camera_configs = AsyncMock(return_value=[])  # camera deleted

    await manager._reconcile()

    assert rgb_fake.stop_called is True
    assert thermal_fake.stop_called is True
    assert manager._workers == {}
    await manager.stop()
