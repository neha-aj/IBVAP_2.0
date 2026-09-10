from app.rules.line_crossing import crossing_direction, segments_intersect
from app.schemas.internal import Point


def test_segments_intersect_when_paths_cross() -> None:
    # Line A-B is horizontal at y=50; the track moves from above to below it.
    a, b = Point(x=0, y=50), Point(x=100, y=50)
    prev, curr = Point(x=50, y=10), Point(x=50, y=90)
    assert segments_intersect(prev, curr, a, b) is True


def test_segments_do_not_intersect_when_paths_dont_cross() -> None:
    a, b = Point(x=0, y=50), Point(x=100, y=50)
    prev, curr = Point(x=10, y=10), Point(x=20, y=20)  # stays above the line
    assert segments_intersect(prev, curr, a, b) is False


def test_segments_do_not_intersect_outside_the_line_segments_bounds() -> None:
    # The infinite line through A-B passes through the movement segment's
    # extension, but the actual bounded line segment (x in [0,10]) doesn't.
    a, b = Point(x=0, y=50), Point(x=10, y=50)
    prev, curr = Point(x=50, y=10), Point(x=50, y=90)
    assert segments_intersect(prev, curr, a, b) is False


def test_crossing_direction_a_to_b() -> None:
    a, b = Point(x=0, y=50), Point(x=100, y=50)
    prev, curr = Point(x=50, y=90), Point(x=50, y=10)
    assert crossing_direction(a, b, prev, curr) == "a_to_b"


def test_crossing_direction_b_to_a_is_the_reverse() -> None:
    a, b = Point(x=0, y=50), Point(x=100, y=50)
    prev, curr = Point(x=50, y=10), Point(x=50, y=90)
    assert crossing_direction(a, b, prev, curr) == "b_to_a"
