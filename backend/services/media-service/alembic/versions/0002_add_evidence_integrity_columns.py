"""M25: tamper-evident hash + signature columns for snapshots/recordings

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-23

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("snapshots", sa.Column("content_hash", sa.String(), nullable=True), schema="media")
    op.add_column("snapshots", sa.Column("signature", sa.String(), nullable=True), schema="media")
    op.add_column("recordings", sa.Column("content_hash", sa.String(), nullable=True), schema="media")
    op.add_column("recordings", sa.Column("signature", sa.String(), nullable=True), schema="media")


def downgrade() -> None:
    op.drop_column("recordings", "signature", schema="media")
    op.drop_column("recordings", "content_hash", schema="media")
    op.drop_column("snapshots", "signature", schema="media")
    op.drop_column("snapshots", "content_hash", schema="media")
