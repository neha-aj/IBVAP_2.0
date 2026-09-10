import datetime as dt
import uuid

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class WatchlistEntry(Base):
    """`anpr.watchlist` (Phase 2 doc09 §2.1) -- a plate read matching one of
    these escalates from `low` to `critical` severity."""

    __tablename__ = "watchlist"
    __table_args__ = {"schema": "anpr"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plate_text: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    # References auth-service's users table by id -- no physical FK across
    # services' schemas (IG §6), same convention as everywhere else.
    added_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
