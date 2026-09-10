"""add mv_people_vehicles_by_camera materialized view (per-camera daily
totals feature request)

Same source and per-day loop-replay exclusion as `mv_daily_counters`
(see `0005_fix_loop_replay_exclusion`'s own docstring for why this has to
be "first loop_generation observed per (camera_id, day)", not the naive
`loop_generation = 0`, on a long-running deployment) -- this view just
keeps `camera_id` in the grouping instead of collapsing it, so
`peopleDetectedToday`/`vehiclesDetectedToday` can be broken out per camera
instead of only as one platform-wide total.

No `camera_name` column: unlike `events.events`, `events.tracks` has no
denormalized camera name (see its own model docstring -- it only ever
needed `camera_id` for the loitering rule's bookkeeping). The API layer
returns bare `camera_id`; the frontend already has the full camera list
(id -> name) loaded wherever this gets displayed.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-08

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE MATERIALIZED VIEW analytics.mv_people_vehicles_by_camera AS
        WITH first_loop_per_camera_day AS (
            SELECT camera_id, date_trunc('day', first_seen)::date AS day,
                   min(loop_generation) AS min_loop_generation
            FROM events.tracks
            GROUP BY 1, 2
        )
        SELECT
            date_trunc('day', t.first_seen)::date AS day,
            t.camera_id,
            count(*) FILTER (WHERE t.object_type = 'person') AS person_count,
            count(*) FILTER (WHERE t.object_type = 'vehicle') AS vehicle_count
        FROM events.tracks t
        JOIN first_loop_per_camera_day f
            ON f.camera_id = t.camera_id
           AND f.day = date_trunc('day', t.first_seen)::date
           AND f.min_loop_generation = t.loop_generation
        GROUP BY 1, 2
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX ix_analytics_mv_people_vehicles_by_camera_day_camera "
        "ON analytics.mv_people_vehicles_by_camera (day, camera_id)"
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS analytics.mv_people_vehicles_by_camera")
