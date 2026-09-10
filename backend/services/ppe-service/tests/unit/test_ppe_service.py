import cv2
import numpy as np
import pytest

from app.core.config import Settings
from app.schemas.internal import BoundingBox, Point, TrackEvent, Zone
from app.services.ppe_service import PPEService


def _settings(**overrides) -> Settings:
    defaults = {
        "postgres_user": "u", "postgres_password": "p", "postgres_db": "d", "jwt_secret": "s",
        "internal_service_token": "t", "person_crop_min_size_px": 10,
        "violation_debounce_updates": 2, "escalation_violation_updates": 4,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _jpeg_frame(height: int = 200, width: int = 300) -> bytes:
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", frame)
    assert ok
    return encoded.tobytes()


_REQUIRES_PPE_ZONE = Zone(
    id="z1", name="Construction Area", zoneType="restricted", requiresPpe=True,
    polygon=[Point(x=0, y=0), Point(x=100, y=0), Point(x=100, y=100), Point(x=0, y=100)],
)
_NO_PPE_ZONE = Zone(
    id="z2", name="Office", zoneType="general", requiresPpe=False,
    polygon=[Point(x=0, y=0), Point(x=100, y=0), Point(x=100, y=100), Point(x=0, y=100)],
)


def _track_event(
    event: str = "track.started", camera_id: str = "CAM-01", track_id: str = "7", object_type: str = "person",
) -> TrackEvent:
    bbox = None if event == "track.lost" else BoundingBox(x=10.0, y=10.0, width=50.0, height=50.0)
    return TrackEvent(event=event, trackId=track_id, cameraId=camera_id, objectType=object_type, bbox=bbox)


class FakeCameraClient:
    def __init__(self, *, frame_bytes: bytes | None, zones: list[Zone]) -> None:
        self.frame_bytes = frame_bytes
        self.zones = zones

    async def get_current_frame(self, camera_id: str) -> bytes | None:
        return self.frame_bytes

    async def get_zones(self, camera_id: str) -> list[Zone]:
        return self.zones


class FakeEventClient:
    def __init__(self) -> None:
        self.reported: list[tuple[str, list[str], str]] = []

    async def report_violation(self, *, camera_id: str, missing_items: list[str], severity: str) -> None:
        self.reported.append((camera_id, missing_items, severity))


def _always_missing_vest(crop, *, vest_min_coverage_fraction: float) -> list[str]:
    return ["vest"]


def _always_compliant(crop, *, vest_min_coverage_fraction: float) -> list[str]:
    return []


@pytest.mark.asyncio
async def test_ignores_non_person_object_types() -> None:
    camera_client = FakeCameraClient(frame_bytes=_jpeg_frame(), zones=[_REQUIRES_PPE_ZONE])
    event_client = FakeEventClient()
    service = PPEService(
        settings=_settings(), camera_client=camera_client, event_client=event_client, classify_fn=_always_missing_vest,
    )

    result = await service.process_track_event(_track_event(object_type="vehicle"))

    assert result is None
    assert event_client.reported == []


@pytest.mark.asyncio
async def test_no_violation_outside_a_requires_ppe_zone() -> None:
    camera_client = FakeCameraClient(frame_bytes=_jpeg_frame(), zones=[_NO_PPE_ZONE])
    event_client = FakeEventClient()
    service = PPEService(
        settings=_settings(), camera_client=camera_client, event_client=event_client, classify_fn=_always_missing_vest,
    )

    result = await service.process_track_event(_track_event())

    assert result is None
    assert event_client.reported == []


@pytest.mark.asyncio
async def test_compliant_person_never_fires() -> None:
    camera_client = FakeCameraClient(frame_bytes=_jpeg_frame(), zones=[_REQUIRES_PPE_ZONE])
    event_client = FakeEventClient()
    service = PPEService(
        settings=_settings(), camera_client=camera_client, event_client=event_client, classify_fn=_always_compliant,
    )

    for _ in range(5):
        result = await service.process_track_event(_track_event())
        assert result is None

    assert event_client.reported == []


@pytest.mark.asyncio
async def test_violation_debounced_then_fires_at_medium_severity() -> None:
    """violation_debounce_updates=2 -- the first missing-PPE read must not
    fire alone (a brief pass-through shouldn't alert)."""
    camera_client = FakeCameraClient(frame_bytes=_jpeg_frame(), zones=[_REQUIRES_PPE_ZONE])
    event_client = FakeEventClient()
    service = PPEService(
        settings=_settings(), camera_client=camera_client, event_client=event_client, classify_fn=_always_missing_vest,
    )

    first = await service.process_track_event(_track_event())
    assert first is None
    assert event_client.reported == []

    second = await service.process_track_event(_track_event())
    assert second == ["vest"]
    assert event_client.reported == [("CAM-01", ["vest"], "medium")]


@pytest.mark.asyncio
async def test_repeated_violation_escalates_to_high_once() -> None:
    """escalation_violation_updates=4 -- staying in violation long enough
    past the initial medium alert fires a second, high-severity event, and
    only once (not every subsequent update)."""
    camera_client = FakeCameraClient(frame_bytes=_jpeg_frame(), zones=[_REQUIRES_PPE_ZONE])
    event_client = FakeEventClient()
    service = PPEService(
        settings=_settings(), camera_client=camera_client, event_client=event_client, classify_fn=_always_missing_vest,
    )

    for _ in range(3):
        await service.process_track_event(_track_event())
    assert event_client.reported == [("CAM-01", ["vest"], "medium")]

    result = await service.process_track_event(_track_event())
    assert result == ["vest"]
    assert event_client.reported == [
        ("CAM-01", ["vest"], "medium"),
        ("CAM-01", ["vest"], "high"),
    ]

    # A further update stays in violation but must not re-fire high again.
    result = await service.process_track_event(_track_event())
    assert result is None
    assert len(event_client.reported) == 2


@pytest.mark.asyncio
async def test_coming_back_into_compliance_resets_the_streak() -> None:
    camera_client = FakeCameraClient(frame_bytes=_jpeg_frame(), zones=[_REQUIRES_PPE_ZONE])
    event_client = FakeEventClient()
    classify_calls = {"missing": True}

    def toggling_classify(crop, *, vest_min_coverage_fraction: float) -> list[str]:
        return ["vest"] if classify_calls["missing"] else []

    service = PPEService(
        settings=_settings(), camera_client=camera_client, event_client=event_client, classify_fn=toggling_classify,
    )

    await service.process_track_event(_track_event())
    await service.process_track_event(_track_event())
    assert len(event_client.reported) == 1  # first medium alert fired

    classify_calls["missing"] = False
    await service.process_track_event(_track_event())  # comes into compliance -- resets streak

    classify_calls["missing"] = True
    first_after_reset = await service.process_track_event(_track_event())
    assert first_after_reset is None  # debounced again, same as a fresh episode
    second_after_reset = await service.process_track_event(_track_event())
    assert second_after_reset == ["vest"]
    assert len(event_client.reported) == 2  # a fresh medium alert for the new episode


@pytest.mark.asyncio
async def test_track_lost_clears_state() -> None:
    camera_client = FakeCameraClient(frame_bytes=_jpeg_frame(), zones=[_REQUIRES_PPE_ZONE])
    event_client = FakeEventClient()
    service = PPEService(
        settings=_settings(), camera_client=camera_client, event_client=event_client, classify_fn=_always_missing_vest,
    )

    await service.process_track_event(_track_event())
    result = await service.process_track_event(_track_event(event="track.lost"))
    assert result is None

    # A fresh track.started for the same track_id starts a new streak.
    first = await service.process_track_event(_track_event())
    assert first is None
    assert event_client.reported == []


@pytest.mark.asyncio
async def test_crop_too_small_is_skipped() -> None:
    camera_client = FakeCameraClient(frame_bytes=_jpeg_frame(), zones=[_REQUIRES_PPE_ZONE])
    event_client = FakeEventClient()
    service = PPEService(
        settings=_settings(person_crop_min_size_px=1000), camera_client=camera_client,
        event_client=event_client, classify_fn=_always_missing_vest,
    )

    result = await service.process_track_event(_track_event())

    assert result is None
    assert event_client.reported == []


@pytest.mark.asyncio
async def test_missing_frame_is_skipped_without_crashing() -> None:
    camera_client = FakeCameraClient(frame_bytes=None, zones=[_REQUIRES_PPE_ZONE])
    event_client = FakeEventClient()
    service = PPEService(
        settings=_settings(), camera_client=camera_client, event_client=event_client, classify_fn=_always_missing_vest,
    )

    result = await service.process_track_event(_track_event())

    assert result is None
    assert event_client.reported == []
