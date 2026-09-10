import datetime as dt

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class TrackSummary(Base):
    """Per-track bookkeeping (DB Spec §3 `events.tracks`) -- just enough to
    drive the loitering rule's dwell-time check (`first_seen`) and give the
    rule engine a durable record of tracks across service restarts. The
    Tracking Service (M5) itself stays stateless; this is where that
    lifecycle finally gets persisted, by the service documented to own it.
    """

    __tablename__ = "tracks"
    __table_args__ = (
        CheckConstraint("status in ('active','lost')", name="ck_tracks_status"),
        {"schema": "events"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # See `models/event.py::Event.camera_id` -- external_id string.
    camera_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # ByteTrack's own per-camera track id (a small int, unique only within
    # that camera's tracker lifetime) -- kept as text since it resets/repeats
    # across camera reconnects and isn't globally unique.
    track_ref: Mapped[str] = mapped_column(String, nullable=False, index=True)
    object_type: Mapped[str] = mapped_column(String, nullable=False)
    first_seen: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    # 0 for a live source or a file source's first play-through; >0 means
    # this track was seen during a replay of a looping test video. The
    # Analytics Service (M9) excludes loop_generation > 0 rows from
    # `peopleDetectedToday`/`vehiclesDetectedToday` so a short looping test
    # clip doesn't inflate those counts once per loop.
    loop_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Phase 2 M14 Queue Detection: the "queue"-type zone (camera-service
    # Zone.id) this track is currently inside, or null. Persisted (not just
    # kept in the rule engine's in-memory state) specifically so the
    # Analytics Service can compute live queue length/dwell time with a
    # plain SQL query against this table, without a live call back into
    # this service (analytics-service never calls other services' APIs --
    # see its own migration's docstring on cross-schema reads).
    current_queue_zone_id: Mapped[str | None] = mapped_column(String, nullable=True)
