"""M25: TOTP-based MFA columns on users

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
    op.add_column("users", sa.Column("mfa_secret", sa.String(), nullable=True), schema="auth")
    op.add_column(
        "users", sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()), schema="auth"
    )


def downgrade() -> None:
    op.drop_column("users", "mfa_enabled", schema="auth")
    op.drop_column("users", "mfa_secret", schema="auth")
