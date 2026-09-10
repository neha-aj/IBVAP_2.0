"""add loop_generation to tracks

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-06

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tracks", sa.Column("loop_generation", sa.Integer(), nullable=False, server_default="0"), schema="events"
    )


def downgrade() -> None:
    op.drop_column("tracks", "loop_generation", schema="events")
