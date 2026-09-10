import numpy as np
import pytest

from app.core.config import Settings
from app.services.tamper_service import TamperService


def _settings(**overrides) -> Settings:
    defaults = {
        "postgres_user": "u", "postgres_password": "p", "postgres_db": "d", "jwt_secret": "s",
        "internal_service_token": "t", "debounce_frames": 3,
    }
    defaults.update(overrides)
    return Settings(**defaults)


class FakeEventClient:
    def __init__(self) -> None:
        self.reported: list[tuple[str, str]] = []

    async def report_tamper(self, *, camera_id: str, category: str) -> None:
        self.reported.append((camera_id, category))


class FakeBaseline:
    """`compare()` returns a placeholder reading (its content is irrelevant
    -- `classify_fn` is scripted separately below to control what
    TamperService actually sees each call, so tests don't need real image
    processing)."""

    def __init__(self) -> None:
        self.update_calls = 0

    def compare(self, frame):
        return None

    def update(self, frame):
        self.update_calls += 1


def _scripted_classify(categories: list[str | None]):
    it = iter(categories)

    def classify_fn(reading, **kwargs):
        return next(it)

    return classify_fn


def _frame() -> np.ndarray:
    return np.zeros((10, 10, 3), dtype=np.uint8)


@pytest.mark.asyncio
async def test_single_deviation_below_debounce_does_not_alert() -> None:
    client = FakeEventClient()
    baseline = FakeBaseline()
    service = TamperService(
        camera_id="CAM-01", settings=_settings(debounce_frames=3), event_client=client,
        baseline=baseline, classify_fn=_scripted_classify(["covered"]),
    )

    result = await service.process_frame(_frame())

    assert result is None
    assert client.reported == []


@pytest.mark.asyncio
async def test_sustained_deviation_across_debounce_window_alerts() -> None:
    """doc09 §2.5: "require the deviation to persist across several
    consecutive samples" -- momentary flicker (1-2 frames) must not fire;
    a sustained run reaching the debounce count must."""
    client = FakeEventClient()
    baseline = FakeBaseline()
    service = TamperService(
        camera_id="CAM-01", settings=_settings(debounce_frames=3), event_client=client,
        baseline=baseline, classify_fn=_scripted_classify(["covered", "covered", "covered"]),
    )

    results = [await service.process_frame(_frame()) for _ in range(3)]

    assert results == [None, None, "covered"]
    assert client.reported == [("CAM-01", "covered")]


@pytest.mark.asyncio
async def test_momentary_deviation_resets_streak_and_never_alerts() -> None:
    client = FakeEventClient()
    baseline = FakeBaseline()
    service = TamperService(
        camera_id="CAM-01", settings=_settings(debounce_frames=3), event_client=client,
        baseline=baseline, classify_fn=_scripted_classify(["covered", "covered", None, "covered", "covered"]),
    )

    results = [await service.process_frame(_frame()) for _ in range(5)]

    assert results == [None, None, None, None, None]  # streak reset by the None in the middle
    assert client.reported == []


@pytest.mark.asyncio
async def test_does_not_repeat_alert_while_still_tampered() -> None:
    client = FakeEventClient()
    baseline = FakeBaseline()
    service = TamperService(
        camera_id="CAM-01", settings=_settings(debounce_frames=2), event_client=client,
        baseline=baseline, classify_fn=_scripted_classify(["covered", "covered", "covered", "covered"]),
    )

    results = [await service.process_frame(_frame()) for _ in range(4)]

    assert results == [None, "covered", None, None]  # only fires once for the whole episode
    assert len(client.reported) == 1


@pytest.mark.asyncio
async def test_fires_again_after_returning_to_normal_and_tampering_again() -> None:
    client = FakeEventClient()
    baseline = FakeBaseline()
    service = TamperService(
        camera_id="CAM-01", settings=_settings(debounce_frames=2), event_client=client,
        baseline=baseline,
        classify_fn=_scripted_classify(["covered", "covered", None, "covered", "covered"]),
    )

    results = [await service.process_frame(_frame()) for _ in range(5)]

    assert results == [None, "covered", None, None, "covered"]
    assert len(client.reported) == 2


@pytest.mark.asyncio
async def test_baseline_only_updates_on_normal_frames() -> None:
    """A tampered frame must never be absorbed into the rolling baseline
    as "the new normal" -- update() should only be called while
    classify_fn reports no deviation."""
    client = FakeEventClient()
    baseline = FakeBaseline()
    service = TamperService(
        camera_id="CAM-01", settings=_settings(debounce_frames=2), event_client=client,
        baseline=baseline, classify_fn=_scripted_classify([None, "covered", "covered", None]),
    )

    for _ in range(4):
        await service.process_frame(_frame())

    assert baseline.update_calls == 2  # only the two `None` (normal) frames
