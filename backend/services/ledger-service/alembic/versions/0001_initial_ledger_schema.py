"""initial ledger schema: anchors, chain_tip

Revision ID: 0001
Revises:
Create Date: 2026-09-23

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GENESIS_HASH = "0" * 64


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS ledger")
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        "anchors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                   server_default=sa.text("gen_random_uuid()")),
        sa.Column("record_type", sa.String(), nullable=False),
        sa.Column("record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("prev_hash", sa.String(), nullable=False),
        sa.Column("entry_hash", sa.String(), nullable=False, unique=True),
        sa.Column("signature", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="ledger",
    )
    op.create_index("ix_ledger_anchors_record_type", "anchors", ["record_type"], schema="ledger")
    op.create_index("ix_ledger_anchors_record_id", "anchors", ["record_id"], schema="ledger")

    op.create_table(
        "chain_tip",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entry_hash", sa.String(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        schema="ledger",
    )
    op.execute(
        f"INSERT INTO ledger.chain_tip (id, entry_hash, updated_at) VALUES (1, '{_GENESIS_HASH}', now())"
    )


def downgrade() -> None:
    op.drop_table("chain_tip", schema="ledger")
    op.drop_table("anchors", schema="ledger")
