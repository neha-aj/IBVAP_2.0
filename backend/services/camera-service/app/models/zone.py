import uuid

from sqlalchemy import Boolean, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Zone(Base):
    """Polygon zones per camera, consumed by the Event/Alert Service rule
    engine (SAS §5.4) for intrusion/restricted-zone rules. Not yet exposed
    via API or UI in M2 -- table created now so M6 needs no migration."""

    __tablename__ = "zones"
    __table_args__ = {"schema": "camera"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    camera_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("camera.cameras.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    polygon: Mapped[list] = mapped_column(JSONB, nullable=False)  # [{"x":.., "y":..}, ...] normalized 0-100
    # "queue" added Phase 2 M14 (Queue Detection) -- no DB CHECK constraint
    # on this column, only the Pydantic ZoneType Literal enforces the enum.
    zone_type: Mapped[str] = mapped_column(String, nullable=False, default="general")
    # Phase 2 M14 Crowd Density: opt-in per zone (null = density alerting
    # disabled for this zone) -- people-per-polygon-area threshold.
    density_threshold: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    # Phase 2 M21 PPE Detection: opt-in per zone (doc09 §2.8 -- "a PPE rule
    # only applies in zones marked as requiring it, e.g. a construction
    # area, not an office reception zone"). Read directly by ppe-service via
    # the same internal zones endpoint the rule engine already uses.
    requires_ppe: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
