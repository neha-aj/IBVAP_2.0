"""initial camera schema: sectors, cameras, camera_health, zones, settings

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
    op.execute("CREATE SCHEMA IF NOT EXISTS camera")
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        "sectors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                   server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("code", sa.String(), nullable=False, unique=True),
        schema="camera",
    )

    op.create_table(
        "cameras",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                   server_default=sa.text("gen_random_uuid()")),
        sa.Column("external_id", sa.String(), nullable=False, unique=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("location", sa.String(), nullable=False),
        sa.Column("sector_id", postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("camera.sectors.id"), nullable=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="offline"),
        sa.Column("resolution", sa.String(), nullable=True),
        sa.Column("fps", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("type in ('rtsp','usb','ip','file','webcam')", name="ck_cameras_type"),
        sa.CheckConstraint("status in ('online','warning','offline')", name="ck_cameras_status"),
        schema="camera",
    )
    op.create_index("ix_camera_cameras_external_id", "cameras", ["external_id"], schema="camera")
    op.create_index("ix_camera_cameras_status", "cameras", ["status"], schema="camera")
    op.create_index("ix_camera_cameras_sector_id", "cameras", ["sector_id"], schema="camera")

    op.create_table(
        "camera_health",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                   server_default=sa.text("gen_random_uuid()")),
        sa.Column("camera_id", postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("camera.cameras.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("fps", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="camera",
    )
    op.create_index(
        "ix_camera_camera_health_camera_id_checked_at",
        "camera_health", ["camera_id", "checked_at"], schema="camera",
    )

    op.create_table(
        "zones",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                   server_default=sa.text("gen_random_uuid()")),
        sa.Column("camera_id", postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("camera.cameras.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("polygon", postgresql.JSONB(), nullable=False),
        sa.Column("zone_type", sa.String(), nullable=False, server_default="general"),
        schema="camera",
    )
    op.create_index("ix_camera_zones_camera_id", "zones", ["camera_id"], schema="camera")

    op.create_table(
        "settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                   server_default=sa.text("gen_random_uuid()")),
        sa.Column("group_name", sa.String(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("group_name", "key", name="uq_settings_group_key"),
        schema="camera",
    )


def downgrade() -> None:
    op.drop_table("settings", schema="camera")
    op.drop_table("zones", schema="camera")
    op.drop_table("camera_health", schema="camera")
    op.drop_table("cameras", schema="camera")
    op.drop_table("sectors", schema="camera")
