"""M25 chain-of-custody: an append-only, hash-chained log of who viewed,
downloaded, or verified a piece of evidence, and when.

Each entry's hash covers its own fields *and* the previous entry's hash
(the same chaining idea as NI-7's MMR leaves, or a minimal blockchain) --
so altering or deleting a past row breaks every hash after it. `verify_chain`
recomputes the whole chain from genesis and says exactly where it first
breaks, if anywhere. This is a single, service-local chain (not a
distributed ledger); services/ledger-service provides the independent,
separately-keyed anchor that survives even a compromise of this database
(see that service's own module docstring).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditChainTip, AuditLogEntry

GENESIS_HASH = "0" * 64
_TIP_ID = 1
_ENTRY_PREFIX = b"NI7-AUDIT/1\0"


def _entry_hash(
    *, prev_hash: str, record_type: str, record_id: uuid.UUID, action: str,
    actor: str | None, result: str | None, created_at: dt.datetime,
) -> str:
    payload = _ENTRY_PREFIX + "\0".join(
        [prev_hash, record_type, str(record_id), action, actor or "", result or "", created_at.isoformat()]
    ).encode()
    return hashlib.sha256(payload).hexdigest()


async def append_audit_entry(
    session: AsyncSession,
    *,
    record_type: str,
    record_id: uuid.UUID,
    action: str,
    actor: str | None,
    result: str | None,
) -> AuditLogEntry:
    """Appends one entry to the chain. `SELECT ... FOR UPDATE` on the tip
    row serializes concurrent appends onto a single, unforked chain --
    without it, two simultaneous requests could both read the same "latest"
    hash and each produce a valid-looking but conflicting next link."""
    tip = (
        await session.execute(select(AuditChainTip).where(AuditChainTip.id == _TIP_ID).with_for_update())
    ).scalar_one()

    created_at = dt.datetime.now(dt.UTC)
    entry_hash = _entry_hash(
        prev_hash=tip.entry_hash, record_type=record_type, record_id=record_id, action=action,
        actor=actor, result=result, created_at=created_at,
    )
    entry = AuditLogEntry(
        record_type=record_type, record_id=record_id, action=action, actor=actor, result=result,
        prev_hash=tip.entry_hash, entry_hash=entry_hash, created_at=created_at,
    )
    session.add(entry)
    tip.entry_hash = entry_hash
    tip.updated_at = created_at
    await session.commit()
    return entry


async def entries_for_record(session: AsyncSession, *, record_type: str, record_id: uuid.UUID) -> list[AuditLogEntry]:
    result = await session.execute(
        select(AuditLogEntry)
        .where(AuditLogEntry.record_type == record_type, AuditLogEntry.record_id == record_id)
        .order_by(AuditLogEntry.created_at)
    )
    return list(result.scalars().all())


async def verify_chain(session: AsyncSession) -> tuple[bool, int, str | None]:
    """Recomputes the whole chain from genesis. Returns
    `(intact, entries_checked, first_broken_entry_id)`. `intact=False`
    means some entry's stored hash doesn't match what its own fields (and
    the entry before it) recompute to -- i.e. something in the log was
    edited, deleted, or reordered after being written."""
    result = await session.execute(select(AuditLogEntry).order_by(AuditLogEntry.created_at))
    entries = list(result.scalars().all())

    prev_hash = GENESIS_HASH
    for entry in entries:
        expected = _entry_hash(
            prev_hash=prev_hash, record_type=entry.record_type, record_id=entry.record_id, action=entry.action,
            actor=entry.actor, result=entry.result, created_at=entry.created_at,
        )
        if entry.prev_hash != prev_hash or entry.entry_hash != expected:
            return False, len(entries), str(entry.id)
        prev_hash = entry.entry_hash

    return True, len(entries), None
