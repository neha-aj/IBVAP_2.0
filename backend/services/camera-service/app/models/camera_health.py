import datetime as dt
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CameraHealth(Base):
    """Heartbeat history written by the Stream Ingestion Service (M3).
    Not populated yet in M2 -- table exists now so M3 has nothing to migrate."""

    __tablename__ = "camera_health"
    __table_args__ = {"schema": "camera"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    camera_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("camera.cameras.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String, nullable=False)
    fps: Mapped[int] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=True)
    checked_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
