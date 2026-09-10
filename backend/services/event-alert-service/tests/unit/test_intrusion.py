from app.rules.intrusion import event_label_for_zone, find_matching_zone, severity_for_zone
from app.schemas.internal import BoundingBox, Point, Zone


def _square_zone(zone_type: str, name: str = "Zone") -> Zone:
    return Zone(
        id="zone-1", name=name, zone_type=zone_type,
        polygon=[Point(x=0, y=0), Point(x=100, y=0), Point(x=100, y=100), Point(x=0, y=100)],
    )


def _bbox_inside() -> BoundingBox:
    return BoundingBox(x=40.0, y=40.0, width=10.0, height=10.0)


def _bbox_outside() -> BoundingBox:
    return BoundingBox(x=200.0, y=200.0, width=10.0, height=10.0)


def test_perimeter_zone_entry_labeled_fence_intrusion() -> None:
    zone = _square_zone("perimeter")
    matched = find_matching_zone(_bbox_inside(), [zone])
    assert matched is not None
    assert event_label_for_zone(matched) == "Fence Intrusion"
    assert severity_for_zone(matched) == "critical"


def test_restricted_zone_entry_labeled_restricted_zone_entry() -> None:
    zone = _square_zone("restricted")
    matched = find_matching_zone(_bbox_inside(), [zone])
    assert matched is not None
    assert event_label_for_zone(matched) == "Restricted Zone Entry"
    assert severity_for_zone(matched) == "high"


def test_general_zone_never_matches() -> None:
    zone = _square_zone("general")
    assert find_matching_zone(_bbox_inside(), [zone]) is None


def test_no_match_when_outside_all_zones() -> None:
    zone = _square_zone("perimeter")
    assert find_matching_zone(_bbox_outside(), [zone]) is None


def test_no_zones_configured_means_no_match() -> None:
    assert find_matching_zone(_bbox_inside(), []) is None
