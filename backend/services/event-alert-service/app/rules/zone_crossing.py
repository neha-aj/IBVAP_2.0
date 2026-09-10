"""Pure polygon geometry used by `intrusion.py` and the Zone Entry/Exit rule
(Phase 2 M13) -- kept separate per the documented project structure
(`rules/{intrusion.py,zone_crossing.py}`) since zone/polygon math is
reusable beyond just the intrusion rule."""

from __future__ import annotations

from app.schemas.internal import BoundingBox, Point, Zone


def bbox_center(bbox: BoundingBox) -> tuple[float, float]:
    return bbox.x + bbox.width / 2, bbox.y + bbox.height / 2


def point_in_polygon(x: float, y: float, polygon: list[Point]) -> bool:
    """Standard ray-casting point-in-polygon test. Coordinates and polygon
    are both in the same percentage-of-frame space (SAS §5.2/§5.4) -- units
    don't matter for this algorithm, only that both sides agree, which they
    do here."""
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


def find_general_zone(bbox: BoundingBox, zones: list[Zone]) -> Zone | None:
    """The Zone Entry/Exit rule (M13) deliberately only watches `general`
    zones -- `restricted`/`perimeter` zones already get their own entry-only
    alert from `intrusion.py` (`Fence Intrusion`/`Restricted Zone Entry`);
    watching them here too would double-fire on the same physical event."""
    cx, cy = bbox_center(bbox)
    for zone in zones:
        if zone.zone_type != "general":
            continue
        if point_in_polygon(cx, cy, zone.polygon):
            return zone
    return None


def find_queue_zone(bbox: BoundingBox, zones: list[Zone]) -> Zone | None:
    """Queue Detection (M14) -- same single-match pattern as
    `find_general_zone`, scoped to `queue`-type zones instead."""
    cx, cy = bbox_center(bbox)
    for zone in zones:
        if zone.zone_type != "queue":
            continue
        if point_in_polygon(cx, cy, zone.polygon):
            return zone
    return None


def zones_with_density_threshold(bbox: BoundingBox, zones: list[Zone]) -> list[Zone]:
    """Crowd Density (M14) -- unlike the other rules here, a track can count
    toward *multiple* density-monitored zones at once (they can overlap, and
    density opts in per-zone via `density_threshold` regardless of
    `zone_type`), so this returns every match rather than the first."""
    cx, cy = bbox_center(bbox)
    return [
        zone for zone in zones
        if zone.density_threshold is not None and point_in_polygon(cx, cy, zone.polygon)
    ]


def polygon_area(polygon: list[Point]) -> float:
    """Shoelace formula. Same percentage-of-frame units as everything else
    here, so the resulting "area" is in percent-of-frame-squared -- not a
    real-world unit, but consistent and sufficient for a people-per-area
    density threshold that's tuned empirically per deployment anyway."""
    n = len(polygon)
    if n < 3:
        return 0.0
    total = 0.0
    for i in range(n):
        j = (i + 1) % n
        total += polygon[i].x * polygon[j].y
        total -= polygon[j].x * polygon[i].y
    return abs(total) / 2.0
