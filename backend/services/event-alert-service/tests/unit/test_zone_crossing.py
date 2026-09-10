from app.rules.zone_crossing import (
    bbox_center,
    find_general_zone,
    find_queue_zone,
    point_in_polygon,
    polygon_area,
    zones_with_density_threshold,
)
from app.schemas.internal import BoundingBox, Point, Zone


def _square(x0: float, y0: float, x1: float, y1: float) -> list[Point]:
    return [Point(x=x0, y=y0), Point(x=x1, y=y0), Point(x=x1, y=y1), Point(x=x0, y=y1)]


def test_point_inside_polygon() -> None:
    assert point_in_polygon(50.0, 50.0, _square(0, 0, 100, 100)) is True


def test_point_outside_polygon() -> None:
    assert point_in_polygon(150.0, 50.0, _square(0, 0, 100, 100)) is False


def test_degenerate_polygon_never_contains_a_point() -> None:
    assert point_in_polygon(1.0, 1.0, [Point(x=0, y=0), Point(x=1, y=1)]) is False


def test_bbox_center_is_midpoint() -> None:
    bbox = BoundingBox(x=10.0, y=20.0, width=10.0, height=10.0)
    assert bbox_center(bbox) == (15.0, 25.0)


def _zone(zone_type: str, polygon: list[Point], zone_id: str = "z1", density_threshold: float | None = None) -> Zone:
    return Zone(id=zone_id, name="Zone", polygon=polygon, zone_type=zone_type, density_threshold=density_threshold)


def test_find_general_zone_matches_only_general_type() -> None:
    bbox = BoundingBox(x=45.0, y=45.0, width=10.0, height=10.0)
    zones = [
        _zone("restricted", _square(0, 0, 100, 100), "restricted-1"),
        _zone("general", _square(0, 0, 100, 100), "general-1"),
    ]
    matched = find_general_zone(bbox, zones)
    assert matched is not None
    assert matched.id == "general-1"


def test_find_general_zone_none_when_outside() -> None:
    bbox = BoundingBox(x=200.0, y=200.0, width=10.0, height=10.0)
    zones = [_zone("general", _square(0, 0, 100, 100))]
    assert find_general_zone(bbox, zones) is None


def test_find_general_zone_ignores_restricted_and_perimeter() -> None:
    bbox = BoundingBox(x=45.0, y=45.0, width=10.0, height=10.0)
    zones = [
        _zone("restricted", _square(0, 0, 100, 100)),
        _zone("perimeter", _square(0, 0, 100, 100)),
    ]
    assert find_general_zone(bbox, zones) is None


def test_find_queue_zone_matches_only_queue_type() -> None:
    bbox = BoundingBox(x=45.0, y=45.0, width=10.0, height=10.0)
    zones = [
        _zone("general", _square(0, 0, 100, 100), "general-1"),
        _zone("queue", _square(0, 0, 100, 100), "queue-1"),
    ]
    matched = find_queue_zone(bbox, zones)
    assert matched is not None
    assert matched.id == "queue-1"


def test_zones_with_density_threshold_returns_all_matches_not_first() -> None:
    """Unlike find_general_zone/find_queue_zone, a track can count toward
    multiple overlapping density-monitored zones at once."""
    bbox = BoundingBox(x=45.0, y=45.0, width=10.0, height=10.0)
    zones = [
        _zone("general", _square(0, 0, 100, 100), "z1", density_threshold=0.01),
        _zone("restricted", _square(0, 0, 100, 100), "z2", density_threshold=0.02),
        _zone("general", _square(0, 0, 100, 100), "z3", density_threshold=None),  # opted out
    ]
    matches = zones_with_density_threshold(bbox, zones)
    assert {z.id for z in matches} == {"z1", "z2"}


def test_polygon_area_of_a_square() -> None:
    assert polygon_area(_square(0, 0, 10, 10)) == 100.0


def test_polygon_area_degenerate_is_zero() -> None:
    assert polygon_area([Point(x=0, y=0), Point(x=1, y=1)]) == 0.0
