"""add zone_lines table

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-06

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "zone_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                   server_default=sa.text("gen_random_uuid()")),
        sa.Column("camera_id", postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("camera.cameras.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("point_a", postgresql.JSONB(), nullable=False),
        sa.Column("point_b", postgresql.JSONB(), nullable=False),
        sa.Column("direction", sa.String(), nullable=True),
        schema="camera",
    )
    op.create_index("ix_camera_zone_lines_camera_id", "zone_lines", ["camera_id"], schema="camera")


def downgrade() -> None:
    op.drop_table("zone_lines", schema="camera")
