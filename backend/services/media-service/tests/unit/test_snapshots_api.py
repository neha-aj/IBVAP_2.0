import uuid
from dataclasses import dataclass, field

import pytest

from ibvap_common.errors import UnauthorizedError
from ibvap_common.stream_auth import create_resource_token

from app.api import snapshots
from app.core.config import Settings
from app.security import integrity


def _settings(tmp_path=None) -> Settings:
    kwargs = dict(
        postgres_user="u", postgres_password="p", postgres_db="d", jwt_secret="s",
        # Fast, guaranteed-unreachable -- these tests exercise the snapshot
        # routes, not ledger-service; avoids a slow/flaky real DNS lookup
        # against the default "ledger-service" hostname.
        ledger_service_url="http://127.0.0.1:1", ledger_request_timeout_seconds=0.5,
    )
    if tmp_path is not None:
        kwargs["media_root"] = str(tmp_path)
    return Settings(**kwargs)


@dataclass
class _FakeSnapshot:
    file_path: str
    # M25 tamper-evidence fields, defaulted so every existing call site
    # above (which only cares about file_path/X-Accel-Redirect) keeps
    # working unchanged.
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    camera_id: str = "CAM-01"
    content_hash: str | None = None
    signature: str | None = None


class _FakeRepo:
    def __init__(self, session) -> None:
        self._session = session

    async def get_snapshot(self, snapshot_id: uuid.UUID):
        return self._session.get(snapshot_id)


class _FakeSession(dict):
    def get(self, snapshot_id: uuid.UUID):
        return super().get(snapshot_id)


