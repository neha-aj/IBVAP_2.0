"""Unit tests for the pure bbox-normalization logic, per Implementation
Guide §9 (unit tests should not require live infrastructure)."""

from app.inference.base import RawDetection
from app.streaming.detection_publisher import to_detections


def test_person_class_maps_and_normalizes_to_percent() -> None:
    raw = RawDetection(class_id=0, confidence=0.91, x1=100.0, y1=50.0, x2=200.0, y2=250.0)

    detections = to_detections(
        camera_id="CAM-01", raw_detections=[raw], frame_width=1000, frame_height=500
    )

    assert len(detections) == 1
    detection = detections[0]
    assert detection.camera_id == "CAM-01"
    assert detection.type == "person"
    assert detection.confidence == 0.91
    assert detection.track_id is None
    assert detection.bbox.x == 10.0  # 100/1000 * 100
    assert detection.bbox.y == 10.0  # 50/500 * 100
    assert detection.bbox.width == 10.0  # (200-100)/1000 * 100
    assert detection.bbox.height == 40.0  # (250-50)/500 * 100


def test_vehicle_classes_all_map_to_vehicle_type() -> None:
    vehicle_class_ids = [1, 2, 3, 5, 7]  # bicycle, car, motorcycle, bus, truck
    raws = [
        RawDetection(class_id=cid, confidence=0.5, x1=0.0, y1=0.0, x2=10.0, y2=10.0)
        for cid in vehicle_class_ids
    ]

    detections = to_detections(
        camera_id="CAM-01", raw_detections=raws, frame_width=100, frame_height=100
    )

    assert len(detections) == len(vehicle_class_ids)
    assert all(d.type == "vehicle" for d in detections)


def test_animal_classes_all_map_to_animal_type() -> None:
    """Phase 2 M21 -- see COCO_TYPE_MAP's own docstring for why this
    deployment enables this particular subset of COCO's animal classes."""
    animal_class_ids = [15, 16, 17, 18, 19, 20, 21, 22, 23]
    raws = [
        RawDetection(class_id=cid, confidence=0.5, x1=0.0, y1=0.0, x2=10.0, y2=10.0)
        for cid in animal_class_ids
    ]

    detections = to_detections(
        camera_id="CAM-01", raw_detections=raws, frame_width=100, frame_height=100
    )

    assert len(detections) == len(animal_class_ids)
    assert all(d.type == "animal" for d in detections)


def test_unmapped_class_is_dropped() -> None:
    raw = RawDetection(class_id=14, confidence=0.9, x1=0.0, y1=0.0, x2=10.0, y2=10.0)  # "bird" -- not enabled

    detections = to_detections(
        camera_id="CAM-01", raw_detections=[raw], frame_width=100, frame_height=100
    )

    assert detections == []


def test_bbox_is_clamped_to_0_100_range() -> None:
    # A box that (due to upstream rounding) slightly exceeds the frame bounds
    # must never produce an out-of-range percentage for the overlay.
    raw = RawDetection(class_id=0, confidence=0.5, x1=-5.0, y1=-5.0, x2=1005.0, y2=1005.0)

    detections = to_detections(
        camera_id="CAM-01", raw_detections=[raw], frame_width=1000, frame_height=1000
    )

    bbox = detections[0].bbox
    assert 0.0 <= bbox.x <= 100.0
    assert 0.0 <= bbox.y <= 100.0
    assert 0.0 <= bbox.width <= 100.0
    assert 0.0 <= bbox.height <= 100.0


def test_detection_serializes_with_camel_case_aliases() -> None:
    raw = RawDetection(class_id=0, confidence=0.8, x1=0.0, y1=0.0, x2=10.0, y2=10.0)
    detection = to_detections(
        camera_id="CAM-01", raw_detections=[raw], frame_width=100, frame_height=100
    )[0]

    dumped = detection.model_dump(by_alias=True)

    assert dumped["cameraId"] == "CAM-01"
    assert dumped["trackId"] is None
    assert set(dumped["bbox"].keys()) == {"x", "y", "width", "height"}
