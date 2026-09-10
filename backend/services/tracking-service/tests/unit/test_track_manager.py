"""Unit tests for `TrackManager`'s lifecycle-event diffing (started/updated/
lost), layered on top of the real ByteTrack runner."""

from app.core.config import Settings
from app.schemas.detection import BoundingBox, Detection
from app.tracking.track_manager import TrackManager


def _settings() -> Settings:
    # minimum_consecutive_frames=1 so these lifecycle-event-diffing tests can
    # assert on a single update() call -- flicker-filtering behavior itself
    # is covered separately in test_bytetrack_runner.py.
    return Settings(
        postgres_user="u", postgres_password="p", postgres_db="d", jwt_secret="s",
        minimum_consecutive_frames=1,
    )


def _detection(x: float, y: float, object_type: str = "person") -> Detection:
    return Detection(
        id="raw-id", cameraId="CAM-01", type=object_type, confidence=0.9, trackId=None,
        bbox=BoundingBox(x=x, y=y, width=10.0, height=20.0),
    )


def test_first_sighting_emits_track_started() -> None:
    manager = TrackManager(_settings())

    tracked, events = manager.update("CAM-01", [_detection(x=10.0, y=10.0)])

    assert len(tracked) == 1
    assert [e.event for e in events] == ["track.started"]
    assert events[0].track_id == tracked[0].trackId


def test_continuing_sighting_emits_track_updated() -> None:
    manager = TrackManager(_settings())
    manager.update("CAM-01", [_detection(x=10.0, y=10.0)])

    _, events = manager.update("CAM-01", [_detection(x=11.0, y=10.5)])

    assert [e.event for e in events] == ["track.updated"]


def test_disappearing_object_emits_track_lost() -> None:
    manager = TrackManager(_settings())
    tracked, _ = manager.update("CAM-01", [_detection(x=10.0, y=10.0)])
    lost_track_id = tracked[0].trackId

    _, events = manager.update("CAM-01", [])

    assert [e.event for e in events] == ["track.lost"]
    assert events[0].track_id == lost_track_id


def test_cameras_are_tracked_independently() -> None:
    manager = TrackManager(_settings())

    _tracked_a, events_a = manager.update("CAM-A", [_detection(x=10.0, y=10.0)])
    _tracked_b, events_b = manager.update("CAM-B", [_detection(x=10.0, y=10.0)])

    # Both cameras see their first object -- both must be "started", not
    # accidentally deduplicated or cross-contaminated by a shared tracker.
    assert [e.event for e in events_a] == ["track.started"]
    assert [e.event for e in events_b] == ["track.started"]


def test_track_lost_reports_the_correct_object_type() -> None:
    # Regression test: `track.lost` used to hardcode object_type="person"
    # regardless of what was actually lost, which would silently corrupt any
    # downstream per-type bookkeeping (e.g. Event/Alert Service's active
    # person/vehicle counts) for lost vehicle tracks.
    manager = TrackManager(_settings())
    tracked, _ = manager.update("CAM-01", [_detection(x=10.0, y=10.0, object_type="vehicle")])
    assert tracked[0].type == "vehicle"

    _, events = manager.update("CAM-01", [])

    assert events[0].event == "track.lost"
    assert events[0].object_type == "vehicle"


def test_remove_camera_clears_its_state() -> None:
    manager = TrackManager(_settings())
    manager.update("CAM-01", [_detection(x=10.0, y=10.0)])

    manager.remove_camera("CAM-01")
    _tracked, events = manager.update("CAM-01", [_detection(x=10.0, y=10.0)])

    # A fresh tracker for this camera -- treated as a brand-new sighting.
    assert [e.event for e in events] == ["track.started"]
