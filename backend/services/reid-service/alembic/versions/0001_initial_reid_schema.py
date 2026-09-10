"""initial reid schema: person_embeddings (Phase 2 M16)

Revision ID: 0001
Revises:
Create Date: 2026-09-06

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EMBEDDING_DIMENSION = 2048


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS reid")
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')

    op.create_table(
        "person_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                   server_default=sa.text("gen_random_uuid()")),
        sa.Column("track_id", sa.String(), nullable=False),
        sa.Column("camera_id", sa.String(), nullable=False),
        sa.Column("embedding", Vector(_EMBEDDING_DIMENSION), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="reid",
    )
    op.create_index("ix_reid_person_embeddings_track_id", "person_embeddings", ["track_id"], schema="reid")
    op.create_index("ix_reid_person_embeddings_camera_id", "person_embeddings", ["camera_id"], schema="reid")
    # No ANN index (HNSW/IVFFLAT) yet: both cap at 2000 dimensions in this
    # pgvector version, but the ResNet-50 embedding fallback (doc11 §2,
    # embedder.py's own docstring) is 2048-dim -- over the limit either way.
    # This is fine for now: doc08 §8 only calls for an ANN index "once
    # embedding count passes ~100k", and a sequential scan (what pgvector
    # does without one) is correct, just not sped up, well below that.
    # Add one once either (a) embedding count approaches that scale, or (b)
    # a real Re-ID model with a smaller projection head (doc11's own
    # "Primary" OSNet/TorchReID recommendation, typically 512-dim) replaces
    # this fallback.


def downgrade() -> None:
    op.drop_table("person_embeddings", schema="reid")
