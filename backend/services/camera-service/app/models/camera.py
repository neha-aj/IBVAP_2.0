import datetime as dt
import uuid

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Camera(Base):
    __tablename__ = "cameras"
    __table_args__ = (
        CheckConstraint(
            "type in ('rtsp','usb','ip','file','webcam','thermal','dual')", name="ck_cameras_type"
        ),
        CheckConstraint("status in ('online','warning','offline')", name="ck_cameras_status"),
        {"schema": "camera"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Human-readable, unique display id used everywhere in the frontend
    # contract (e.g. "BOP-01-CAM-01") -- see Frontend Analysis Report §5.
    external_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    location: Mapped[str] = mapped_column(String, nullable=False)
    sector_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("camera.sectors.id"), nullable=True
    )
    sector: Mapped["Sector"] = relationship(lazy="joined")  # noqa: F821

    # rtsp|usb|ip = real hardware; file = uploaded video treated as a virtual
    # camera; webcam = local capture device. All five run through the same
    # downstream pipeline (SAS §5.1, addendum for file/webcam sources).
    # M11: thermal = thermal-only source; dual = an RGB+thermal camera pair
    # sharing one logical camera row (source_url is the RGB stream,
    # thermal_source_url the thermal one).
    type: Mapped[str] = mapped_column(String, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    # M11: only set when type='dual' -- same encryption-at-rest as source_url.
    thermal_source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    # M11: 'central' (default, unchanged Phase 1/2 behavior) | 'edge' -- which
    # detection profile owns this camera (SAS M11 §7 edge deployment profile).
    deployment_mode: Mapped[str] = mapped_column(String, nullable=False, default="central")

    status: Mapped[str] = mapped_column(String, nullable=False, default="offline")
    resolution: Mapped[str | None] = mapped_column(String, nullable=True)
    fps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_active_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Phase 2 M14 Speed Estimation: {pixelDistance, realWorldMeters,
    # thresholdKmh} -- a one-time per-camera pixel-to-meter calibration.
    calibration: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
