import datetime as dt
import uuid

from ibvap_common.stream_auth import verify_resource_token

from app.api.anpr import _to_plate_read
from app.core.config import Settings
from app.models.plate_read import PlateRead


def _settings() -> Settings:
    return Settings(postgres_user="u", postgres_password="p", postgres_db="d", jwt_secret="s")


def _row(**overrides) -> PlateRead:
    defaults = dict(
        id=uuid.uuid4(), camera_id="CAM-01", track_id=None, plate_text="ABC123",
        confidence=91.5, snapshot_id=None, watchlist_match=False, created_at=dt.datetime.now(dt.UTC),
    )
    defaults.update(overrides)
    return PlateRead(**defaults)


def test_to_plate_read_snapshot_url_carries_a_token_scoped_to_the_snapshot() -> None:
    """M24 security review follow-up: `GET /anpr/reads` is the endpoint that
    hands `snapshotId` to the frontend's `<img src>` -- since that tag can't
    carry an Authorization header, the response must include a fetchable,
    token-scoped `snapshotUrl` alongside the bare id."""
    settings = _settings()
    snapshot_id = uuid.uuid4()
    row = _row(snapshot_id=snapshot_id)

    result = _to_plate_read(row, settings)

    assert result.snapshot_id == str(snapshot_id)
    assert result.snapshot_url.startswith(f"/media/snapshots/{snapshot_id}?token=")
    token = result.snapshot_url.split("?token=", 1)[1]
    verify_resource_token(token, resource=str(snapshot_id), settings=settings)  # must not raise


def test_to_plate_read_snapshot_url_is_none_without_a_stored_snapshot() -> None:
    result = _to_plate_read(_row(snapshot_id=None), _settings())

    assert result.snapshot_id is None
    assert result.snapshot_url is None
