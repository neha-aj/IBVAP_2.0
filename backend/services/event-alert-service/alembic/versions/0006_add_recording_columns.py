"""add recording_id/recording_url to events and alerts (Phase 2 M23)

Recording clip capture is best-effort and happens in a background task
after the event/alert rows already exist (see recording_client.py's own
docstring for why it can't run inline like snapshot capture does) -- both
columns start null and get backfilled once capture completes, exactly
like snapshot_id/snapshot_url's own precedent on events.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-08

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("events", sa.Column("recording_id", postgresql.UUID(as_uuid=True), nullable=True), schema="events")
    op.add_column("events", sa.Column("recording_url", sa.String(), nullable=True), schema="events")
    op.add_column("alerts", sa.Column("recording_id", postgresql.UUID(as_uuid=True), nullable=True), schema="events")
    op.add_column("alerts", sa.Column("recording_url", sa.String(), nullable=True), schema="events")


def downgrade() -> None:
    op.drop_column("alerts", "recording_url", schema="events")
    op.drop_column("alerts", "recording_id", schema="events")
    op.drop_column("events", "recording_url", schema="events")
    op.drop_column("events", "recording_id", schema="events")
