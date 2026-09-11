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

    # `download` explicit (not left to its `Query(default=False)` default) --
    # calling the route function directly, bypassing FastAPI's own request
    # cycle, means an unpassed Query-marker parameter evaluates to the
    # sentinel Query object itself (truthy), not the resolved default value.
    # Same reason every other param in this file (e.g. `token`) is always
    # passed explicitly too.
    response = await recordings.get_recording_file(
        str(recording_id), token=token, download=False, session=session, settings=settings
    )

    assert response.status_code == 200
    assert response.headers["x-accel-redirect"] == "/media/recordings/CAM-01/2026-09-08/clip.mp4"
    assert response.media_type == "video/mp4"


async def test_get_recording_file_malformed_id_returns_not_found() -> None:
    with pytest.raises(NotFoundError):
        await recordings.get_recording_file("not-a-uuid", token=None, session=_FakeSession(), settings=_settings())


async def test_get_recording_file_download_sets_content_disposition(monkeypatch: pytest.MonkeyPatch) -> None:
    """Evidence export: ?download=true must trigger a browser save-as
    (Content-Disposition: attachment) with a readable filename, instead of
    the default inline <video> playback the /file route already served."""
    import datetime as dt

    from ibvap_common.stream_auth import create_resource_token

    monkeypatch.setattr(recordings, "MediaRepository", _FakeRepo)
    settings = _settings()
    recording_id = uuid.uuid4()
    start = dt.datetime(2026, 9, 8, 14, 30, 0, tzinfo=dt.UTC)
    session = _FakeSession({recording_id: _FakeRecording(id=recording_id, start_time=start)})
    token = create_resource_token(resource=str(recording_id), ttl_seconds=60, settings=settings)

    response = await recordings.get_recording_file(
        str(recording_id), token=token, download=True, session=session, settings=settings
    )

    assert response.status_code == 200
    assert response.headers["x-accel-redirect"] == "/media/recordings/CAM-01/2026-09-08/clip.mp4"
    assert response.headers["content-disposition"] == 'attachment; filename="CAM-01_20260908-143000.mp4"'


async def test_create_recording_stores_under_the_uploaded_files_real_extension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """event-alert-service's RecordingClient uploads clips as .webm (VP8 --
    no browser-playable H.264 encoder is available in that container, and
    MP4's mp4v fallback isn't supported by any browser's <video> element,
    see recording_client.py's own comment) -- the stored filename must
    follow whatever the caller actually uploaded, not a hardcoded .mp4, or
    `GET .../file`'s `mimetypes.guess_type` mislabels the Content-Type and
    playback breaks despite the bytes on disk being perfectly fine."""
    import datetime as dt
    import io

    from fastapi import UploadFile

    saved = {}

    class _FakeBackend:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def save(self, *, subdir: str, filename: str, data: bytes) -> str:
            saved["subdir"] = subdir
            saved["filename"] = filename
            return f"/media/{subdir}/{filename}"

    class _FakeCreateRepo:
        def __init__(self, _session) -> None:
            pass

        async def create_recording(self, recording):
            return recording

    monkeypatch.setattr(recordings, "LocalStorageBackend", _FakeBackend)
    monkeypatch.setattr(recordings, "MediaRepository", _FakeCreateRepo)

    upload = UploadFile(filename="clip.webm", file=io.BytesIO(b"fake-webm-bytes"))
    now = dt.datetime.now(dt.UTC)

    await recordings.create_recording(
        camera_id="CAM-01", start_time=now, end_time=now, duration_seconds=5,
        file=upload, session=_FakeSession(), settings=_settings(),
    )

    assert saved["filename"] == "clip.webm"


async def test_get_recording_file_without_download_omits_content_disposition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default (no ?download) must behave exactly as before this feature --
    no Content-Disposition header, so existing <video src> inline playback
    is untouched."""
    from ibvap_common.stream_auth import create_resource_token

    monkeypatch.setattr(recordings, "MediaRepository", _FakeRepo)
    settings = _settings()
    recording_id = uuid.uuid4()
    session = _FakeSession({recording_id: _FakeRecording(id=recording_id)})
    token = create_resource_token(resource=str(recording_id), ttl_seconds=60, settings=settings)

    response = await recordings.get_recording_file(
        str(recording_id), token=token, download=False, session=session, settings=settings
    )

    assert "content-disposition" not in response.headers
