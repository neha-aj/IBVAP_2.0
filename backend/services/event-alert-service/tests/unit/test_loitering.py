import datetime as dt

from app.rules.loitering import has_exceeded_dwell_time


def test_under_threshold_not_loitering() -> None:
    first_seen = dt.datetime(2026, 1, 1, 12, 0, 0, tzinfo=dt.UTC)
    now = first_seen + dt.timedelta(seconds=10)
    assert has_exceeded_dwell_time(first_seen, now, threshold_seconds=30) is False


def test_over_threshold_is_loitering() -> None:
    first_seen = dt.datetime(2026, 1, 1, 12, 0, 0, tzinfo=dt.UTC)
    now = first_seen + dt.timedelta(seconds=31)
    assert has_exceeded_dwell_time(first_seen, now, threshold_seconds=30) is True
