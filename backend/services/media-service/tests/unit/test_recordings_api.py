import uuid
from dataclasses import dataclass

import pytest

from ibvap_common.errors import NotFoundError, UnauthorizedError
from ibvap_common.stream_auth import verify_resource_token

from app.api import recordings
from app.core.config import Settings
from app.security import integrity


def _settings(tmp_path=None) -> Settings:
    kwargs = dict(
        postgres_user="u", postgres_password="p", postgres_db="d", jwt_secret="s",
        # Fast, guaranteed-unreachable -- avoids a slow/flaky real DNS
        # lookup against the default "ledger-service" hostname; ledger
        # calls degrade to "unavailable"/no-op regardless (see
        # app/services/ledger_service.py).
        ledger_service_url="http://127.0.0.1:1", ledger_request_timeout_seconds=0.5,
    )
    if tmp_path is not None:
        # Only needed for tests that actually sign something (create_recording,
        # verify_recording) -- signing persists a key file under media_root,
        # and the real default ("/data/media") must never be touched by a
        # test run. Tests that don't sign anything keep the plain default.
        kwargs["media_root"] = str(tmp_path)
    return Settings(**kwargs)


class _RecordingAuditLog:
    """Stand-in for app.services.audit_log_service -- see the identical
    class in test_snapshots_api.py for why."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def append_audit_entry(self, _session, **kwargs):
        self.calls.append(kwargs)


class _NoOpAnomaly:
    """Stand-in for app.services.anomaly_service -- same reason as
    `_RecordingAuditLog` (it also needs a real DB session)."""

    async def check_and_report(self, *_args, **_kwargs):
        pass


@dataclass
class _FakeRecording:
    id: uuid.UUID
    camera_id: str = "CAM-01"
    start_time: object = None
    end_time: object = None
    duration_seconds: int = 30
    file_path: str = "/media/recordings/CAM-01/2026-09-08/clip.mp4"
    # M25 tamper-evidence fields, defaulted so every existing call site
    # above keeps working unchanged.
    content_hash: str | None = None
    signature: str | None = None


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
    monkeypatch.setattr(recordings, "audit_log_service", _RecordingAuditLog())
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
    monkeypatch.setattr(recordings, "audit_log_service", _RecordingAuditLog())
    monkeypatch.setattr(recordings, "anomaly_service", _NoOpAnomaly())
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
    monkeypatch: pytest.MonkeyPatch, tmp_path,
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
        file=upload, session=_FakeSession(), settings=_settings(tmp_path),
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
    monkeypatch.setattr(recordings, "audit_log_service", _RecordingAuditLog())
    settings = _settings()
    recording_id = uuid.uuid4()
    session = _FakeSession({recording_id: _FakeRecording(id=recording_id)})
    token = create_resource_token(resource=str(recording_id), ttl_seconds=60, settings=settings)

    response = await recordings.get_recording_file(
        str(recording_id), token=token, download=False, session=session, settings=settings
    )

    assert "content-disposition" not in response.headers


# --- M25 tamper-evidence: GET /media/recordings/{id}/verify ---------------------


async def test_verify_recording_without_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(recordings, "MediaRepository", _FakeRepo)
    recording_id = uuid.uuid4()

    with pytest.raises(UnauthorizedError):
        await recordings.verify_recording(str(recording_id), token=None, session=_FakeSession(), settings=_settings())


async def test_verify_recording_reports_tampered_when_the_clip_was_modified(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    from ibvap_common.stream_auth import create_resource_token

    monkeypatch.setattr(recordings, "MediaRepository", _FakeRepo)
    monkeypatch.setattr(recordings, "audit_log_service", _RecordingAuditLog())
    monkeypatch.setattr(recordings, "anomaly_service", _NoOpAnomaly())
    settings = _settings(tmp_path)
    recording_id = uuid.uuid4()
    relative = f"recordings/CAM-01/{uuid.uuid4().hex}_clip.webm"
    (tmp_path / "recordings" / "CAM-01").mkdir(parents=True)
    (tmp_path / relative).write_bytes(b"original clip bytes")
    content_hash = integrity.compute_hash(b"original clip bytes")
    signature = integrity.sign_evidence(
        media_root=settings.media_root, record_id=str(recording_id), camera_id="CAM-01", content_hash=content_hash
    )
    # The clip is overwritten after capture -- the tamper case.
    (tmp_path / relative).write_bytes(b"swapped-in clip bytes")
    recording = _FakeRecording(
        id=recording_id, file_path=f"{settings.media_url_prefix}/{relative}",
        content_hash=content_hash, signature=signature,
    )
    session = _FakeSession({recording_id: recording})
    token = create_resource_token(resource=str(recording_id), ttl_seconds=60, settings=settings)

    result = await recordings.verify_recording(str(recording_id), token=token, session=session, settings=settings)

    assert result.status == "tampered"
    assert result.hash_matches is False
    assert result.signature_valid is True


async def test_verify_recording_records_the_result_in_the_audit_log(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    from ibvap_common.stream_auth import create_resource_token

    monkeypatch.setattr(recordings, "MediaRepository", _FakeRepo)
    audit_log = _RecordingAuditLog()
    monkeypatch.setattr(recordings, "audit_log_service", audit_log)
    monkeypatch.setattr(recordings, "anomaly_service", _NoOpAnomaly())
    settings = _settings(tmp_path)
    recording_id = uuid.uuid4()
    recording = _FakeRecording(id=recording_id, file_path=f"{settings.media_url_prefix}/recordings/CAM-01/old.webm")
    session = _FakeSession({recording_id: recording})
    token = create_resource_token(resource=str(recording_id), ttl_seconds=60, settings=settings, subject="bob")

    await recordings.verify_recording(str(recording_id), token=token, session=session, settings=settings)

    assert len(audit_log.calls) == 1
    assert audit_log.calls[0]["action"] == "verify"
    assert audit_log.calls[0]["actor"] == "bob"
    assert audit_log.calls[0]["result"] == "not_signed"
