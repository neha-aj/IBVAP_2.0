from app.core.dashboard_stats import build_dashboard_stats


def _daily(**overrides) -> dict:
    base = {"people_detected": 0, "vehicles_detected": 0, "events_count": 0}
    base.update(overrides)
    return base


def test_active_cameras_and_offline_always_sum_to_total() -> None:
    """Regression test: a `warning`-status camera used to be counted in
    neither activeCameras nor camerasOffline, so the two never summed to
    totalCameras -- caught live when a real camera in `warning` state made
    the Dashboard show activeCameras=0, camerasOffline=0, totalCameras=1."""
    cameras = {"online": 2, "warning": 1, "offline": 1, "total": 4}

    stats = build_dashboard_stats(
        cameras=cameras, alerts={"active": 0, "critical": 0}, daily=_daily(), avg_events=0
    )

    assert stats["activeCameras"] + stats["camerasOffline"] == stats["totalCameras"]
    assert stats["activeCameras"] == 3  # online + warning
    assert stats["camerasOffline"] == 1


def test_all_cameras_offline() -> None:
    cameras = {"online": 0, "warning": 0, "offline": 2, "total": 2}

    stats = build_dashboard_stats(
        cameras=cameras, alerts={"active": 0, "critical": 0}, daily=_daily(), avg_events=0
    )

    assert stats["activeCameras"] == 0
    assert stats["camerasOffline"] == 2


def test_passes_through_alert_and_daily_counts() -> None:
    cameras = {"online": 1, "warning": 0, "offline": 0, "total": 1}
    daily = _daily(people_detected=5, vehicles_detected=2, events_count=10)

    stats = build_dashboard_stats(
        cameras=cameras, alerts={"active": 4, "critical": 1}, daily=daily, avg_events=5
    )

    assert stats["activeAlerts"] == 4
    assert stats["criticalAlerts"] == 1
    assert stats["peopleDetectedToday"] == 5
    assert stats["vehiclesDetectedToday"] == 2
    assert stats["eventsToday"] == 10
    assert stats["eventsTodayDeltaPct"] == 100.0  # 10 vs avg 5 -> +100%
