from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class DashboardStats(_CamelModel):
    """API Spec §7 `GET /dashboard/stats` exactly."""

    active_cameras: int
    total_cameras: int
    cameras_offline: int
    active_alerts: int
    critical_alerts: int
    people_detected_today: int
    vehicles_detected_today: int
    events_today: int
    events_today_delta_pct: float


class ActivityHourPoint(BaseModel):
    """`ActivityOverview` area chart: `[{h:"08:00", v:14}, ...]`."""

    h: str
    v: int


class NamedValuePoint(BaseModel):
    """Shared shape for `activity-weekly`, `alerts-by-type`, and
    `camera-uptime`: `[{name:"Mon", value:34}, ...]`."""

    name: str
    value: float


class NamedCountPoint(BaseModel):
    """`events-by-camera`: `[{name:"BOP-01", count:84}, ...]`."""

    name: str
    count: int


class CameraDailyCounts(_CamelModel):
    """`people-vehicles-by-camera`: per-camera breakdown of the same
    person/vehicle totals `DashboardStats.peopleDetectedToday`/
    `vehiclesDetectedToday` sum across all cameras."""

    camera_id: str
    person_count: int
    vehicle_count: int


class QueueStatusPoint(_CamelModel):
    """Phase 2 M14 Queue Detection: `GET /analytics/queue-length?camera=`."""

    zone_id: str
    zone_name: str
    count: int
    avg_dwell_seconds: float
