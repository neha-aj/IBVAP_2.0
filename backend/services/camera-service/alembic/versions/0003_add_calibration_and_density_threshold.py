"""add calibration to cameras, density_threshold to zones

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-06

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("cameras", sa.Column("calibration", postgresql.JSONB(), nullable=True), schema="camera")
    op.add_column("zones", sa.Column("density_threshold", sa.Numeric(), nullable=True), schema="camera")


def downgrade() -> None:
    op.drop_column("zones", "density_threshold", schema="camera")
    op.drop_column("cameras", "calibration", schema="camera")
