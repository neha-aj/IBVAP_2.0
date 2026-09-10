"""Unit tests against the real `supervision` ByteTrack implementation (no
mocking) -- per Implementation Guide §9, unit tests should not require live
infrastructure, but there's nothing infra-dependent about the tracker
itself, so these exercise the genuine algorithm."""

from app.schemas.detection import BoundingBox, Detection
from app.tracking.bytetrack_runner import ByteTrackRunner


def _detection(x: float, y: float, object_type: str = "person", confidence: float = 0.9) -> Detection:
    return Detection(
        id="raw-id",
        cameraId="CAM-01",
        type=object_type,  # type: ignore[arg-type]
        confidence=confidence,
        trackId=None,
        bbox=BoundingBox(x=x, y=y, width=10.0, height=20.0),
    )


def _runner() -> ByteTrackRunner:
    return ByteTrackRunner(
        frame_rate=5,
        track_activation_threshold=0.25,
        lost_track_buffer_frames=30,
        minimum_matching_threshold=0.8,
    )


def test_same_object_keeps_same_track_id_across_frames() -> None:
    runner = _runner()

    frame1 = runner.update("CAM-01", [_detection(x=10.0, y=10.0)])
    frame2 = runner.update("CAM-01", [_detection(x=11.0, y=10.5)])  # small nearby move

    assert len(frame1) == 1
    assert len(frame2) == 1
    assert frame1[0].trackId is not None
    assert frame1[0].trackId == frame2[0].trackId


def test_two_simultaneous_objects_get_distinct_track_ids() -> None:
    runner = _runner()

    tracked = runner.update(
        "CAM-01", [_detection(x=10.0, y=10.0), _detection(x=80.0, y=80.0)]
    )

    assert len(tracked) == 2
    assert tracked[0].trackId != tracked[1].trackId


def test_empty_detections_returns_empty_and_does_not_crash() -> None:
    runner = _runner()

    tracked = runner.update("CAM-01", [])

    assert tracked == []


def test_output_bbox_stays_in_percentage_space() -> None:
    runner = _runner()

    tracked = runner.update("CAM-01", [_detection(x=25.0, y=30.0)])

    bbox = tracked[0].bbox
    assert 0.0 <= bbox.x <= 100.0
    assert 0.0 <= bbox.y <= 100.0


def test_single_frame_flicker_is_not_promoted_to_a_track() -> None:
    """A detection that appears once and never again (a false-positive
    blip) must not surface as a track -- without `minimum_consecutive_frames`
    it would, inflating counts with phantom people/vehicles."""
    runner = ByteTrackRunner(
        frame_rate=5,
        track_activation_threshold=0.25,
        lost_track_buffer_frames=30,
        minimum_matching_threshold=0.8,
        minimum_consecutive_frames=3,
    )

    tracked = runner.update("CAM-01", [_detection(x=10.0, y=10.0)])
    assert tracked == []

    tracked = runner.update("CAM-01", [])
    assert tracked == []


def test_object_present_across_enough_frames_is_promoted_to_a_track() -> None:
    runner = ByteTrackRunner(
        frame_rate=5,
        track_activation_threshold=0.25,
        lost_track_buffer_frames=30,
        minimum_matching_threshold=0.8,
        minimum_consecutive_frames=3,
    )

    runner.update("CAM-01", [_detection(x=10.0, y=10.0)])
    runner.update("CAM-01", [_detection(x=10.5, y=10.0)])
    tracked = runner.update("CAM-01", [_detection(x=11.0, y=10.0)])

    assert len(tracked) == 1
    assert tracked[0].trackId is not None


def test_animal_type_round_trips_through_the_tracker() -> None:
    """Phase 2 M21 -- "animal" is a third internal class id (see
    bytetrack_runner.py's own _CLASS_BY_TYPE/_TYPE_BY_CLASS), must survive
    the class_id round-trip unchanged same as person/vehicle."""
    runner = _runner()

    tracked = runner.update("CAM-01", [_detection(x=10.0, y=10.0, object_type="animal")])

    assert len(tracked) == 1
    assert tracked[0].type == "animal"
