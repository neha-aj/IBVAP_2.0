"""initial analytics materialized views (DB Spec §5)

Reads across schemas directly (camera.cameras, camera.camera_health,
events.tracks, events.events, events.alerts) -- an explicitly sanctioned
exception to the usual per-service-schema isolation, per SAS §3's own
architecture table ("Analytics Service | ... | Postgres (reads across
schemas via views)"). Every other service resolves cross-service data via
API calls; this one is the one place that doesn't, because bulk
aggregation over raw pipeline tables via repeated API calls per row simply
isn't practical, and read-only cross-schema SQL views carry none of the
coupling risk a cross-schema *write* or foreign key would.

Each view needs a unique index to support `REFRESH MATERIALIZED VIEW
CONCURRENTLY` (SAS §5), which doesn't lock reads during refresh.

Revision ID: 0001
Revises:
Create Date: 2026-09-05

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS analytics")

    # --- mv_daily_counters(day, people_detected, vehicles_detected,
    #     events_count, alerts_count, critical_alerts_count) ---
    # People/vehicles are counted from `events.tracks` (one row per distinct
    # tracked object, keyed by first_seen) rather than raw per-frame
    # detections -- counting frames would massively overcount the same
    # person seen 5x/sec for however long they're in view.
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

    # --- mv_activity_by_hour(day, hour_bucket, count) ---
    # "Activity" = new-track starts (person + vehicle combined), per hour of
    # each day -- powers the Dashboard's hour-bucketed ActivityOverview chart
    # (API Spec §7 `?range=today` filters this view's rows to today's date
    # at query time).
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

    # --- mv_alerts_by_type(type, count) ---
    # Grouped by the rule engine's actual alert `type` values (e.g. "Fence
    # Intrusion", "Connection Lost", "Loitering Detected") -- API Spec §7's
    # own example categories ("Intrusion/Vehicle/Loitering/Other") are
    # illustrative, not a fixed enum to force real data into.
    op.execute(
        """
        CREATE MATERIALIZED VIEW analytics.mv_alerts_by_type AS
        SELECT type, count(*) AS count
        FROM events.alerts
        GROUP BY 1
        """
    )
    op.execute("CREATE UNIQUE INDEX ix_analytics_mv_alerts_by_type_type ON analytics.mv_alerts_by_type (type)")

    # --- mv_camera_uptime(camera_id, camera_name, uptime_pct) ---
    # % of heartbeats in the last 24h that weren't 'offline'. LEFT JOIN so
    # every camera appears even with zero health history yet (0% rather than
    # missing from the chart entirely).
    op.execute(
        """
        CREATE MATERIALIZED VIEW analytics.mv_camera_uptime AS
        SELECT
            c.external_id AS camera_id,
            c.name AS camera_name,
            COALESCE(
                100.0 * count(h.id) FILTER (
                    WHERE h.status != 'offline' AND h.checked_at >= now() - interval '24 hours'
                ) / NULLIF(count(h.id) FILTER (WHERE h.checked_at >= now() - interval '24 hours'), 0),
                0
            ) AS uptime_pct
        FROM camera.cameras c
        LEFT JOIN camera.camera_health h ON h.camera_id = c.id
        GROUP BY c.external_id, c.name
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX ix_analytics_mv_camera_uptime_camera_id ON analytics.mv_camera_uptime (camera_id)"
    )

    # --- mv_events_by_camera(camera_id, camera_name, count) ---
    op.execute(
        """
        CREATE MATERIALIZED VIEW analytics.mv_events_by_camera AS
        SELECT camera_id, camera_name, count(*) AS count
        FROM events.events
        GROUP BY camera_id, camera_name
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX ix_analytics_mv_events_by_camera_camera_id "
        "ON analytics.mv_events_by_camera (camera_id)"
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS analytics.mv_events_by_camera")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS analytics.mv_camera_uptime")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS analytics.mv_alerts_by_type")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS analytics.mv_activity_by_hour")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS analytics.mv_daily_counters")
