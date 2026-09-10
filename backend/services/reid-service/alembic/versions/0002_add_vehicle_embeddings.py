"""add vehicle_embeddings (Phase 2 M17)

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-06

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Must match app/models/embedding_dimension.py -- both tables are populated
# by the same ResNet-50 backbone in this deployment (see vehicle_embedding.py
# and embedder.py's own documented reasoning).
_EMBEDDING_DIMENSION = 2048


def upgrade() -> None:
    op.create_table(
        "vehicle_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                   server_default=sa.text("gen_random_uuid()")),
        sa.Column("track_id", sa.String(), nullable=False),
        sa.Column("camera_id", sa.String(), nullable=False),
        sa.Column("embedding", Vector(_EMBEDDING_DIMENSION), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="reid",
    )
    op.create_index("ix_reid_vehicle_embeddings_track_id", "vehicle_embeddings", ["track_id"], schema="reid")
    op.create_index("ix_reid_vehicle_embeddings_camera_id", "vehicle_embeddings", ["camera_id"], schema="reid")
    # No ANN index -- same 2000-dim HNSW/IVFFLAT cap vs. this table's 2048-dim
    # embeddings as 0001's person_embeddings; see that migration's comment.


def downgrade() -> None:
    op.drop_table("vehicle_embeddings", schema="reid")
