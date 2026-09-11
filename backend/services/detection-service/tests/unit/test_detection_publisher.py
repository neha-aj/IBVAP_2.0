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
    # Spread out (non-overlapping) so `_suppress_contained_duplicates`
    # (each of these is a distinct raw COCO class, but they all resolve to
    # the same merged "vehicle" type) has nothing to suppress here -- this
    # test is about the class->type mapping, not the dedup logic, which
    # has its own tests below.
    vehicle_class_ids = [1, 2, 3, 5, 7]  # bicycle, car, motorcycle, bus, truck
    raws = [
        RawDetection(class_id=cid, confidence=0.5, x1=float(i * 20), y1=0.0, x2=float(i * 20 + 10), y2=10.0)
        for i, cid in enumerate(vehicle_class_ids)
    ]

    detections = to_detections(
        camera_id="CAM-01", raw_detections=raws, frame_width=1000, frame_height=100
    )

    assert len(detections) == len(vehicle_class_ids)
    assert all(d.type == "vehicle" for d in detections)


def test_animal_classes_all_map_to_animal_type() -> None:
    """Phase 2 M21 -- see COCO_TYPE_MAP's own docstring for why this
    deployment enables this particular subset of COCO's animal classes.
    Spread out for the same reason `test_vehicle_classes_all_map_to_
    vehicle_type` is -- see that test's own comment."""
    animal_class_ids = [15, 16, 17, 18, 19, 20, 21, 22, 23]
    raws = [
        RawDetection(class_id=cid, confidence=0.5, x1=float(i * 20), y1=0.0, x2=float(i * 20 + 10), y2=10.0)
        for i, cid in enumerate(animal_class_ids)
    ]

    detections = to_detections(
        camera_id="CAM-01", raw_detections=raws, frame_width=1000, frame_height=100
    )

    assert len(detections) == len(animal_class_ids)
    assert all(d.type == "animal" for d in detections)


def test_duplicate_vehicle_across_raw_classes_is_suppressed() -> None:
    """Reproduces this deployment's real, observed false positive: one
    physical vehicle scored highly as YOLO's raw "car" class (a tight box
    around the car body) and, in the same frame, as raw "truck" (a much
    larger box spanning the car plus its open trunk) -- both merged into
    "vehicle" by `COCO_TYPE_MAP`. The two raw boxes overlapped at only
    ~10% IoU (too low for any standard IoU-based NMS to catch) but the
    smaller box sat ~56% inside the larger one -- this is exactly the
    containment shape `_suppress_contained_duplicates` targets. Only the
    higher-confidence ("car") detection should survive."""
    car = RawDetection(class_id=2, confidence=0.80, x1=259.0, y1=287.0, x2=570.0, y2=405.0)
    truck = RawDetection(class_id=7, confidence=0.57, x1=311.0, y1=326.0, x2=770.0, y2=695.0)

    detections = to_detections(
        camera_id="CAM-01", raw_detections=[car, truck], frame_width=1490, frame_height=790
    )

    assert len(detections) == 1
    assert detections[0].confidence == 0.80


def test_distinct_same_type_vehicles_are_not_suppressed() -> None:
    """Two genuinely separate vehicles (e.g. a second car partially visible
    at frame's edge) must never be collapsed just for sharing a type --
    only real containment triggers suppression."""
    left_car = RawDetection(class_id=2, confidence=0.9, x1=0.0, y1=0.0, x2=100.0, y2=100.0)
    right_car = RawDetection(class_id=2, confidence=0.8, x1=500.0, y1=0.0, x2=600.0, y2=100.0)

    detections = to_detections(
        camera_id="CAM-01", raw_detections=[left_car, right_car], frame_width=1000, frame_height=100
    )

    assert len(detections) == 2


def test_same_raw_class_containment_is_not_suppressed() -> None:
    """Reproduces a real mistake caught live on this deployment's own
    footage: an earlier, broader version of the suppression logic (which
    compared any two detections of the same *merged* type, not just cross-
    raw-class ones) wrongly deleted a real, distinct second vehicle -- a
    dark SUV parked beside a white one, both raw class "car" (class_id=2)
    -- purely because its smaller box's rectangle happened to fall inside
    the larger SUV's box. Two same-raw-class boxes have already been
    through YOLO's own per-class NMS upstream, so both surviving is real
    evidence they're genuinely separate objects; suppression must only
    ever trigger across *different* raw classes (see
    `_suppress_contained_duplicates`'s own docstring)."""
    white_suv = RawDetection(class_id=2, confidence=0.91, x1=915.0, y1=267.0, x2=1490.0, y2=712.0)
    dark_suv = RawDetection(class_id=2, confidence=0.71, x1=1325.0, y1=307.0, x2=1490.0, y2=456.0)  # class_id=2

    detections = to_detections(
        camera_id="CAM-01", raw_detections=[white_suv, dark_suv], frame_width=1490, frame_height=790
    )

    assert len(detections) == 2


def test_duplicate_suppression_is_scoped_to_same_merged_type() -> None:
    """A person and a vehicle occupying the same screen region (e.g. a
    driver visible through a windshield) must never suppress each other --
    `_suppress_contained_duplicates` only ever compares detections that
    already resolved to the same reported type."""
    person = RawDetection(class_id=0, confidence=0.9, x1=10.0, y1=10.0, x2=50.0, y2=90.0)
    vehicle = RawDetection(class_id=2, confidence=0.85, x1=0.0, y1=0.0, x2=100.0, y2=100.0)  # fully contains person

    detections = to_detections(
        camera_id="CAM-01", raw_detections=[person, vehicle], frame_width=1000, frame_height=1000
    )

    assert len(detections) == 2
    assert {d.type for d in detections} == {"person", "vehicle"}


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
