"""Reads the materialized views (fast, pre-aggregated) plus two small live
tables (`camera.cameras`, `events.alerts` filtered to `status='active'`) --
those two are cheap, low-cardinality lookups, not the "raw detections/events"
bulk scans SAS §11 warns against pre-aggregating around."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class AnalyticsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def camera_status_counts(self) -> dict[str, int]:
        result = await self._session.execute(
            text("SELECT status, count(*) AS n FROM camera.cameras GROUP BY status")
        )
        counts = {row.status: row.n for row in result}
        return {
            "online": counts.get("online", 0),
            "warning": counts.get("warning", 0),
            "offline": counts.get("offline", 0),
            "total": sum(counts.values()),
        }

    async def active_alert_counts(self) -> dict[str, int]:
        result = await self._session.execute(
            text(
                "SELECT count(*) AS active, "
                "count(*) FILTER (WHERE severity = 'critical') AS critical "
                "FROM events.alerts WHERE status = 'active'"
            )
        )
        row = result.one()
        return {"active": row.active, "critical": row.critical}

    async def people_vehicles_by_camera(self, day: dt.date) -> list[tuple[str, int, int]]:
        result = await self._session.execute(
            text(
                "SELECT camera_id, person_count, vehicle_count "
                "FROM analytics.mv_people_vehicles_by_camera WHERE day = :day"
            ),
            {"day": day},
        )
        return [(row.camera_id, row.person_count, row.vehicle_count) for row in result]

    async def daily_counters(self, day: dt.date) -> dict[str, int]:
        result = await self._session.execute(
            text(
                "SELECT people_detected, vehicles_detected, events_count, "
                "alerts_count, critical_alerts_count "
                "FROM analytics.mv_daily_counters WHERE day = :day"
            ),
            {"day": day},
        )
        row = result.one_or_none()
        if row is None:
            return {
                "people_detected": 0, "vehicles_detected": 0, "events_count": 0,
                "alerts_count": 0, "critical_alerts_count": 0,
            }
        return dict(row._mapping)

    async def average_events_count(self, *, before: dt.date, trailing_days: int) -> float:
        """Baseline for `eventsTodayDeltaPct` -- mean `events_count` over the
        `trailing_days` before `before` (today isn't included in its own
        baseline)."""
        result = await self._session.execute(
            text(
                "SELECT COALESCE(avg(events_count), 0) AS avg_events "
                "FROM analytics.mv_daily_counters "
                "WHERE day >= :start AND day < :before"
            ),
            {"before": before, "start": before - dt.timedelta(days=trailing_days)},
        )
        return float(result.scalar_one())

    async def activity_by_hour(self, day: dt.date) -> list[tuple[str, int]]:
        result = await self._session.execute(
            text(
                "SELECT hour_bucket, count FROM analytics.mv_activity_by_hour "
                "WHERE day = :day ORDER BY hour_bucket"
            ),
            {"day": day},
        )
        return [(row.hour_bucket, row.count) for row in result]

    async def activity_by_weekday(self) -> list[tuple[str, int]]:
        """Not one of DB Spec §5's five named views -- a live GROUP BY over
        the already-tiny `mv_daily_counters` (one row per day ever
        recorded), so it's still fast without needing a sixth materialized
        view for what's a cheap derived query."""
        result = await self._session.execute(
            text(
                "SELECT to_char(day, 'Dy') AS weekday, extract(isodow FROM day) AS dow, "
                "sum(people_detected + vehicles_detected) AS total "
                "FROM analytics.mv_daily_counters GROUP BY weekday, dow ORDER BY dow"
            )
        )
        return [(row.weekday, int(row.total)) for row in result]

    async def alerts_by_type(self) -> list[tuple[str, int]]:
        result = await self._session.execute(
            text("SELECT type, count FROM analytics.mv_alerts_by_type ORDER BY count DESC")
        )
        return [(row.type, row.count) for row in result]

    async def camera_uptime(self) -> list[tuple[str, float]]:
        result = await self._session.execute(
            text("SELECT camera_name, uptime_pct FROM analytics.mv_camera_uptime ORDER BY camera_name")
        )
        return [(row.camera_name, float(row.uptime_pct)) for row in result]

    async def events_by_camera(self) -> list[tuple[str, int]]:
        result = await self._session.execute(
            text("SELECT camera_name, count FROM analytics.mv_events_by_camera ORDER BY count DESC")
        )
        return [(row.camera_name, row.count) for row in result]

    async def ppe_violations_by_camera(self) -> list[tuple[str, int]]:
        """Phase 2 M21 PPE Detection compliance panel -- see
        `mv_ppe_violations_by_camera`'s own migration docstring for why this
        is camera-level, not zone-level."""
        result = await self._session.execute(
            text("SELECT camera_name, count FROM analytics.mv_ppe_violations_by_camera ORDER BY count DESC")
        )
        return [(row.camera_name, row.count) for row in result]

    async def direction_flow(self, camera_id: str | None) -> list[tuple[str, int]]:
        """Phase 2 M14 Direction Analysis -- summed across cameras unless
        `camera_id` narrows it to one, matching the compass-rose/stacked-bar
        widget doc09 §1.2 describes (a single aggregate view, not a
        per-camera breakdown)."""
        if camera_id is not None:
            result = await self._session.execute(
                text(
                    "SELECT direction, count FROM analytics.mv_direction_flow "
                    "WHERE camera_id = :camera_id ORDER BY direction"
                ),
                {"camera_id": camera_id},
            )
        else:
            result = await self._session.execute(
                text(
                    "SELECT direction, sum(count) AS count FROM analytics.mv_direction_flow "
                    "GROUP BY direction ORDER BY direction"
                )
            )
        return [(row.direction, int(row.count)) for row in result]

    async def queue_status(self, camera_id: str) -> list[dict]:
        """Phase 2 M14 Queue Detection -- deliberately a live query, not a
        materialized view: queue length/dwell time needs to reflect *right
        now*, not a stale up-to-60s-old snapshot. Still one of the "small
        live table" reads this repository's own docstring already sanctions
        (filtered to one camera's active tracks currently in a queue zone --
        cheap, low-cardinality, nothing like the bulk raw-table scans SAS
        §11 warns against). Joins `camera.zones` (cross-schema, same
        sanctioned exception) only for the zone's display name."""
        result = await self._session.execute(
            text(
                "SELECT t.current_queue_zone_id AS zone_id, "
                "       COALESCE(z.name, 'Unknown zone') AS zone_name, "
                "       count(*) AS count, "
                "       avg(extract(epoch FROM (now() - t.first_seen))) AS avg_dwell_seconds "
                "FROM events.tracks t "
                "LEFT JOIN camera.zones z ON z.id::text = t.current_queue_zone_id "
                "WHERE t.status = 'active' AND t.camera_id = :camera_id "
                "  AND t.current_queue_zone_id IS NOT NULL "
                "GROUP BY t.current_queue_zone_id, z.name"
            ),
            {"camera_id": camera_id},
        )
        return [
            {
                "zone_id": row.zone_id,
                "zone_name": row.zone_name,
                "count": row.count,
                "avg_dwell_seconds": round(float(row.avg_dwell_seconds), 1),
            }
            for row in result
        ]
