import uuid
from dataclasses import dataclass

import pytest

from ibvap_common.errors import NotFoundError, UnauthorizedError
from ibvap_common.stream_auth import verify_resource_token

from app.api import recordings
from app.core.config import Settings


def _settings() -> Settings:
    return Settings(postgres_user="u", postgres_password="p", postgres_db="d", jwt_secret="s")


@dataclass
class _FakeRecording:
    id: uuid.UUID
    camera_id: str = "CAM-01"
    start_time: object = None
    end_time: object = None
    duration_seconds: int = 30
    file_path: str = "/media/recordings/CAM-01/2026-09-08/clip.mp4"


class _FakeRepo:
    def __init__(self, session) -> None:
        self._session = session

    async def get_recording(self, recording_id: uuid.UUID):
        return self._session.get(recording_id)


class _FakeSession(dict):
    def get(self, recording_id: uuid.UUID):
        return super().get(recording_id)


async def test_get_recording_playback_url_carries_a_valid_scoped_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """M24 security review follow-up: `playback_url` used to be the raw
    static file path, fetchable with zero auth via nginx's static alias
    once that alias is made `internal`. It must instead point at the new
    token-gated `/file` sub-route with a token that verifies for this
    exact recording id."""
    import datetime as dt

    monkeypatch.setattr(recordings, "MediaRepository", _FakeRepo)
    settings = _settings()
    recording_id = uuid.uuid4()
    now = dt.datetime.now(dt.UTC)
    session = _FakeSession(
        {recording_id: _FakeRecording(id=recording_id, start_time=now, end_time=now, duration_seconds=12)}
    )

    result = await recordings.get_recording(str(recording_id), session=session, settings=settings, _user=None)

    assert result.playback_url.startswith(f"/media/recordings/{recording_id}/file?token=")
    token = result.playback_url.split("?token=", 1)[1]
    verify_resource_token(token, resource=str(recording_id), settings=settings)  # must not raise


async def test_get_recording_file_without_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(recordings, "MediaRepository", _FakeRepo)
    recording_id = uuid.uuid4()

    with pytest.raises(UnauthorizedError):
        await recordings.get_recording_file(
            str(recording_id), token=None, session=_FakeSession(), settings=_settings()
        )


async def test_get_recording_file_with_valid_token_serves_via_x_accel_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ibvap_common.stream_auth import create_resource_token

    monkeypatch.setattr(recordings, "MediaRepository", _FakeRepo)
    settings = _settings()
    recording_id = uuid.uuid4()
    session = _FakeSession({recording_id: _FakeRecording(id=recording_id)})
    token = create_resource_token(resource=str(recording_id), ttl_seconds=60, settings=settings)

    response = await recordings.get_recording_file(str(recording_id), token=token, session=session, settings=settings)

    assert response.status_code == 200
    assert response.headers["x-accel-redirect"] == "/media/recordings/CAM-01/2026-09-08/clip.mp4"
    assert response.media_type == "video/mp4"


async def test_get_recording_file_malformed_id_returns_not_found() -> None:
    with pytest.raises(NotFoundError):
        await recordings.get_recording_file("not-a-uuid", token=None, session=_FakeSession(), settings=_settings())
