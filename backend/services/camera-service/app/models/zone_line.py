import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ZoneLine(Base):
    """Line-segment definitions per camera (Phase 2 doc09 §1.1) -- for rules
    a polygon can't express: Line Crossing and Wrong-Way Detection both need
    a two-point line plus an allowed-direction vector, not an enclosed area.
    Kept as its own table rather than shoehorned into `zones` because a line
    isn't a polygon."""

    __tablename__ = "zone_lines"
    __table_args__ = {"schema": "camera"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    camera_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("camera.cameras.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    point_a: Mapped[dict] = mapped_column(JSONB, nullable=False)  # {"x":.., "y":..} normalized 0-100
    point_b: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Per doc09 §1.1's table spec exactly: `direction text`. Optional
    # allowed-direction label for Wrong-Way Detection (M14, e.g. "a_to_b" /
    # "b_to_a"); nullable because Line Crossing (M13) doesn't need one.
    direction: Mapped[str | None] = mapped_column(String, nullable=True)
    # Fence Climbing Detection (behavioral analytics): nullable, defaults to
    # NULL ("boundary" -- an ordinary line-crossing/wrong-way line, today's
    # only behavior). Only "fence" changes anything -- see event-alert-
    # service's `rules/engine.py::_check_line_crossing` -- so every line
    # created before this column existed keeps behaving exactly as before.
    line_type: Mapped[str | None] = mapped_column(String, nullable=True)
