"""initial events schema: tracks, events, alerts

Revision ID: 0001
Revises:
Create Date: 2026-09-05

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS events")
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        "tracks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("camera_id", sa.String(), nullable=False),
        sa.Column("track_ref", sa.String(), nullable=False),
        sa.Column("object_type", sa.String(), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.CheckConstraint("status in ('active','lost')", name="ck_tracks_status"),
        schema="events",
    )
    op.create_index("ix_events_tracks_camera_id", "tracks", ["camera_id"], schema="events")
    op.create_index("ix_events_tracks_track_ref", "tracks", ["track_ref"], schema="events")

    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                   server_default=sa.text("gen_random_uuid()")),
        sa.Column("camera_id", sa.String(), nullable=False),
        sa.Column("camera_name", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("object_type", sa.String(), nullable=True),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("requires_review", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("severity in ('critical','high','medium','low')", name="ck_events_severity"),
        sa.CheckConstraint("status in ('active','reviewing','resolved')", name="ck_events_status"),
        schema="events",
    )
    op.create_index("ix_events_events_camera_id", "events", ["camera_id"], schema="events")
    op.create_index("ix_events_events_event_type", "events", ["event_type"], schema="events")
    op.create_index("ix_events_events_severity", "events", ["severity"], schema="events")
    op.create_index("ix_events_events_created_at", "events", ["created_at"], schema="events")

    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                   server_default=sa.text("gen_random_uuid()")),
        sa.Column("event_id", postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("events.events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("camera_id", sa.String(), nullable=False),
        sa.Column("camera_name", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("object_type", sa.String(), nullable=True),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("acknowledged_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("severity in ('critical','high','medium','low')", name="ck_alerts_severity"),
        sa.CheckConstraint("status in ('active','reviewing','resolved')", name="ck_alerts_status"),
        schema="events",
    )
    op.create_index("ix_events_alerts_camera_id", "alerts", ["camera_id"], schema="events")
    op.create_index("ix_events_alerts_severity", "alerts", ["severity"], schema="events")
    op.create_index("ix_events_alerts_status", "alerts", ["status"], schema="events")
    op.create_index("ix_events_alerts_created_at", "alerts", ["created_at"], schema="events")


def downgrade() -> None:
    op.drop_table("alerts", schema="events")
    op.drop_table("events", schema="events")
    op.drop_table("tracks", schema="events")
