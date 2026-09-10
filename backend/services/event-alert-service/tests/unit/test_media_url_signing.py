import datetime as dt
import uuid

from ibvap_common.stream_auth import verify_resource_token

from app.core.config import Settings
from app.models.alert import Alert
from app.models.event import Event
from app.schemas.alert import to_alert_read
from app.schemas.event import to_event_detail


def _settings() -> Settings:
    return Settings(postgres_user="u", postgres_password="p", postgres_db="d", jwt_secret="s")


def _event(**overrides) -> Event:
    defaults = dict(
        id=uuid.uuid4(), camera_id="CAM-01", camera_name="North Gate", event_type="Fence Intrusion",
        object_type="person", severity="high", location="Perimeter", status="active", description=None,
        snapshot_id=None, snapshot_url=None, recording_id=None, recording_url=None,
        created_at=dt.datetime.now(dt.UTC),
    )
    defaults.update(overrides)
    return Event(**defaults)


def _alert(**overrides) -> Alert:
    defaults = dict(
        id=uuid.uuid4(), event_id=uuid.uuid4(), camera_id="CAM-01", camera_name="North Gate", type="Fence Intrusion",
        object_type="person", severity="critical", location="Perimeter", description=None,
        recording_id=None, recording_url=None, status="active", acknowledged_by=None, acknowledged_at=None,
        resolved_at=None, created_at=dt.datetime.now(dt.UTC),
    )
    defaults.update(overrides)
    return Alert(**defaults)


def test_event_detail_rebuilds_snapshot_and_recording_urls_from_stored_ids() -> None:
    """M24 security review follow-up: `Event.snapshot_url`/`recording_url`
    are raw file paths denormalized at capture time -- fetchable with zero
    auth if handed to the frontend as-is once nginx's static alias is
    locked down. `GET /events/{id}` must instead rebuild a fresh, scoped,
    signed URL from the stored ids every time it's read, and must ignore
    whatever stale raw value sits in those denormalized columns."""
    settings = _settings()
    snapshot_id = uuid.uuid4()
    recording_id = uuid.uuid4()
    event = _event(
        snapshot_id=snapshot_id,
        snapshot_url="/media/snapshots/CAM-01/2026-09-08/leaked.jpg",  # stale raw path -- must not be reused
        recording_id=recording_id,
        recording_url="/media/recordings/CAM-01/2026-09-08/leaked.mp4",
    )

    detail = to_event_detail(event, settings)

    assert detail.snapshot_url.startswith(f"/media/snapshots/{snapshot_id}?token=")
    assert detail.recording_url.startswith(f"/media/recordings/{recording_id}/file?token=")
    verify_resource_token(
        detail.snapshot_url.split("?token=", 1)[1], resource=str(snapshot_id), settings=settings
    )
    verify_resource_token(
        detail.recording_url.split("?token=", 1)[1], resource=str(recording_id), settings=settings
    )


def test_event_detail_urls_are_none_without_stored_ids() -> None:
    detail = to_event_detail(_event(), _settings())
    assert detail.snapshot_url is None
    assert detail.recording_url is None


def test_alert_read_rebuilds_recording_url_from_stored_id() -> None:
    settings = _settings()
    recording_id = uuid.uuid4()
    alert = _alert(recording_id=recording_id, recording_url="/media/recordings/CAM-01/2026-09-08/leaked.mp4")

    read = to_alert_read(alert, settings)

    assert read.recording_url.startswith(f"/media/recordings/{recording_id}/file?token=")
    verify_resource_token(read.recording_url.split("?token=", 1)[1], resource=str(recording_id), settings=settings)


def test_alert_read_without_settings_omits_recording_url() -> None:
    """`settings` is optional (mirrors `PubSubPublisher.__init__`'s own
    optional-settings idiom) so any caller that only needs persistence
    doesn't have to construct a full `Settings` -- it must degrade to no
    URL rather than raising."""
    alert = _alert(recording_id=uuid.uuid4(), recording_url="/media/recordings/CAM-01/2026-09-08/leaked.mp4")

    read = to_alert_read(alert)

    assert read.recording_url is None
