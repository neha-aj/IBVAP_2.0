import cv2
import numpy as np
import pytest

from app.core.config import Settings
from app.models.plate_read import PlateRead
from app.models.watchlist import WatchlistEntry
from app.schemas.internal import BoundingBox, Detection
from app.services.plate_service import PlateService


def _settings(**overrides) -> Settings:
    defaults = {
        "postgres_user": "u", "postgres_password": "p", "postgres_db": "d", "jwt_secret": "s",
        "internal_service_token": "t", "plate_format_regex": r"^[A-Z0-9]{5,10}$", "min_ocr_confidence": 40.0,
        "min_plate_crop_height_px": 64,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _jpeg_frame(height: int = 200, width: int = 300) -> bytes:
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", frame)
    assert ok
    return encoded.tobytes()


def _vehicle_detection(camera_id: str = "CAM-01") -> Detection:
    return Detection(
        id="d1", cameraId=camera_id, type="vehicle", confidence=0.9, trackId="7",
        bbox=BoundingBox(x=10.0, y=10.0, width=50.0, height=30.0),
    )


class FakeCameraClient:
    def __init__(self, frame_bytes: bytes | None) -> None:
        self.frame_bytes = frame_bytes

    async def get_current_frame(self, camera_id: str) -> bytes | None:
        return self.frame_bytes


class FakeMediaClient:
    def __init__(self) -> None:
        self.calls = []

    async def store_plate_crop(self, *, camera_id: str, jpeg_bytes: bytes):
        self.calls.append((camera_id, jpeg_bytes))


class FakeEventClient:
    def __init__(self) -> None:
        self.reports = []

    async def report_plate_read(self, *, camera_id, plate_text, confidence, watchlist_match):
        self.reports.append((camera_id, plate_text, confidence, watchlist_match))


class FakeWatchlistRepo:
    def __init__(self, entries: dict[str, WatchlistEntry] | None = None) -> None:
        self.entries = entries or {}

    async def get_by_plate(self, plate_text: str) -> WatchlistEntry | None:
        return self.entries.get(plate_text)


class FakePlateReadRepo:
    def __init__(self) -> None:
        self.created: list[PlateRead] = []

    async def create(self, plate_read: PlateRead) -> PlateRead:
        self.created.append(plate_read)
        return plate_read


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.value = start

    def __call__(self) -> float:
        return self.value


def _build_service(*, frame_bytes, detect_plate, read_plate, watchlist_entries=None, settings=None, now=None):
    return PlateService(
        settings=settings or _settings(),
        plate_repo=FakePlateReadRepo(),
        watchlist_repo=FakeWatchlistRepo(watchlist_entries),
        camera_client=FakeCameraClient(frame_bytes),
        media_client=FakeMediaClient(),
        event_client=FakeEventClient(),
        detect_plate=detect_plate,
        read_plate=read_plate,
        **({"now": now} if now is not None else {}),
    )


@pytest.mark.asyncio
async def test_process_vehicle_detection_happy_path_persists_and_reports() -> None:
    service = _build_service(
        frame_bytes=_jpeg_frame(),
        detect_plate=lambda gray: (0, 0, 10, 5),
        read_plate=lambda crop: ("AB123CD", 88.0),
    )

    result = await service.process_vehicle_detection(_vehicle_detection())

    assert result is not None
    assert result.plate_text == "AB123CD"
    assert result.watchlist_match is False
    assert service._event_client.reports == [("CAM-01", "AB123CD", 88.0, False)]


@pytest.mark.asyncio
async def test_process_vehicle_detection_ignores_non_vehicle() -> None:
    service = _build_service(
        frame_bytes=_jpeg_frame(), detect_plate=lambda g: (0, 0, 1, 1), read_plate=lambda c: ("X", 90.0),
    )
    non_vehicle = Detection(
        id="d2", cameraId="CAM-01", type="person", confidence=0.9,
        bbox=BoundingBox(x=0, y=0, width=10, height=10),
    )
    assert await service.process_vehicle_detection(non_vehicle) is None


@pytest.mark.asyncio
async def test_process_vehicle_detection_none_when_no_current_frame() -> None:
    service = _build_service(frame_bytes=None, detect_plate=lambda g: (0, 0, 1, 1), read_plate=lambda c: ("X", 90.0))
    assert await service.process_vehicle_detection(_vehicle_detection()) is None


@pytest.mark.asyncio
async def test_process_vehicle_detection_none_when_no_plate_region_found() -> None:
    service = _build_service(frame_bytes=_jpeg_frame(), detect_plate=lambda g: None, read_plate=lambda c: ("X", 90.0))
    assert await service.process_vehicle_detection(_vehicle_detection()) is None


@pytest.mark.asyncio
async def test_process_vehicle_detection_none_when_ocr_fails() -> None:
    service = _build_service(frame_bytes=_jpeg_frame(), detect_plate=lambda g: (0, 0, 10, 5), read_plate=lambda c: None)
    assert await service.process_vehicle_detection(_vehicle_detection()) is None


@pytest.mark.asyncio
async def test_process_vehicle_detection_none_when_plate_format_invalid() -> None:
    service = _build_service(
        frame_bytes=_jpeg_frame(), detect_plate=lambda g: (0, 0, 10, 5), read_plate=lambda c: ("!!", 90.0),
    )
    assert await service.process_vehicle_detection(_vehicle_detection()) is None


@pytest.mark.asyncio
async def test_process_vehicle_detection_flags_watchlist_match() -> None:
    watchlist_entries = {"AB123CD": WatchlistEntry(plate_text="AB123CD", reason="stolen")}
    service = _build_service(
        frame_bytes=_jpeg_frame(), detect_plate=lambda g: (0, 0, 10, 5), read_plate=lambda c: ("AB123CD", 90.0),
        watchlist_entries=watchlist_entries,
    )

    result = await service.process_vehicle_detection(_vehicle_detection())

    assert result.watchlist_match is True
    assert service._event_client.reports == [("CAM-01", "AB123CD", 90.0, True)]


@pytest.mark.asyncio
async def test_repeat_plate_within_cooldown_is_not_repersisted() -> None:
    """A vehicle sitting in frame for several seconds must not flood the
    License Plates page with a duplicate row per detection message."""
    clock = FakeClock(start=1000.0)
    service = _build_service(
        frame_bytes=_jpeg_frame(), detect_plate=lambda g: (0, 0, 10, 5), read_plate=lambda c: ("AB123CD", 90.0),
        settings=_settings(plate_read_cooldown_seconds=30.0), now=clock,
    )

    first = await service.process_vehicle_detection(_vehicle_detection())
    clock.value += 5.0  # still within the 30s cooldown
    second = await service.process_vehicle_detection(_vehicle_detection())

    assert first is not None
    assert second is None
    assert len(service._plate_repo.created) == 1
    assert len(service._event_client.reports) == 1


@pytest.mark.asyncio
async def test_repeat_plate_after_cooldown_expires_is_repersisted() -> None:
    clock = FakeClock(start=1000.0)
    service = _build_service(
        frame_bytes=_jpeg_frame(), detect_plate=lambda g: (0, 0, 10, 5), read_plate=lambda c: ("AB123CD", 90.0),
        settings=_settings(plate_read_cooldown_seconds=30.0), now=clock,
    )

    await service.process_vehicle_detection(_vehicle_detection())
    clock.value += 31.0  # past the cooldown window
    result = await service.process_vehicle_detection(_vehicle_detection())

    assert result is not None
    assert len(service._plate_repo.created) == 2


@pytest.mark.asyncio
async def test_different_plates_on_same_camera_are_never_cooled_down() -> None:
    reads = iter([("AB123CD", 90.0), ("XY987ZZ", 91.0)])
    clock = FakeClock(start=1000.0)
    service = _build_service(
        frame_bytes=_jpeg_frame(), detect_plate=lambda g: (0, 0, 10, 5),
        read_plate=lambda c: next(reads), now=clock,
    )

    first = await service.process_vehicle_detection(_vehicle_detection())
    second = await service.process_vehicle_detection(_vehicle_detection())

    assert first is not None and second is not None
    assert len(service._plate_repo.created) == 2


@pytest.mark.asyncio
async def test_same_plate_on_different_cameras_is_never_cooled_down() -> None:
    clock = FakeClock(start=1000.0)
    service = _build_service(
        frame_bytes=_jpeg_frame(), detect_plate=lambda g: (0, 0, 10, 5), read_plate=lambda c: ("AB123CD", 90.0),
        now=clock,
    )

    first = await service.process_vehicle_detection(_vehicle_detection(camera_id="CAM-01"))
    second = await service.process_vehicle_detection(_vehicle_detection(camera_id="CAM-02"))

    assert first is not None and second is not None
    assert len(service._plate_repo.created) == 2
