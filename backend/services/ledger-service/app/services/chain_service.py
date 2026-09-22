"""The append-only, hash-chained anchor log itself. Each entry's hash
covers its own fields plus the previous entry's hash, and is signed with
this service's own key -- so proving an anchor is genuine means recomputing
the chain AND checking the signature, not just trusting a database row.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.anchor import Anchor, ChainTip
from app.security.signing import sign_entry_hash

GENESIS_HASH = "0" * 64
_TIP_ID = 1
_ENTRY_PREFIX = b"NI7-LEDGER/1\0"


def _entry_hash(
    *, prev_hash: str, record_type: str, record_id: uuid.UUID, content_hash: str, created_at: dt.datetime
) -> str:
    payload = _ENTRY_PREFIX + "\0".join(
        [prev_hash, record_type, str(record_id), content_hash, created_at.isoformat()]
    ).encode()
    return hashlib.sha256(payload).hexdigest()


async def anchor(
    session: AsyncSession, *, key_root: str, record_type: str, record_id: uuid.UUID, content_hash: str
) -> Anchor:
    tip = (await session.execute(select(ChainTip).where(ChainTip.id == _TIP_ID).with_for_update())).scalar_one()

    created_at = dt.datetime.now(dt.UTC)
    entry_hash = _entry_hash(
        prev_hash=tip.entry_hash, record_type=record_type, record_id=record_id,
        content_hash=content_hash, created_at=created_at,
    )
    signature = sign_entry_hash(key_root=key_root, entry_hash=entry_hash)

    entry = Anchor(
        record_type=record_type, record_id=record_id, content_hash=content_hash,
        prev_hash=tip.entry_hash, entry_hash=entry_hash, signature=signature, created_at=created_at,
    )
    session.add(entry)
    tip.entry_hash = entry_hash
    tip.updated_at = created_at
    await session.commit()
    return entry


async def latest_anchor(session: AsyncSession, *, record_type: str, record_id: uuid.UUID) -> Anchor | None:
    result = await session.execute(
        select(Anchor)
        .where(Anchor.record_type == record_type, Anchor.record_id == record_id)
        .order_by(Anchor.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def verify_chain(session: AsyncSession) -> tuple[bool, int, str | None]:
    """Same shape/purpose as media-service's own `audit_log_service.verify_chain`."""
    result = await session.execute(select(Anchor).order_by(Anchor.created_at))
    entries = list(result.scalars().all())

    prev_hash = GENESIS_HASH
    for entry in entries:
        expected = _entry_hash(
            prev_hash=prev_hash, record_type=entry.record_type, record_id=entry.record_id,
            content_hash=entry.content_hash, created_at=entry.created_at,
        )
        if entry.prev_hash != prev_hash or entry.entry_hash != expected:
            return False, len(entries), str(entry.id)
        prev_hash = entry.entry_hash

    return True, len(entries), None
