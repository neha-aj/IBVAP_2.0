"""Direction Observed events are high-volume informational samples; saving a
snapshot image for each was what filled the disk. They must skip snapshot
capture -- and every other event type must still get one."""

from types import SimpleNamespace

import pytest

import app.streaming.pubsub_publisher as pubsub
from app.core.config import Settings
from app.rules.engine import EventDraft
from app.streaming.pubsub_publisher import PubSubPublisher


class _CameraClient:
    async def get_camera_info(self, camera_id):
        return SimpleNamespace(name="Gate", location="North")


class _SnapshotClient:
    def __init__(self) -> None:
        self.captured_for: list[str] = []

    async def capture(self, *, camera_id, event_id):
        self.captured_for.append(event_id)
        return SimpleNamespace(id="snap-1", url="/media/snapshots/x.jpg")


class _EventRepo:
    created: list = []
    snapshots_set: list = []

    def __init__(self, session) -> None:
        pass

    async def create(self, event):
        event.id = f"evt-{len(_EventRepo.created)}"
        _EventRepo.created.append(event)
        return event

    async def set_snapshot(self, event, *, snapshot_id, snapshot_url):
        _EventRepo.snapshots_set.append(event.id)
        event.snapshot_id = snapshot_id
        return event


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    _EventRepo.created = []
    _EventRepo.snapshots_set = []
    monkeypatch.setattr(pubsub, "EventRepository", _EventRepo)

    async def fake_publish(*a, **k):
        return None

    monkeypatch.setattr(pubsub, "publish_event", fake_publish)
    # The published payload isn't what's under test.
    monkeypatch.setattr(
        pubsub, "to_event_read", lambda event: SimpleNamespace(model_dump=lambda **k: {"id": str(event.id)})
    )


def _publisher(snapshots: _SnapshotClient, settings: Settings | None = None) -> PubSubPublisher:
    return PubSubPublisher(
        redis_client=None, camera_client=_CameraClient(), snapshot_client=snapshots,
        recording_client=None, session_factory=None, settings=settings,
    )


def _draft(event_type: str, severity: str = "low", requires_review: bool = False) -> EventDraft:
    return EventDraft(camera_id="CAM-1", event_type=event_type, object_type="person", severity=severity,
                      description=None, requires_review=requires_review)


def _settings(**overrides) -> Settings:
    return Settings(postgres_user="u", postgres_password="p", postgres_db="d", jwt_secret="s",
                    internal_service_token="t", **overrides)


@pytest.mark.asyncio
async def test_direction_observed_gets_no_snapshot() -> None:
    snapshots = _SnapshotClient()

    await _publisher(snapshots).persist_and_publish(None, _draft("Direction Observed"))

    assert snapshots.captured_for == []  # no capture attempt at all, not even a failed one
    assert len(_EventRepo.created) == 1  # the event itself is still stored
    assert _EventRepo.snapshots_set == []


@pytest.mark.asyncio
async def test_other_event_types_still_get_a_snapshot() -> None:
    snapshots = _SnapshotClient()
    publisher = _publisher(snapshots)

    for event_type in ("Loitering Detected", "Fire Detected", "Fighting Detected", "Plate Read"):
        await publisher.persist_and_publish(None, _draft(event_type))

    assert len(snapshots.captured_for) == 4
    assert len(_EventRepo.snapshots_set) == 4


@pytest.mark.asyncio
async def test_skip_list_comes_from_settings_when_given() -> None:
    snapshots = _SnapshotClient()
    settings = _settings(snapshot_skip_event_types=("Person Count Threshold Exceeded",))
    publisher = _publisher(snapshots, settings)

    await publisher.persist_and_publish(None, _draft("Person Count Threshold Exceeded"))
    await publisher.persist_and_publish(None, _draft("Direction Observed"))  # no longer skipped by this config

    assert len(snapshots.captured_for) == 1


def test_default_setting_skips_only_direction_observed() -> None:
    assert _settings().snapshot_skip_event_types == ("Direction Observed",)
