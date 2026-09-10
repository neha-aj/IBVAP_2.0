"""Pure aggregation logic for `GET /dashboard/stats`, split out from the API
handler so the camera-status bucketing (the source of a real bug: a
`warning`-status camera counted in neither `activeCameras` nor
`camerasOffline`, so the two never summed to `totalCameras`) has a direct
unit test instead of only being reachable through a live HTTP call."""

from __future__ import annotations

from app.core.deltas import compute_delta_pct


def build_dashboard_stats(
    *, cameras: dict[str, int], alerts: dict[str, int], daily: dict[str, int], avg_events: float
) -> dict:
    events_today = daily["events_count"]
    return {
        # "Active" = still transmitting, i.e. not offline (online OR
        # warning -- a degraded-fps camera is still up, just struggling).
        "activeCameras": cameras["online"] + cameras["warning"],
        "totalCameras": cameras["total"],
        "camerasOffline": cameras["offline"],
        "activeAlerts": alerts["active"],
        "criticalAlerts": alerts["critical"],
        "peopleDetectedToday": daily["people_detected"],
        "vehiclesDetectedToday": daily["vehicles_detected"],
        "eventsToday": events_today,
        "eventsTodayDeltaPct": round(compute_delta_pct(events_today, avg_events), 1),
    }
