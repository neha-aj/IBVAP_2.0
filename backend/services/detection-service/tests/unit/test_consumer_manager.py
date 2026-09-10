"""Covers M11's extension to ConsumerManager's reconcile loop -- a 'dual'
camera must get exactly two FrameConsumers sharing one FusionMerger, while
every existing single-stream camera type keeps its original
one-consumer-per-camera_id behavior unchanged."""

from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.streaming.consumer_manager import ConsumerManager


def _settings(**overrides) -> Settings:
    defaults = {
        "postgres_user": "u", "postgres_password": "p", "postgres_db": "d", "jwt_secret": "s",
        "internal_service_token": "t",
    }
    defaults.update(overrides)
    return Settings(**defaults)


class FakeConsumer:
    def __init__(self, *, is_running: bool = True) -> None:
        self.is_running = is_running
        self.stop_called = False

    async def stop(self) -> None:
        self.stop_called = True


def _config(camera_id: str = "CAM-01", camera_type: str = "file") -> dict:
    return {"id": camera_id, "type": camera_type}


@pytest.mark.asyncio
async def test_single_stream_camera_unaffected_by_dual_support() -> None:
    manager = ConsumerManager(_settings(), engine=object())
    fake = FakeConsumer(is_running=True)
    manager._consumers["CAM-01"] = fake
    manager._fetch_camera_configs = AsyncMock(return_value=[_config()])

    await manager._reconcile()

    assert fake.stop_called is False
    assert manager._consumers["CAM-01"] is fake
    await manager.stop()


@pytest.mark.asyncio
async def test_dead_single_stream_consumer_is_restarted() -> None:
    manager = ConsumerManager(_settings(), engine=object())
    fake = FakeConsumer(is_running=False)
    manager._consumers["CAM-01"] = fake
    manager._fetch_camera_configs = AsyncMock(return_value=[_config()])

    await manager._reconcile()

    assert fake.stop_called is True
    assert manager._consumers["CAM-01"] is not fake
    await manager.stop()


@pytest.mark.asyncio
async def test_dual_camera_gets_two_consumers_under_compound_keys() -> None:
    manager = ConsumerManager(_settings(), engine=object())
    manager._fetch_camera_configs = AsyncMock(return_value=[_config("CAM-DUAL-01", "dual")])

    await manager._reconcile()

    assert set(manager._consumers) == {"CAM-DUAL-01:rgb", "CAM-DUAL-01:thermal"}
    await manager.stop()


@pytest.mark.asyncio
async def test_healthy_dual_pair_is_left_alone() -> None:
    manager = ConsumerManager(_settings(), engine=object())
    rgb_fake = FakeConsumer(is_running=True)
    thermal_fake = FakeConsumer(is_running=True)
    manager._consumers["CAM-DUAL-01:rgb"] = rgb_fake
    manager._consumers["CAM-DUAL-01:thermal"] = thermal_fake
    manager._fetch_camera_configs = AsyncMock(return_value=[_config("CAM-DUAL-01", "dual")])

    await manager._reconcile()

    assert rgb_fake.stop_called is False
    assert thermal_fake.stop_called is False
    assert manager._consumers["CAM-DUAL-01:rgb"] is rgb_fake
    assert manager._consumers["CAM-DUAL-01:thermal"] is thermal_fake
    await manager.stop()


@pytest.mark.asyncio
async def test_dual_pair_both_recreated_if_either_half_dies() -> None:
    """If just the thermal half dies, both halves get recreated together
    (against a fresh FusionMerger) rather than leaving a lone RGB consumer
    feeding a merger nothing will ever pair with again."""
    manager = ConsumerManager(_settings(), engine=object())
    rgb_fake = FakeConsumer(is_running=True)
    thermal_fake = FakeConsumer(is_running=False)
    manager._consumers["CAM-DUAL-01:rgb"] = rgb_fake
    manager._consumers["CAM-DUAL-01:thermal"] = thermal_fake
    manager._fetch_camera_configs = AsyncMock(return_value=[_config("CAM-DUAL-01", "dual")])

    await manager._reconcile()

    assert rgb_fake.stop_called is True
    assert thermal_fake.stop_called is True
    assert manager._consumers["CAM-DUAL-01:rgb"] is not rgb_fake
    assert manager._consumers["CAM-DUAL-01:thermal"] is not thermal_fake
    await manager.stop()


@pytest.mark.asyncio
async def test_dual_pair_both_stopped_when_camera_removed() -> None:
    manager = ConsumerManager(_settings(), engine=object())
    rgb_fake = FakeConsumer(is_running=True)
    thermal_fake = FakeConsumer(is_running=True)
    manager._consumers["CAM-DUAL-01:rgb"] = rgb_fake
    manager._consumers["CAM-DUAL-01:thermal"] = thermal_fake
    manager._fetch_camera_configs = AsyncMock(return_value=[])  # camera deleted

    await manager._reconcile()

    assert rgb_fake.stop_called is True
    assert thermal_fake.stop_called is True
    assert manager._consumers == {}
    await manager.stop()
