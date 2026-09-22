import datetime as dt
import uuid

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Anchor(Base):
    """One hash-chained, signed entry per anchored evidence hash. See
    app/services/chain_service.py for the chaining -- the same
    prev-hash-plus-fields construction media-service's own audit log uses,
    kept in this separate service/database/signing-key so a compromise of
    media-service alone can't also rewrite what was anchored here."""

    __tablename__ = "anchors"
    __table_args__ = {"schema": "ledger"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    record_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    prev_hash: Mapped[str] = mapped_column(String, nullable=False)
    entry_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    signature: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ChainTip(Base):
    """Singleton chain-tip row -- same `SELECT ... FOR UPDATE` serialization
    pattern as media-service's own AuditChainTip."""

    __tablename__ = "chain_tip"
    __table_args__ = {"schema": "ledger"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_hash: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
