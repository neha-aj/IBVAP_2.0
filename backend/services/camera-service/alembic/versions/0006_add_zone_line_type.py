"""add zone_lines.line_type

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-11

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable, no default -- every existing row (and every line created via
    # the old API contract) stays NULL, which `_check_line_crossing` treats
    # identically to "boundary" (today's only behavior). Only a new line
    # explicitly created with line_type="fence" behaves differently.
    op.add_column("zone_lines", sa.Column("line_type", sa.String(), nullable=True), schema="camera")


def downgrade() -> None:
    op.drop_column("zone_lines", "line_type", schema="camera")
