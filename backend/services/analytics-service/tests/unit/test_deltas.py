from app.core.deltas import compute_delta_pct


def test_above_average_is_positive() -> None:
    assert compute_delta_pct(current=15, average=10) == 50.0


def test_below_average_is_negative() -> None:
    assert compute_delta_pct(current=5, average=10) == -50.0


def test_equal_to_average_is_zero() -> None:
    assert compute_delta_pct(current=10, average=10) == 0.0


def test_zero_average_does_not_divide_by_zero() -> None:
    assert compute_delta_pct(current=5, average=0) == 0.0


def test_negative_average_treated_as_no_baseline() -> None:
    assert compute_delta_pct(current=5, average=-1) == 0.0
