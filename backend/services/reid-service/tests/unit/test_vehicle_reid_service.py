"""Phase 2 M17 (Vehicle Re-ID). Mirrors test_reid_service.py's fixtures but
exercises `ReidService` configured for `object_type="vehicle"` /
`VehicleEmbedding` -- the point of these tests is confirming the
parameterization actually switches behavior (filters `vehicle` not
`person`, persists into a `VehicleEmbedding`), not re-testing orchestration
logic already covered for the person case."""

import datetime as dt

import cv2
import numpy as np
import pytest

from app.core.config import Settings
from app.models.vehicle_embedding import VehicleEmbedding
from app.schemas.internal import BoundingBox, TrackEvent
from app.services.reid_service import ReidService


def _settings(**overrides) -> Settings:
    defaults = {
        "postgres_user": "u", "postgres_password": "p", "postgres_db": "d", "jwt_secret": "s",
        "internal_service_token": "t", "vehicle_crop_min_size_px": 10, "similarity_threshold": 0.6,
        "max_search_results": 20,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _jpeg_frame(height: int = 200, width: int = 300) -> bytes:
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", frame)
    assert ok
    return encoded.tobytes()


def _track_event(object_type: str = "vehicle", event: str = "track.started") -> TrackEvent:
    bbox = None if event == "track.lost" else BoundingBox(x=10.0, y=10.0, width=50.0, height=50.0)
    return TrackEvent(event=event, trackId="7", cameraId="CAM-01", objectType=object_type, bbox=bbox)


class FakeCameraClient:
    def __init__(self, frame_bytes: bytes | None) -> None:
        self.frame_bytes = frame_bytes

    async def get_current_frame(self, camera_id: str) -> bytes | None:
        return self.frame_bytes

    async def get_camera_info(self, camera_id: str):
        return None


class FakeMediaClient:
    async def store_person_crop(self, *, camera_id: str, jpeg_bytes: bytes):
        return None


class FakeEmbeddingRepo:
    def __init__(self) -> None:
        self.created: list[VehicleEmbedding] = []
        self.search_results: list[tuple[VehicleEmbedding, float]] = []

    async def get_latest_by_track(self, *, camera_id: str, track_id: str):
        return None

    async def create(self, embedding_row: VehicleEmbedding) -> VehicleEmbedding:
        embedding_row.created_at = dt.datetime.now(dt.UTC)
        self.created.append(embedding_row)
        return embedding_row

    async def search_similar(self, query_embedding, *, exclude_track_id, limit):
        return self.search_results


def _build_service(*, frame_bytes, embed, settings=None):
    repo = FakeEmbeddingRepo()
    service = ReidService(
        settings=settings or _settings(),
        embedding_repo=repo,
        camera_client=FakeCameraClient(frame_bytes),
        media_client=FakeMediaClient(),
        embed=embed,
        object_type="vehicle",
        embedding_factory=VehicleEmbedding,
        crop_min_size=(settings or _settings()).vehicle_crop_min_size_px,
    )
    return service, repo


@pytest.mark.asyncio
async def test_process_track_event_extracts_and_persists_vehicle_embedding() -> None:
    service, repo = _build_service(frame_bytes=_jpeg_frame(), embed=lambda crop: [0.4, 0.5])

    result = await service.process_track_event(_track_event())

    assert result is not None
    assert isinstance(result, VehicleEmbedding)
    assert result.track_id == "7"
    assert result.embedding == [0.4, 0.5]
    assert len(repo.created) == 1


@pytest.mark.asyncio
async def test_process_track_event_skips_person() -> None:
    """The vehicle-configured service must ignore person tracks -- the
    complement of test_reid_service.py's "skips_non_person" case, and the
    actual behavior that lets one TrackConsumer safely run a message
    through both services (see reconcile_manager.py)."""
    service, repo = _build_service(frame_bytes=_jpeg_frame(), embed=lambda crop: [0.1])
    assert await service.process_track_event(_track_event(object_type="person")) is None
    assert repo.created == []


@pytest.mark.asyncio
async def test_process_track_event_none_for_too_small_crop() -> None:
    service, repo = _build_service(
        frame_bytes=_jpeg_frame(), embed=lambda crop: [0.1], settings=_settings(vehicle_crop_min_size_px=1000),
    )
    assert await service.process_track_event(_track_event()) is None
    assert repo.created == []


@pytest.mark.asyncio
async def test_search_by_image_embeds_and_searches_vehicle_index() -> None:
    match_row = VehicleEmbedding(track_id="9", camera_id="CAM-01", embedding=[0.1])
    match_row.created_at = dt.datetime.now(dt.UTC)
    service, repo = _build_service(frame_bytes=_jpeg_frame(), embed=lambda crop: [0.5])
    repo.search_results = [(match_row, 0.9)]

    matches = await service.search_by_image(_jpeg_frame())

    assert len(matches) == 1
    assert matches[0].track_id == "9"
