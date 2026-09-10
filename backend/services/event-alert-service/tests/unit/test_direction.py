from app.rules.direction import average_heading, compass_bucket
from app.schemas.internal import Point


def test_average_heading_none_with_fewer_than_two_points() -> None:
    assert average_heading([]) is None
    assert average_heading([Point(x=0, y=0)]) is None


def test_average_heading_is_mean_displacement() -> None:
    positions = [Point(x=0, y=0), Point(x=2, y=0), Point(x=4, y=0)]
    dx, dy = average_heading(positions)
    assert (dx, dy) == (2.0, 0.0)


def test_compass_bucket_east() -> None:
    assert compass_bucket(dx=10, dy=0) == "E"


def test_compass_bucket_north_is_decreasing_y() -> None:
    assert compass_bucket(dx=0, dy=-10) == "N"


def test_compass_bucket_south_is_increasing_y() -> None:
    assert compass_bucket(dx=0, dy=10) == "S"


def test_compass_bucket_west() -> None:
    assert compass_bucket(dx=-10, dy=0) == "W"


def test_compass_bucket_diagonal_northeast() -> None:
    assert compass_bucket(dx=10, dy=-10) == "NE"


def test_compass_bucket_stationary_defaults_to_north() -> None:
    assert compass_bucket(dx=0, dy=0) == "N"
