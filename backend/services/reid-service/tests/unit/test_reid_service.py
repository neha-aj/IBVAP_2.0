import datetime as dt
import uuid

import cv2
import numpy as np
import pytest

from ibvap_common.stream_auth import verify_resource_token

from app.core.config import Settings
from app.models.person_embedding import PersonEmbedding
from app.schemas.internal import BoundingBox, TrackEvent
from app.services.reid_service import ReidService


def _settings(**overrides) -> Settings:
    defaults = {
        "postgres_user": "u", "postgres_password": "p", "postgres_db": "d", "jwt_secret": "s",
        "internal_service_token": "t", "person_crop_min_size_px": 10, "similarity_threshold": 0.6,
        "max_search_results": 20,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _jpeg_frame(height: int = 200, width: int = 300) -> bytes:
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", frame)
    assert ok
    return encoded.tobytes()


def _track_event(event: str = "track.started", camera_id: str = "CAM-01", track_id: str = "7") -> TrackEvent:
    bbox = None if event == "track.lost" else BoundingBox(x=10.0, y=10.0, width=50.0, height=50.0)
    return TrackEvent(event=event, trackId=track_id, cameraId=camera_id, objectType="person", bbox=bbox)


class FakeCameraClient:
    def __init__(self, frame_bytes: bytes | None) -> None:
        self.frame_bytes = frame_bytes
        self.names = {"CAM-01": _FakeCameraInfo("CAM-01", "North Gate")}

    async def get_current_frame(self, camera_id: str) -> bytes | None:
        return self.frame_bytes

    async def get_camera_info(self, camera_id: str):
        return self.names.get(camera_id)


class _FakeCameraInfo:
    def __init__(self, id_: str, name: str) -> None:
        self.id = id_
        self.name = name


class FakeMediaClient:
    async def store_person_crop(self, *, camera_id: str, jpeg_bytes: bytes):
        return None


class FakeEmbeddingRepo:
    def __init__(self, existing: dict[tuple[str, str], PersonEmbedding] | None = None) -> None:
        self.existing = existing or {}
        self.created: list[PersonEmbedding] = []
        self.search_results: list[tuple[PersonEmbedding, float]] = []

    async def get_latest_by_track(self, *, camera_id: str, track_id: str):
        return self.existing.get((camera_id, track_id))

    async def create(self, embedding_row: PersonEmbedding) -> PersonEmbedding:
        embedding_row.created_at = dt.datetime.now(dt.UTC)
        self.created.append(embedding_row)
        self.existing[(embedding_row.camera_id, embedding_row.track_id)] = embedding_row
        return embedding_row

    async def search_similar(self, query_embedding, *, exclude_track_id, limit):
        return self.search_results


def _build_service(*, frame_bytes, embed, existing=None, search_results=None, settings=None):
    repo = FakeEmbeddingRepo(existing)
    repo.search_results = search_results or []
    service = ReidService(
        settings=settings or _settings(),
        embedding_repo=repo,
        camera_client=FakeCameraClient(frame_bytes),
        media_client=FakeMediaClient(),
        embed=embed,
    )
    return service, repo


@pytest.mark.asyncio
async def test_process_track_event_extracts_and_persists_embedding() -> None:
    service, repo = _build_service(frame_bytes=_jpeg_frame(), embed=lambda crop: [0.1, 0.2, 0.3])

    result = await service.process_track_event(_track_event())

    assert result is not None
    assert result.track_id == "7"
    assert result.camera_id == "CAM-01"
    assert result.embedding == [0.1, 0.2, 0.3]
    assert len(repo.created) == 1


@pytest.mark.asyncio
async def test_process_track_event_skips_non_person() -> None:
    service, repo = _build_service(frame_bytes=_jpeg_frame(), embed=lambda crop: [0.1])
    event = TrackEvent(
        event="track.started", trackId="7", cameraId="CAM-01", objectType="vehicle",
        bbox=BoundingBox(x=10, y=10, width=50, height=50),
    )
    assert await service.process_track_event(event) is None
    assert repo.created == []


@pytest.mark.asyncio
async def test_process_track_event_skips_track_lost() -> None:
    service, repo = _build_service(frame_bytes=_jpeg_frame(), embed=lambda crop: [0.1])
    assert await service.process_track_event(_track_event("track.lost")) is None
    assert repo.created == []


@pytest.mark.asyncio
async def test_process_track_event_does_not_duplicate_existing_embedding() -> None:
    existing_row = PersonEmbedding(track_id="7", camera_id="CAM-01", embedding=[0.9])
    service, repo = _build_service(
        frame_bytes=_jpeg_frame(), embed=lambda crop: [0.1], existing={("CAM-01", "7"): existing_row},
    )
    result = await service.process_track_event(_track_event())
    assert result is None
    assert repo.created == []


@pytest.mark.asyncio
async def test_process_track_event_none_without_current_frame() -> None:
    service, repo = _build_service(frame_bytes=None, embed=lambda crop: [0.1])
    assert await service.process_track_event(_track_event()) is None
    assert repo.created == []


@pytest.mark.asyncio
async def test_process_track_event_none_for_too_small_crop() -> None:
    service, repo = _build_service(
        frame_bytes=_jpeg_frame(), embed=lambda crop: [0.1], settings=_settings(person_crop_min_size_px=1000),
    )
    assert await service.process_track_event(_track_event()) is None
    assert repo.created == []


@pytest.mark.asyncio
async def test_search_by_track_empty_when_no_stored_embedding() -> None:
    service, _ = _build_service(frame_bytes=_jpeg_frame(), embed=lambda crop: [0.1])
    matches = await service.search_by_track(camera_id="CAM-01", track_id="unknown")
    assert matches == []


@pytest.mark.asyncio
async def test_search_by_track_filters_below_threshold_and_resolves_camera_name() -> None:
    query_row = PersonEmbedding(track_id="7", camera_id="CAM-01", embedding=[0.1])
    match_row = PersonEmbedding(track_id="8", camera_id="CAM-01", embedding=[0.1])
    match_row.snapshot_id = uuid.uuid4()
    match_row.created_at = dt.datetime.now(dt.UTC)
    service, _ = _build_service(
        frame_bytes=_jpeg_frame(), embed=lambda crop: [0.1],
        existing={("CAM-01", "7"): query_row},
        search_results=[(match_row, 0.85), (match_row, 0.2)],  # second is below default 0.6 threshold
    )

    matches = await service.search_by_track(camera_id="CAM-01", track_id="7")

    assert len(matches) == 1
    assert matches[0].similarity_score == 0.85
    assert matches[0].camera_name == "North Gate"
    assert matches[0].snapshot_id == str(match_row.snapshot_id)


@pytest.mark.asyncio
async def test_search_by_track_snapshot_url_carries_a_token_scoped_to_that_snapshot() -> None:
    """M24 security review follow-up: a bare `snapshotId` isn't enough for
    the frontend's `<img src>` (which can't attach an Authorization
    header) -- `snapshotUrl` must be a fetchable, token-scoped URL, and the
    token must verify against this exact snapshot id, not just any."""
    query_row = PersonEmbedding(track_id="7", camera_id="CAM-01", embedding=[0.1])
    match_row = PersonEmbedding(track_id="8", camera_id="CAM-01", embedding=[0.1])
    match_row.snapshot_id = uuid.uuid4()
    match_row.created_at = dt.datetime.now(dt.UTC)
    settings = _settings()
    service, _ = _build_service(
        frame_bytes=_jpeg_frame(), embed=lambda crop: [0.1],
        existing={("CAM-01", "7"): query_row},
        search_results=[(match_row, 0.85)],
        settings=settings,
    )

    matches = await service.search_by_track(camera_id="CAM-01", track_id="7")

    assert matches[0].snapshot_url.startswith(f"/media/snapshots/{match_row.snapshot_id}?token=")
    token = matches[0].snapshot_url.split("?token=", 1)[1]
    verify_resource_token(token, resource=str(match_row.snapshot_id), settings=settings)  # must not raise


@pytest.mark.asyncio
async def test_search_by_track_snapshot_url_is_none_without_a_stored_snapshot() -> None:
    query_row = PersonEmbedding(track_id="7", camera_id="CAM-01", embedding=[0.1])
    match_row = PersonEmbedding(track_id="8", camera_id="CAM-01", embedding=[0.1])
    match_row.created_at = dt.datetime.now(dt.UTC)
    service, _ = _build_service(
        frame_bytes=_jpeg_frame(), embed=lambda crop: [0.1],
        existing={("CAM-01", "7"): query_row},
        search_results=[(match_row, 0.85)],
    )

    matches = await service.search_by_track(camera_id="CAM-01", track_id="7")

    assert matches[0].snapshot_id is None
    assert matches[0].snapshot_url is None


@pytest.mark.asyncio
async def test_search_by_image_embeds_and_searches() -> None:
    match_row = PersonEmbedding(track_id="9", camera_id="CAM-01", embedding=[0.1])
    match_row.created_at = dt.datetime.now(dt.UTC)
    service, _ = _build_service(
        frame_bytes=_jpeg_frame(), embed=lambda crop: [0.5],
        search_results=[(match_row, 0.9)],
    )

    matches = await service.search_by_image(_jpeg_frame())

    assert len(matches) == 1
    assert matches[0].track_id == "9"


@pytest.mark.asyncio
async def test_has_embedding_reflects_repo_state() -> None:
    existing_row = PersonEmbedding(track_id="7", camera_id="CAM-01", embedding=[0.9])
    service, _ = _build_service(
        frame_bytes=_jpeg_frame(), embed=lambda crop: [0.1], existing={("CAM-01", "7"): existing_row},
    )
    assert await service.has_embedding(camera_id="CAM-01", track_id="7") is True
    assert await service.has_embedding(camera_id="CAM-01", track_id="other") is False
