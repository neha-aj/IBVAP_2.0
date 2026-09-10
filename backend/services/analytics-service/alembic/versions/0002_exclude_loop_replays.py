"""exclude looped-video replays from daily/hourly activity counts

A short test video looping (`loop_file_sources=true`, the default for
`file`-type cameras) makes the tracker lose continuity on every restart and
assign fresh track ids to the same recurring people/vehicles -- inflating
`peopleDetectedToday`/`vehiclesDetectedToday`/the hourly activity chart by
roughly one full recount per loop. `events.tracks.loop_generation` (0 for a
live source or a file source's first play-through, incrementing per loop
after that) lets these two views filter replays out, with zero effect on
real (non-looping) cameras, which never have a nonzero value here.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-06

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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
