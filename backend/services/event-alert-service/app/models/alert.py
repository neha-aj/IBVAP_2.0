import datetime as dt
import uuid

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint("severity in ('critical','high','medium','low')", name="ck_alerts_severity"),
        CheckConstraint("status in ('active','reviewing','resolved')", name="ck_alerts_status"),
        {"schema": "events"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # See `models/event.py::Event.camera_id` -- stores the external_id
    # string, matching the convention used throughout the running pipeline.
    camera_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    camera_name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    object_type: Mapped[str | None] = mapped_column(String, nullable=True)
    severity: Mapped[str] = mapped_column(String, nullable=False, index=True)
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    # Copied from the originating Event's `description` (both are built from
    # the same `EventDraft` in pubsub_publisher.py) -- previously alerts had
    # no description at all, an asymmetry with Event that the frontend
    # papered over with a generated placeholder sentence.
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    # Phase 2 M23: mirrors Event.recording_id/url -- denormalized here too
    # (not just on Event) since AlertDetails is this project's actually-
    # wired detail view (Events' own equivalent is an unfinished
    # placeholder); set by the same background capture task once it
    # completes, same as Event's copy.
    recording_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    recording_url: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active", index=True)
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    acknowledged_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
