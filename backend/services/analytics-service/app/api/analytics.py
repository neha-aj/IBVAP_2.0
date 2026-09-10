import datetime as dt

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from ibvap_common.auth import TokenPayload, require_role

from app.core.cache import cached_json
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.redis_client import get_redis_client
from app.repositories.analytics_repo import AnalyticsRepository
from app.schemas.stats import ActivityHourPoint, CameraDailyCounts, NamedCountPoint, NamedValuePoint, QueueStatusPoint

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/activity-overview", response_model=list[ActivityHourPoint])
async def activity_overview(
    range: str = Query(default="today"),
    session: AsyncSession = Depends(get_db),
    redis_client: Redis = Depends(get_redis_client),
    settings: Settings = Depends(get_settings),
    _user: TokenPayload = Depends(require_role("viewer")),
) -> list[ActivityHourPoint]:
    """API Spec §7 -- hour-bucketed series for the Dashboard's
    `ActivityOverview` chart. Only `range=today` is meaningful today (the
    only range the underlying data is queried for); any other value still
    returns today's series rather than erroring."""

    async def compute() -> list[dict]:
        today = dt.datetime.now(dt.UTC).date()
        rows = await AnalyticsRepository(session).activity_by_hour(today)
        return [{"h": h, "v": v} for h, v in rows]

    data = await cached_json(redis_client, f"analytics:activity-overview:{range}", settings.cache_ttl_seconds, compute)
    return [ActivityHourPoint(**item) for item in data]


@router.get("/activity-weekly", response_model=list[NamedValuePoint])
async def activity_weekly(
    session: AsyncSession = Depends(get_db),
    redis_client: Redis = Depends(get_redis_client),
    settings: Settings = Depends(get_settings),
    _user: TokenPayload = Depends(require_role("viewer")),
) -> list[NamedValuePoint]:
    """API Spec §7 -- bar chart, activity count per weekday, for `ActivityChart`."""

    async def compute() -> list[dict]:
        rows = await AnalyticsRepository(session).activity_by_weekday()
        return [{"name": name, "value": value} for name, value in rows]

    data = await cached_json(redis_client, "analytics:activity-weekly", settings.cache_ttl_seconds, compute)
    return [NamedValuePoint(**item) for item in data]


@router.get("/alerts-by-type", response_model=list[NamedValuePoint])
async def alerts_by_type(
    session: AsyncSession = Depends(get_db),
    redis_client: Redis = Depends(get_redis_client),
    settings: Settings = Depends(get_settings),
    _user: TokenPayload = Depends(require_role("viewer")),
) -> list[NamedValuePoint]:
    """API Spec §7 -- pie chart, alert count by category, for `AlertChart`."""

    async def compute() -> list[dict]:
        rows = await AnalyticsRepository(session).alerts_by_type()
        return [{"name": name, "value": value} for name, value in rows]

    data = await cached_json(redis_client, "analytics:alerts-by-type", settings.cache_ttl_seconds, compute)
    return [NamedValuePoint(**item) for item in data]


@router.get("/camera-uptime", response_model=list[NamedValuePoint])
async def camera_uptime(
    session: AsyncSession = Depends(get_db),
    redis_client: Redis = Depends(get_redis_client),
    settings: Settings = Depends(get_settings),
    _user: TokenPayload = Depends(require_role("viewer")),
) -> list[NamedValuePoint]:
    """API Spec §7 -- per-camera uptime %, for `CameraAnalytics`."""

    async def compute() -> list[dict]:
        rows = await AnalyticsRepository(session).camera_uptime()
        return [{"name": name, "value": round(pct, 1)} for name, pct in rows]

    data = await cached_json(redis_client, "analytics:camera-uptime", settings.cache_ttl_seconds, compute)
    return [NamedValuePoint(**item) for item in data]


