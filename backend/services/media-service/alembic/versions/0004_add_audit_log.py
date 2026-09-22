"""M25: chain-of-custody audit log (hash-chained)

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-23

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GENESIS_HASH = "0" * 64


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                   server_default=sa.text("gen_random_uuid()")),
        sa.Column("record_type", sa.String(), nullable=False),
        sa.Column("record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("actor", sa.String(), nullable=True),
        sa.Column("result", sa.String(), nullable=True),
        sa.Column("prev_hash", sa.String(), nullable=False),
        sa.Column("entry_hash", sa.String(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="media",
    )
    op.create_index("ix_media_audit_log_record_type", "audit_log", ["record_type"], schema="media")
    op.create_index("ix_media_audit_log_record_id", "audit_log", ["record_id"], schema="media")

    op.create_table(
        "audit_chain_tip",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entry_hash", sa.String(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        schema="media",
    )
    # Single seeded row (id=1) so `append_audit_entry` can always
    # `SELECT ... FOR UPDATE` it without a first-row special case.
    op.execute(
        f"INSERT INTO media.audit_chain_tip (id, entry_hash, updated_at) "
        f"VALUES (1, '{_GENESIS_HASH}', now())"
    )


def downgrade() -> None:
    op.drop_table("audit_chain_tip", schema="media")
    op.drop_table("audit_log", schema="media")
