import datetime as dt
import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.embedding_dimension import EMBEDDING_DIMENSION


class VehicleEmbedding(Base):
    """`reid.vehicle_embeddings` (Phase 2 doc09 §2.3 Vehicle Re-ID): "identical
    architecture to §2.2 (same reid-service, a second model + a second
    embedding table), filtered to object_type=vehicle". Column-for-column
    identical to `PersonEmbedding` -- see that model's own docstring for why
    this stays a separate table rather than a shared one with a
    discriminator.

    doc11 §2's primary recommendation for this table is a vehicle-specific
    Re-ID embedding network; its own documented fallback is "reuse a general
    image-embedding model...as a lower-accuracy stopgap" when no such model
    exists for this deployment (true here, same situation M16 was in for
    the person table). Rather than adding a second heavy runtime dependency
    (e.g. CLIP) for that fallback, this reuses the exact same general-purpose
    ResNet-50 extractor already loaded for person embeddings (embedder.py) --
    it's a plain, non-person-specific image embedding, so it satisfies the
    same "general image embedding as stopgap" intent doc11 describes, without
    a second model in memory."""

    __tablename__ = "vehicle_embeddings"
    __table_args__ = {"schema": "reid"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    track_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    camera_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSION), nullable=False)
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
