import datetime as dt
import uuid

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("severity in ('critical','high','medium','low')", name="ck_events_severity"),
        CheckConstraint("status in ('active','reviewing','resolved')", name="ck_events_status"),
        {"schema": "events"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Cross-service reference (DB Spec §6: no physical FK across schemas).
    # DB Spec §3 types this `uuid` (camera.cameras.id), but every actual
    # producer in the running pipeline -- Redis streams, tracking-service's
    # TrackEvent, camera-service's own public `id` field -- uses the
    # external_id string as "the" camera id throughout (see CameraRead's own
    # docstring: "the id the frontend/rest of the pipeline uses everywhere").
    # Storing that same string here (not the internal UUID) matches the
    # established convention and avoids an unused extra resolve-to-UUID
    # round-trip on every single event write. Documented deviation.
    camera_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    camera_name: Mapped[str] = mapped_column(String, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    object_type: Mapped[str | None] = mapped_column(String, nullable=True)
    severity: Mapped[str] = mapped_column(String, nullable=False, index=True)
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Denormalized alongside snapshot_id (same rationale as camera_name/
    # location above) so `GET /events/{id}` never needs a live call to
    # Media Storage Service just to resolve a URL it was already handed
    # once, at capture time (M7).
    snapshot_url: Mapped[str | None] = mapped_column(String, nullable=True)
    # Phase 2 M23: same denormalization rationale as snapshot_id/url above.
    # Null until the background post-roll capture (recording_client.py)
    # completes, which happens after this row already exists -- set via
    # `EventRepository.set_recording` from that background task, not at
    # creation time.
    recording_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    recording_url: Mapped[str | None] = mapped_column(String, nullable=True)
    requires_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Phase 2 M14 Direction Analysis: one of 8 compass buckets (N/NE/E/SE/S/
    # SW/W/NW), set only for event_type='Direction Observed' rows. Not
    # exposed on the public API -- analytics-service reads it directly via
    # its own sanctioned cross-schema SQL (same pattern as every other
    # materialized view there), so no schema/API surface is needed here.
    direction: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
