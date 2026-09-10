import numpy as np
import pytest

from app.core.config import Settings
from app.services.fire_smoke_service import FireSmokeService


def _settings(**overrides) -> Settings:
    defaults = {
        "postgres_user": "u", "postgres_password": "p", "postgres_db": "d", "jwt_secret": "s",
        "internal_service_token": "t", "fire_min_area_fraction": 0.1, "smoke_min_area_fraction": 0.1,
        "alert_cooldown_seconds": 60.0,
    }
    defaults.update(overrides)
    return Settings(**defaults)


class FakeEventClient:
    def __init__(self) -> None:
        self.reported: list[tuple[str, str, float]] = []

    async def report_detection(self, *, camera_id: str, event_type: str, coverage: float) -> None:
        self.reported.append((camera_id, event_type, coverage))


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.value = start

    def __call__(self) -> float:
        return self.value


def _frame() -> np.ndarray:
    return np.zeros((10, 10, 3), dtype=np.uint8)


@pytest.mark.asyncio
async def test_process_frame_reports_fire_above_threshold() -> None:
    client = FakeEventClient()
    service = FireSmokeService(
        settings=_settings(), event_client=client, fire_score=lambda f: 0.5, smoke_score=lambda f: 0.0,
    )

    result = await service.process_frame("CAM-01", _frame())

    assert result == "Fire Detected"
    assert client.reported == [("CAM-01", "Fire Detected", 0.5)]


@pytest.mark.asyncio
async def test_process_frame_reports_smoke_above_threshold() -> None:
    client = FakeEventClient()
    service = FireSmokeService(
        settings=_settings(), event_client=client, fire_score=lambda f: 0.0, smoke_score=lambda f: 0.3,
    )

    result = await service.process_frame("CAM-01", _frame())

    assert result == "Smoke Detected"
    assert client.reported == [("CAM-01", "Smoke Detected", 0.3)]


@pytest.mark.asyncio
async def test_process_frame_none_below_both_thresholds() -> None:
    client = FakeEventClient()
    service = FireSmokeService(
        settings=_settings(), event_client=client, fire_score=lambda f: 0.02, smoke_score=lambda f: 0.02,
    )

    assert await service.process_frame("CAM-01", _frame()) is None
    assert client.reported == []


@pytest.mark.asyncio
async def test_first_detection_fires_immediately_no_debounce() -> None:
    """doc09 §2.6: fire/smoke detection bypasses any per-alert debounce --
    the very first qualifying frame must alert with zero delay."""
    client = FakeEventClient()
    clock = FakeClock(start=1000.0)
    service = FireSmokeService(
        settings=_settings(), event_client=client, fire_score=lambda f: 0.5, smoke_score=lambda f: 0.0, now=clock,
    )

    result = await service.process_frame("CAM-01", _frame())

    assert result == "Fire Detected"
    assert len(client.reported) == 1


@pytest.mark.asyncio
async def test_repeat_detection_within_cooldown_is_suppressed() -> None:
    client = FakeEventClient()
    clock = FakeClock(start=1000.0)
    service = FireSmokeService(
        settings=_settings(alert_cooldown_seconds=60.0), event_client=client,
        fire_score=lambda f: 0.5, smoke_score=lambda f: 0.0, now=clock,
    )

    await service.process_frame("CAM-01", _frame())
    clock.value += 10.0  # still within the 60s cooldown
    result = await service.process_frame("CAM-01", _frame())

    assert result is None
    assert len(client.reported) == 1


@pytest.mark.asyncio
async def test_detection_after_cooldown_expires_fires_again() -> None:
    client = FakeEventClient()
    clock = FakeClock(start=1000.0)
    service = FireSmokeService(
        settings=_settings(alert_cooldown_seconds=60.0), event_client=client,
        fire_score=lambda f: 0.5, smoke_score=lambda f: 0.0, now=clock,
    )

    await service.process_frame("CAM-01", _frame())
    clock.value += 61.0  # past the cooldown window
    result = await service.process_frame("CAM-01", _frame())

    assert result == "Fire Detected"
    assert len(client.reported) == 2


@pytest.mark.asyncio
async def test_different_cameras_have_independent_cooldowns() -> None:
    client = FakeEventClient()
    clock = FakeClock(start=1000.0)
    service = FireSmokeService(
        settings=_settings(alert_cooldown_seconds=60.0), event_client=client,
        fire_score=lambda f: 0.5, smoke_score=lambda f: 0.0, now=clock,
    )

    await service.process_frame("CAM-01", _frame())
    result = await service.process_frame("CAM-02", _frame())

    assert result == "Fire Detected"
    assert len(client.reported) == 2
