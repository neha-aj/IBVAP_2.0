"""initial anpr schema: plate_reads, watchlist (Phase 2 M15)

Revision ID: 0001
Revises:
Create Date: 2026-09-06

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
    op.execute("CREATE SCHEMA IF NOT EXISTS anpr")
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        "watchlist",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                   server_default=sa.text("gen_random_uuid()")),
        sa.Column("plate_text", sa.String(), nullable=False, unique=True),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("added_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="anpr",
    )
    op.create_index("ix_anpr_watchlist_plate_text", "watchlist", ["plate_text"], schema="anpr", unique=True)

    op.create_table(
        "plate_reads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                   server_default=sa.text("gen_random_uuid()")),
        sa.Column("camera_id", sa.String(), nullable=False),
        sa.Column("track_id", sa.String(), nullable=True),
        sa.Column("plate_text", sa.String(), nullable=False),
        sa.Column("confidence", sa.Numeric(), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("watchlist_match", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="anpr",
    )
    op.create_index("ix_anpr_plate_reads_camera_id", "plate_reads", ["camera_id"], schema="anpr")
    op.create_index("ix_anpr_plate_reads_plate_text", "plate_reads", ["plate_text"], schema="anpr")


def downgrade() -> None:
    op.drop_table("plate_reads", schema="anpr")
    op.drop_table("watchlist", schema="anpr")
