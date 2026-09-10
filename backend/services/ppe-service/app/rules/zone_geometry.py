"""Pure polygon geometry -- duplicated from event-alert-service's own
`rules/zone_crossing.py` rather than shared, per Implementation Guide §3
("no service imports another service's package")."""

from __future__ import annotations

from app.schemas.internal import BoundingBox, Point, Zone


def bbox_center(bbox: BoundingBox) -> tuple[float, float]:
    return bbox.x + bbox.width / 2, bbox.y + bbox.height / 2


def point_in_polygon(x: float, y: float, polygon: list[Point]) -> bool:
    """Standard ray-casting point-in-polygon test. Coordinates and polygon
    are both in the same percentage-of-frame space -- units don't matter
    for this algorithm, only that both sides agree, which they do here."""
    inside = False
    n = len(polygon)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i].x, polygon[i].y
        xj, yj = polygon[j].x, polygon[j].y
        if (yi > y) != (yj > y):
            x_intersect = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_intersect:
                inside = not inside
        j = i
    return inside


def any_zone_requires_ppe(bbox: BoundingBox, zones: list[Zone]) -> bool:
    """doc09 §2.8: "a PPE rule only applies in zones marked as requiring
    it" -- true if this track's bbox center falls inside any zone opted
    into `requires_ppe`, regardless of that zone's `zone_type`."""
    cx, cy = bbox_center(bbox)
    return any(zone.requires_ppe and point_in_polygon(cx, cy, zone.polygon) for zone in zones)
