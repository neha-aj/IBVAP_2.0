"""add direction to events, current_queue_zone_id to tracks

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-06

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("events", sa.Column("direction", sa.String(), nullable=True), schema="events")
    op.add_column("tracks", sa.Column("current_queue_zone_id", sa.String(), nullable=True), schema="events")


def downgrade() -> None:
    op.drop_column("tracks", "current_queue_zone_id", schema="events")
    op.drop_column("events", "direction", schema="events")
