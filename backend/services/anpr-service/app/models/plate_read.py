import datetime as dt
import uuid

from sqlalchemy import Boolean, DateTime, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class PlateRead(Base):
    """`anpr.plate_reads` (Phase 2 doc09 §2.1)."""

    __tablename__ = "plate_reads"
    __table_args__ = {"schema": "anpr"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # doc09's own table spec types this `uuid` (camera.cameras.id) -- stored
    # as the external_id string instead, matching the established, already-
    # documented deviation every other cross-service camera_id column in
    # this codebase uses (see event-alert-service/app/models/event.py's own
    # docstring on this exact point).
    camera_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # `cam:{id}:detections` (what this service actually consumes, per doc09
    # §2.1) doesn't carry a track_id -- only tracking-service's downstream
    # output does. Left nullable rather than adding a second stream
    # subscription just to backfill this one column.
    track_id: Mapped[str | None] = mapped_column(String, nullable=True)
    plate_text: Mapped[str] = mapped_column(String, nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Numeric, nullable=False)
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    watchlist_match: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