class _RecordingAuditLog:
    """Stand-in for app.services.audit_log_service -- these routes call
    `audit_log_service.append_audit_entry(session, ...)`, which needs a
    real SQLAlchemy session the fakes above don't provide. Records calls
    instead of touching a database, same spirit as `_FakeRepo`."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def append_audit_entry(self, _session, **kwargs):
        self.calls.append(kwargs)


class _NoOpAnomaly:
    """Stand-in for app.services.anomaly_service -- same reason as
    `_RecordingAuditLog` (it also needs a real DB session)."""

    async def check_and_report(self, *_args, **_kwargs):
        pass


async def test_get_snapshot_without_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """M24 security review follow-up: `GET /media/snapshots/{id}` used to
    have no auth at all -- a plain 307 redirect to a file nginx then served
    with zero auth either. It must now refuse a request that carries no
    resource token before ever touching the DB or the filesystem."""
    monkeypatch.setattr(snapshots, "MediaRepository", _FakeRepo)
    snapshot_id = uuid.uuid4()

    with pytest.raises(UnauthorizedError):
        await snapshots.get_snapshot(
            str(snapshot_id), token=None, session=_FakeSession(), settings=_settings()
        )


async def test_get_snapshot_with_token_for_a_different_id_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(snapshots, "MediaRepository", _FakeRepo)
    settings = _settings()
    snapshot_id = uuid.uuid4()
    other_id = uuid.uuid4()
    token = create_resource_token(resource=str(other_id), ttl_seconds=60, settings=settings)

    with pytest.raises(UnauthorizedError):
        await snapshots.get_snapshot(str(snapshot_id), token=token, session=_FakeSession(), settings=settings)


async def test_get_snapshot_with_a_valid_token_serves_via_x_accel_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    """Once the token checks out, the response must not be a browser-visible
    redirect to the (now nginx-internal-only) static path -- it has to hand
    the bytes back itself via `X-Accel-Redirect`, the only way nginx will
    still resolve that path."""
    monkeypatch.setattr(snapshots, "MediaRepository", _FakeRepo)
    monkeypatch.setattr(snapshots, "audit_log_service", _RecordingAuditLog())
    settings = _settings()
    snapshot_id = uuid.uuid4()
    file_path = f"/media/snapshots/CAM-01/2026-09-08/{uuid.uuid4().hex}_snapshot.jpg"
    session = _FakeSession({snapshot_id: _FakeSnapshot(file_path=file_path, id=snapshot_id)})
    token = create_resource_token(resource=str(snapshot_id), ttl_seconds=60, settings=settings)

    response = await snapshots.get_snapshot(str(snapshot_id), token=token, session=session, settings=settings)

    assert response.status_code == 200
    assert response.headers["x-accel-redirect"] == file_path
    assert response.media_type == "image/jpeg"


async def test_get_snapshot_records_a_view_in_the_audit_log(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(snapshots, "MediaRepository", _FakeRepo)
    audit_log = _RecordingAuditLog()
    monkeypatch.setattr(snapshots, "audit_log_service", audit_log)
    settings = _settings()
    snapshot_id = uuid.uuid4()
    session = _FakeSession({snapshot_id: _FakeSnapshot(file_path="/media/snapshots/x.jpg", id=snapshot_id)})
    token = create_resource_token(resource=str(snapshot_id), ttl_seconds=60, settings=settings, subject="alice")

    await snapshots.get_snapshot(str(snapshot_id), token=token, session=session, settings=settings)

    assert len(audit_log.calls) == 1
    assert audit_log.calls[0]["action"] == "view"
    assert audit_log.calls[0]["actor"] == "alice"


async def test_get_snapshot_malformed_id_returns_not_found_before_verifying_token() -> None:
    from ibvap_common.errors import NotFoundError

    with pytest.raises(NotFoundError):
        await snapshots.get_snapshot("not-a-uuid", token=None, session=_FakeSession(), settings=_settings())


# --- M25 tamper-evidence: GET /media/snapshots/{id}/verify ---------------------


async def test_verify_snapshot_without_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(snapshots, "MediaRepository", _FakeRepo)
    snapshot_id = uuid.uuid4()

    with pytest.raises(UnauthorizedError):
        await snapshots.verify_snapshot(str(snapshot_id), token=None, session=_FakeSession(), settings=_settings())


async def test_verify_snapshot_reports_verified_for_an_untouched_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(snapshots, "MediaRepository", _FakeRepo)
    monkeypatch.setattr(snapshots, "audit_log_service", _RecordingAuditLog())
    monkeypatch.setattr(snapshots, "anomaly_service", _NoOpAnomaly())
    settings = _settings(tmp_path)
    snapshot_id = uuid.uuid4()
    data = b"a real captured frame"
    relative = f"snapshots/CAM-01/{uuid.uuid4().hex}_snapshot.jpg"
    (tmp_path / "snapshots" / "CAM-01").mkdir(parents=True)
    (tmp_path / relative).write_bytes(data)
    content_hash = integrity.compute_hash(data)
    signature = integrity.sign_evidence(
        media_root=settings.media_root, record_id=str(snapshot_id), camera_id="CAM-01", content_hash=content_hash
    )
    snapshot = _FakeSnapshot(
        file_path=f"{settings.media_url_prefix}/{relative}", id=snapshot_id, camera_id="CAM-01",
        content_hash=content_hash, signature=signature,
    )
    session = _FakeSession({snapshot_id: snapshot})
    token = create_resource_token(resource=str(snapshot_id), ttl_seconds=60, settings=settings)

    result = await snapshots.verify_snapshot(str(snapshot_id), token=token, session=session, settings=settings)

    assert result.status == "verified"


async def test_verify_snapshot_reports_not_signed_for_a_legacy_row(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Evidence captured before M25 has no content_hash/signature at all --
    verify must degrade gracefully rather than error."""
    monkeypatch.setattr(snapshots, "MediaRepository", _FakeRepo)
    monkeypatch.setattr(snapshots, "audit_log_service", _RecordingAuditLog())
    monkeypatch.setattr(snapshots, "anomaly_service", _NoOpAnomaly())
    settings = _settings(tmp_path)
    snapshot_id = uuid.uuid4()
    snapshot = _FakeSnapshot(file_path=f"{settings.media_url_prefix}/snapshots/CAM-01/old.jpg", id=snapshot_id)
    session = _FakeSession({snapshot_id: snapshot})
    token = create_resource_token(resource=str(snapshot_id), ttl_seconds=60, settings=settings)

    result = await snapshots.verify_snapshot(str(snapshot_id), token=token, session=session, settings=settings)

    assert result.status == "not_signed"


async def test_verify_snapshot_records_the_result_in_the_audit_log(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(snapshots, "MediaRepository", _FakeRepo)
    audit_log = _RecordingAuditLog()
    monkeypatch.setattr(snapshots, "audit_log_service", audit_log)
    monkeypatch.setattr(snapshots, "anomaly_service", _NoOpAnomaly())
    settings = _settings(tmp_path)
    snapshot_id = uuid.uuid4()
    snapshot = _FakeSnapshot(file_path=f"{settings.media_url_prefix}/snapshots/CAM-01/old.jpg", id=snapshot_id)
    session = _FakeSession({snapshot_id: snapshot})
    token = create_resource_token(resource=str(snapshot_id), ttl_seconds=60, settings=settings)

    await snapshots.verify_snapshot(str(snapshot_id), token=token, session=session, settings=settings)

    assert len(audit_log.calls) == 1
    assert audit_log.calls[0]["action"] == "verify"
    assert audit_log.calls[0]["result"] == "not_signed"