@router.get("/events-by-camera", response_model=list[NamedCountPoint])
async def events_by_camera(
    session: AsyncSession = Depends(get_db),
    redis_client: Redis = Depends(get_redis_client),
    settings: Settings = Depends(get_settings),
    _user: TokenPayload = Depends(require_role("viewer")),
) -> list[NamedCountPoint]:
    """API Spec §7 -- inline "Events by camera" list."""

    async def compute() -> list[dict]:
        rows = await AnalyticsRepository(session).events_by_camera()
        return [{"name": name, "count": count} for name, count in rows]

    data = await cached_json(redis_client, "analytics:events-by-camera", settings.cache_ttl_seconds, compute)
    return [NamedCountPoint(**item) for item in data]


@router.get("/people-vehicles-by-camera", response_model=list[CameraDailyCounts])
async def people_vehicles_by_camera(
    session: AsyncSession = Depends(get_db),
    redis_client: Redis = Depends(get_redis_client),
    settings: Settings = Depends(get_settings),
    _user: TokenPayload = Depends(require_role("viewer")),
) -> list[CameraDailyCounts]:
    """Per-camera breakdown of the same person/vehicle totals the Dashboard
    shows summed across all cameras -- for Live Surveillance's per-tile
    "today" count."""

    async def compute() -> list[dict]:
        today = dt.datetime.now(dt.UTC).date()
        rows = await AnalyticsRepository(session).people_vehicles_by_camera(today)
        return [
            {"cameraId": camera_id, "personCount": person_count, "vehicleCount": vehicle_count}
            for camera_id, person_count, vehicle_count in rows
        ]

    data = await cached_json(
        redis_client, "analytics:people-vehicles-by-camera", settings.cache_ttl_seconds, compute
    )
    return [CameraDailyCounts(**item) for item in data]


@router.get("/ppe-compliance", response_model=list[NamedCountPoint])
async def ppe_compliance(
    session: AsyncSession = Depends(get_db),
    redis_client: Redis = Depends(get_redis_client),
    settings: Settings = Depends(get_settings),
    _user: TokenPayload = Depends(require_role("viewer")),
) -> list[NamedCountPoint]:
    """Phase 2 M21 PPE Detection -- violation count by camera, for the
    Analytics compliance panel."""

    async def compute() -> list[dict]:
        rows = await AnalyticsRepository(session).ppe_violations_by_camera()
        return [{"name": name, "count": count} for name, count in rows]

    data = await cached_json(redis_client, "analytics:ppe-compliance", settings.cache_ttl_seconds, compute)
    return [NamedCountPoint(**item) for item in data]


@router.get("/direction-flow", response_model=list[NamedValuePoint])
async def direction_flow(
    camera: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
    redis_client: Redis = Depends(get_redis_client),
    settings: Settings = Depends(get_settings),
    _user: TokenPayload = Depends(require_role("viewer")),
) -> list[NamedValuePoint]:
    """Phase 2 M14 Direction Analysis -- compass-bucketed movement flow over
    the last hour, for a compass-rose/stacked-bar widget."""

    async def compute() -> list[dict]:
        rows = await AnalyticsRepository(session).direction_flow(camera)
        return [{"name": direction, "value": count} for direction, count in rows]

    cache_key = f"analytics:direction-flow:{camera or 'all'}"
    data = await cached_json(redis_client, cache_key, settings.cache_ttl_seconds, compute)
    return [NamedValuePoint(**item) for item in data]


@router.get("/queue-length", response_model=list[QueueStatusPoint])
async def queue_length(
    camera: str = Query(...),
    session: AsyncSession = Depends(get_db),
    _user: TokenPayload = Depends(require_role("viewer")),
) -> list[QueueStatusPoint]:
    """Phase 2 M14 Queue Detection -- live (uncached, unlike every other
    endpoint here) count + average dwell time per `queue`-type zone on this
    camera, one entry per currently-occupied queue zone."""
    rows = await AnalyticsRepository(session).queue_status(camera)
    return [QueueStatusPoint(**row) for row in rows]
