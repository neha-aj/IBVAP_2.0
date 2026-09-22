import datetime as dt
import uuid

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class AuditLogEntry(Base):
    """M25 chain-of-custody: one row per view/download/verify of a snapshot
    or recording. Each entry's `entry_hash` covers its own fields plus the
    previous entry's hash (see app/services/audit_log_service.py), so the
    log is hash-chained the same way NI-7's own MMR construction chains
    leaves -- editing or deleting a past entry breaks every hash after it,
    which `verify_chain` (same module) detects by recomputing the chain."""

    __tablename__ = "audit_log"
    __table_args__ = {"schema": "media"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    record_type: Mapped[str] = mapped_column(String, nullable=False, index=True)  # "snapshot" | "recording"
    record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String, nullable=False)  # "view" | "download" | "verify"
    # Who, if known -- see ibvap_common.stream_auth's optional `subject`
    # param. Null for a token minted without one (nothing about this
    # feature requires attribution to function; it's best-effort).
    actor: Mapped[str | None] = mapped_column(String, nullable=True)
    result: Mapped[str | None] = mapped_column(String, nullable=True)  # e.g. a verify status
    prev_hash: Mapped[str] = mapped_column(String, nullable=False)
    entry_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditChainTip(Base):
    """Singleton row holding the current chain tip's hash. Read with
    `SELECT ... FOR UPDATE` before every append so concurrent requests
    serialize on this one row instead of racing to read "the latest entry"
    from the log table itself -- the simplest correct way to keep a single,
    unforked chain under concurrent writers."""

    __tablename__ = "audit_chain_tip"
    __table_args__ = {"schema": "media"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_hash: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
