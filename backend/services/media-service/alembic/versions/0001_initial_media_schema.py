"""initial media schema: snapshots, recordings

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
    op.execute("CREATE SCHEMA IF NOT EXISTS media")
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        "snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                   server_default=sa.text("gen_random_uuid()")),
        sa.Column("camera_id", sa.String(), nullable=False),
        sa.Column("event_id", sa.String(), nullable=True),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="media",
    )
    op.create_index("ix_media_snapshots_camera_id", "snapshots", ["camera_id"], schema="media")
    op.create_index("ix_media_snapshots_event_id", "snapshots", ["event_id"], schema="media")
    op.create_index(
        "ix_media_snapshots_camera_id_created_at", "snapshots", ["camera_id", "created_at"], schema="media"
    )

    op.create_table(
        "recordings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                   server_default=sa.text("gen_random_uuid()")),
        sa.Column("camera_id", sa.String(), nullable=False),
        sa.Column("event_id", sa.String(), nullable=True),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="media",
    )
    op.create_index("ix_media_recordings_camera_id", "recordings", ["camera_id"], schema="media")
    op.create_index("ix_media_recordings_event_id", "recordings", ["event_id"], schema="media")
    op.create_index(
        "ix_media_recordings_camera_id_created_at", "recordings", ["camera_id", "created_at"], schema="media"
    )


def downgrade() -> None:
    op.drop_table("recordings", schema="media")
    op.drop_table("snapshots", schema="media")
