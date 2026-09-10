"""fix loop-replay exclusion to be per-day, not global (bugfix)

`0002_exclude_loop_replays` filtered both `mv_daily_counters` and
`mv_activity_by_hour` to `loop_generation = 0` to avoid inflating counts
from a short test clip looping many times. But `loop_generation` increments
*monotonically since the Ingestion Service last started* (camera_worker.py),
not per calendar day -- on a long-running deployment a demo file camera is
already at loop_generation in the hundreds/thousands by the time "today"
starts, so `= 0` matches nothing and every day after the first shows
`peopleDetectedToday`/`vehiclesDetectedToday`/the hourly activity chart as
completely empty. Confirmed live: `mv_daily_counters` had 0/0 for the
current day while `events.tracks` had over a hundred real person/vehicle
tracks recorded for it, all at loop_generation > 600.

Fix: dedupe to each camera's *first* loop_generation observed *within that
day* (`min(loop_generation) per (camera_id, day)`) instead of the global
constant 0 -- this keeps the original intent (one count per loop, not one
per every repeated pass through the same short clip) while actually
surfacing current-day activity on a long-running deployment.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-08

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS analytics.mv_daily_counters")
    op.execute(
        """
        CREATE MATERIALIZED VIEW analytics.mv_daily_counters AS
        WITH first_loop_per_camera_day AS (
            SELECT camera_id, date_trunc('day', first_seen)::date AS day,
                   min(loop_generation) AS min_loop_generation
            FROM events.tracks
            GROUP BY 1, 2
        ),
        tracks_agg AS (
            SELECT date_trunc('day', t.first_seen)::date AS day,
                   count(*) FILTER (WHERE t.object_type = 'person') AS people_detected,
                   count(*) FILTER (WHERE t.object_type = 'vehicle') AS vehicles_detected
            FROM events.tracks t
            JOIN first_loop_per_camera_day f
                ON f.camera_id = t.camera_id
               AND f.day = date_trunc('day', t.first_seen)::date
               AND f.min_loop_generation = t.loop_generation
            GROUP BY 1
        ),
        events_agg AS (
            SELECT date_trunc('day', created_at)::date AS day, count(*) AS events_count
            FROM events.events
            GROUP BY 1
        ),
        alerts_agg AS (
            SELECT date_trunc('day', created_at)::date AS day,
                   count(*) AS alerts_count,
                   count(*) FILTER (WHERE severity = 'critical') AS critical_alerts_count
            FROM events.alerts
            GROUP BY 1
        )
        SELECT
            COALESCE(t.day, e.day, a.day) AS day,
            COALESCE(t.people_detected, 0) AS people_detected,
            COALESCE(t.vehicles_detected, 0) AS vehicles_detected,
            COALESCE(e.events_count, 0) AS events_count,
            COALESCE(a.alerts_count, 0) AS alerts_count,
            COALESCE(a.critical_alerts_count, 0) AS critical_alerts_count
        FROM tracks_agg t
        FULL OUTER JOIN events_agg e ON e.day = t.day
        FULL OUTER JOIN alerts_agg a ON a.day = COALESCE(t.day, e.day)
        """
    )
    op.execute("CREATE UNIQUE INDEX ix_analytics_mv_daily_counters_day ON analytics.mv_daily_counters (day)")

    op.execute("DROP MATERIALIZED VIEW IF EXISTS analytics.mv_activity_by_hour")
    op.execute(
        """
        CREATE MATERIALIZED VIEW analytics.mv_activity_by_hour AS
        WITH first_loop_per_camera_day AS (
            SELECT camera_id, date_trunc('day', first_seen)::date AS day,
                   min(loop_generation) AS min_loop_generation
            FROM events.tracks
            GROUP BY 1, 2
        )
        SELECT
            date_trunc('day', t.first_seen)::date AS day,
            to_char(date_trunc('hour', t.first_seen), 'HH24:00') AS hour_bucket,
            count(*) AS count
        FROM events.tracks t
        JOIN first_loop_per_camera_day f
            ON f.camera_id = t.camera_id
           AND f.day = date_trunc('day', t.first_seen)::date
           AND f.min_loop_generation = t.loop_generation
        GROUP BY 1, 2
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX ix_analytics_mv_activity_by_hour_day_hour "
        "ON analytics.mv_activity_by_hour (day, hour_bucket)"
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS analytics.mv_activity_by_hour")
    op.execute(
        """
        CREATE MATERIALIZED VIEW analytics.mv_activity_by_hour AS
        SELECT
            date_trunc('day', first_seen)::date AS day,
            to_char(date_trunc('hour', first_seen), 'HH24:00') AS hour_bucket,
            count(*) AS count
        FROM events.tracks
        WHERE loop_generation = 0
        GROUP BY 1, 2
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX ix_analytics_mv_activity_by_hour_day_hour "
        "ON analytics.mv_activity_by_hour (day, hour_bucket)"
    )

    op.execute("DROP MATERIALIZED VIEW IF EXISTS analytics.mv_daily_counters")
    op.execute(
        """
        CREATE MATERIALIZED VIEW analytics.mv_daily_counters AS
        WITH tracks_agg AS (
            SELECT date_trunc('day', first_seen)::date AS day,
                   count(*) FILTER (WHERE object_type = 'person') AS people_detected,
                   count(*) FILTER (WHERE object_type = 'vehicle') AS vehicles_detected
            FROM events.tracks
            WHERE loop_generation = 0
            GROUP BY 1
        ),
        events_agg AS (
            SELECT date_trunc('day', created_at)::date AS day, count(*) AS events_count
            FROM events.events
            GROUP BY 1
        ),
        alerts_agg AS (
            SELECT date_trunc('day', created_at)::date AS day,
                   count(*) AS alerts_count,
                   count(*) FILTER (WHERE severity = 'critical') AS critical_alerts_count
            FROM events.alerts
            GROUP BY 1
        )
        SELECT
            COALESCE(t.day, e.day, a.day) AS day,
            COALESCE(t.people_detected, 0) AS people_detected,
            COALESCE(t.vehicles_detected, 0) AS vehicles_detected,
            COALESCE(e.events_count, 0) AS events_count,
            COALESCE(a.alerts_count, 0) AS alerts_count,
            COALESCE(a.critical_alerts_count, 0) AS critical_alerts_count
        FROM tracks_agg t
        FULL OUTER JOIN events_agg e ON e.day = t.day
        FULL OUTER JOIN alerts_agg a ON a.day = COALESCE(t.day, e.day)
        """
    )
    op.execute("CREATE UNIQUE INDEX ix_analytics_mv_daily_counters_day ON analytics.mv_daily_counters (day)")
