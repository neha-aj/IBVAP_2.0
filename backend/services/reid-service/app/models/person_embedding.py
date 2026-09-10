import datetime as dt
import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.embedding_dimension import EMBEDDING_DIMENSION


class PersonEmbedding(Base):
    """`reid.person_embeddings` (Phase 2 doc09 §2.2). Vehicle Re-ID (M17)
    adds a second table (`vehicle_embeddings`, see `vehicle_embedding.py`),
    not a `type` column here -- doc09 §2.3 describes person and vehicle
    Re-ID as independent architectures (potentially different models
    entirely), so a shared table with a discriminator would couple two
    things that only coincidentally have the same shape today. In this
    deployment both tables happen to be populated by the same ResNet-50
    backbone (see embedder.py's own documented reasoning), but the schema
    doesn't assume that stays true."""

    __tablename__ = "person_embeddings"
    __table_args__ = {"schema": "reid"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # doc09's own table spec types this `bigint` (events.tracks.id) --
    # stored as the tracker's own track_ref string instead, matching the
    # established, already-documented deviation every cross-service
    # camera_id/track_id column in this codebase uses (this service has no
    # access to event-alert-service's internal bigint PK without a cross-
    # service call per embedding, which isn't worth it for an id that's
    # never actually joined against here).
    track_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    camera_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSION), nullable=False)
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
