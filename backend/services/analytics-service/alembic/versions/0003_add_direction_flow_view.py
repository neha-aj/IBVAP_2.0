"""add mv_direction_flow materialized view (Phase 2 M14 Direction Analysis)

Reads `events.events` filtered to `event_type = 'Direction Observed'` --
the informational, non-alerting rows event-alert-service's Direction
Analysis rule writes (one of 8 compass buckets, see its own `direction`
column docstring). Windowed to the last hour rather than all-time, same
reasoning as `mv_camera_uptime`'s own 24h window: a raw all-time count would
never reflect *current* flow, only ever-growing historical totals.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-06

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE MATERIALIZED VIEW analytics.mv_direction_flow AS
        SELECT
            camera_id,
            camera_name,
            direction,
            count(*) AS count
        FROM events.events
        WHERE event_type = 'Direction Observed'
          AND direction IS NOT NULL
          AND created_at >= now() - interval '1 hour'
        GROUP BY camera_id, camera_name, direction
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX ix_analytics_mv_direction_flow_camera_direction "
        "ON analytics.mv_direction_flow (camera_id, direction)"
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS analytics.mv_direction_flow")
