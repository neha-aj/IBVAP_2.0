import datetime as dt
import uuid

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Recording(Base):
    """Scaffolded per DB Spec §4 / project structure -- nothing in the
    pipeline triggers segment recording yet (no documented trigger exists
    for it, unlike snapshots' three documented triggers, SAS §5.5.1), so
    this table stays empty until a future milestone wires a producer. The
    read endpoint (`GET /media/recordings/{id}`) is real and works against
    this schema; it just has nothing to return today."""

    __tablename__ = "recordings"
    __table_args__ = {"schema": "media"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    camera_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    event_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    start_time: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
