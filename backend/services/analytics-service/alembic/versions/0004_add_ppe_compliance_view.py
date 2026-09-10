"""add mv_ppe_violations_by_camera materialized view (Phase 2 M21 PPE Detection)

Reads `events.events` filtered to `event_type = 'PPE Violation'` -- the rows
ppe-service's internal-event-contract reports produce. All-time count, same
as `mv_events_by_camera`'s own precedent (not a rolling window like
`mv_camera_uptime`/`mv_direction_flow` -- a compliance trend is meant to
accumulate, not reset). Grouped by camera only, not by zone: `events.events`
has no `zone_id` column (every zone-scoped rule in this codebase only ever
encodes the zone name into free-text `description`, never a queryable
column -- see event-alert-service's own `rules/engine.py`), so a true
per-zone breakdown isn't available without a schema change beyond this
milestone's own `camera.zones.requires_ppe` addition. Documented scope
decision, not an oversight.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-07

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE MATERIALIZED VIEW analytics.mv_ppe_violations_by_camera AS
        SELECT camera_id, camera_name, count(*) AS count
        FROM events.events
        WHERE event_type = 'PPE Violation'
        GROUP BY camera_id, camera_name
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX ix_analytics_mv_ppe_violations_by_camera_camera_id "
        "ON analytics.mv_ppe_violations_by_camera (camera_id)"
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS analytics.mv_ppe_violations_by_camera")
