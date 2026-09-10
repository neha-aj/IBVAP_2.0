import datetime as dt

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from ibvap_common.auth import TokenPayload, require_role

from app.core.cache import cached_json
from app.core.config import Settings, get_settings
from app.core.dashboard_stats import build_dashboard_stats
from app.db.session import get_db
from app.redis_client import get_redis_client
from app.repositories.analytics_repo import AnalyticsRepository
from app.schemas.stats import DashboardStats

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    session: AsyncSession = Depends(get_db),
    redis_client: Redis = Depends(get_redis_client),
    settings: Settings = Depends(get_settings),
    _user: TokenPayload = Depends(require_role("viewer")),
) -> DashboardStats:
    """API Spec §7 -- all six Dashboard `StatCard`s in one aggregate call."""

    async def compute() -> dict:
        repo = AnalyticsRepository(session)
        today = dt.datetime.now(dt.UTC).date()

        cameras = await repo.camera_status_counts()
        alerts = await repo.active_alert_counts()
        daily = await repo.daily_counters(today)
        avg_events = await repo.average_events_count(before=today, trailing_days=7)

        return build_dashboard_stats(cameras=cameras, alerts=alerts, daily=daily, avg_events=avg_events)

    data = await cached_json(redis_client, "analytics:dashboard:stats", settings.cache_ttl_seconds, compute)
    return DashboardStats(**data)
