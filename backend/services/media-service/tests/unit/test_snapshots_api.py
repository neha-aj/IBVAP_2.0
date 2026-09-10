import uuid
from dataclasses import dataclass

import pytest

from ibvap_common.errors import UnauthorizedError
from ibvap_common.stream_auth import create_resource_token

from app.api import snapshots
from app.core.config import Settings


def _settings() -> Settings:
    return Settings(postgres_user="u", postgres_password="p", postgres_db="d", jwt_secret="s")


@dataclass
class _FakeSnapshot:
    file_path: str


class _FakeRepo:
    def __init__(self, session) -> None:
        self._session = session

    async def get_snapshot(self, snapshot_id: uuid.UUID):
        return self._session.get(snapshot_id)


class _FakeSession(dict):
    def get(self, snapshot_id: uuid.UUID):
        return super().get(snapshot_id)


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
    settings = _settings()
    snapshot_id = uuid.uuid4()
    file_path = f"/media/snapshots/CAM-01/2026-09-08/{uuid.uuid4().hex}_snapshot.jpg"
    session = _FakeSession({snapshot_id: _FakeSnapshot(file_path=file_path)})
    token = create_resource_token(resource=str(snapshot_id), ttl_seconds=60, settings=settings)

    response = await snapshots.get_snapshot(str(snapshot_id), token=token, session=session, settings=settings)

    assert response.status_code == 200
    assert response.headers["x-accel-redirect"] == file_path
    assert response.media_type == "image/jpeg"


async def test_get_snapshot_malformed_id_returns_not_found_before_verifying_token() -> None:
    from ibvap_common.errors import NotFoundError

    with pytest.raises(NotFoundError):
        await snapshots.get_snapshot("not-a-uuid", token=None, session=_FakeSession(), settings=_settings())
