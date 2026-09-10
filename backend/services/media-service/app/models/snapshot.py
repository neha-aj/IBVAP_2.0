import datetime as dt
import uuid

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Snapshot(Base):
    __tablename__ = "snapshots"
    __table_args__ = {"schema": "media"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # String, not uuid -- matches the external_id/event-id-as-string
    # convention established in event-alert-service (M6) for the same
    # reason: these are cross-schema references (DB Spec §6), and every
    # producer that will ever hand this service a camera_id/event_id
    # already uses those id-strings, not the internal Postgres UUIDs.
    camera_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    event_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # A URL path resolvable under nginx's static `/media/` alias, not a raw
    # filesystem path (SAS §5.5.3).
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
