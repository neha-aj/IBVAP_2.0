"""M25: key_id metadata column for future signing-key rotation

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-23

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("snapshots", sa.Column("key_id", sa.String(), nullable=True), schema="media")
    op.add_column("recordings", sa.Column("key_id", sa.String(), nullable=True), schema="media")


def downgrade() -> None:
    op.drop_column("recordings", "key_id", schema="media")
    op.drop_column("snapshots", "key_id", schema="media")
