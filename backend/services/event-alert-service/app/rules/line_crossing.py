"""Line Crossing rule (Phase 2 doc09 §1.2): fires when a track's centroid
trajectory crosses a configured line segment between consecutive track
updates. Pure geometry -- the engine owns "what was the previous centroid"
bookkeeping so this stays trivially testable, same as `zone_crossing.py`.

Direction convention: a line has two endpoints, A and B. Walking from A to
B, "a_to_b" is crossed when the track moves from the side of the line where
`cross(B-A, P-A) > 0` to the side where it's `< 0`; "b_to_a" is the reverse.
This is an arbitrary but fixed and testable convention -- it does not encode
any real-world compass direction, only a consistent side-of-line flip.
"""

from __future__ import annotations

from app.schemas.internal import Point


def _cross(o: Point, a: Point, b: Point) -> float:
    return (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x)


def _orientation(a: Point, b: Point, c: Point) -> int:
    val = _cross(a, b, c)
    if val > 0:
        return 1
    if val < 0:
        return -1
    return 0


def segments_intersect(p1: Point, p2: Point, a: Point, b: Point) -> bool:
    """Standard orientation-based segment-segment intersection test. Exact
    collinear overlaps are treated as no-crossing -- a measure-zero edge
    case for floating-point tracker positions, not worth the extra branches
    a fully general test would need."""
    o1 = _orientation(p1, p2, a)
    o2 = _orientation(p1, p2, b)
    o3 = _orientation(a, b, p1)
    o4 = _orientation(a, b, p2)
    return o1 != o2 and o3 != o4 and o1 != 0 and o2 != 0 and o3 != 0 and o4 != 0


def crossing_direction(a: Point, b: Point, prev: Point, curr: Point) -> str:
    """Which way the track crossed line A-B, per this module's documented
    convention. Only meaningful when `segments_intersect` is True for the
    same four points."""
    return "a_to_b" if _cross(a, b, prev) > 0 else "b_to_a"
