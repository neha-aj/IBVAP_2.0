"""Runs `REFRESH MATERIALIZED VIEW CONCURRENTLY` for each view (SAS §5) on
a schedule. CONCURRENTLY refresh must run outside any transaction block (a
Postgres requirement -- it briefly holds only a lock that lets reads
continue against the old data mid-refresh), so this uses an autocommit
connection rather than a normal ORM session."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine

from ibvap_common.logging import get_logger

logger = get_logger(__name__)

_VIEWS = [
    "analytics.mv_daily_counters",
    "analytics.mv_activity_by_hour",
    "analytics.mv_alerts_by_type",
    "analytics.mv_camera_uptime",
    "analytics.mv_events_by_camera",
    "analytics.mv_direction_flow",
    "analytics.mv_ppe_violations_by_camera",
    "analytics.mv_people_vehicles_by_camera",
]


async def refresh_all_views(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        autocommit_connection = await connection.execution_options(isolation_level="AUTOCOMMIT")
        for view in _VIEWS:
            try:
                await autocommit_connection.exec_driver_sql(
                    f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}"
                )
            except Exception as exc:
                # One view failing (e.g. its unique index missing after a
                # migration hiccup) must not stop the others from refreshing.
                logger.warning("view_refresh_failed", view=view, error=str(exc))
