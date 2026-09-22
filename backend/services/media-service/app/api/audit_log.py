import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ibvap_common.auth import TokenPayload, require_role
from ibvap_common.errors import NotFoundError

from app.db.session import get_db
from app.schemas.audit_log import AuditLogEntryRead, AuditLogRead, ChainIntegrity
from app.services import audit_log_service

router = APIRouter(prefix="/media/audit-log", tags=["audit-log"])

_VALID_RECORD_TYPES = {"snapshot", "recording"}


@router.get("/verify-chain", response_model=ChainIntegrity)
async def verify_chain(
    session: AsyncSession = Depends(get_db),
    _user: TokenPayload = Depends(require_role("admin")),
) -> ChainIntegrity:
    """M25: recomputes the entire chain-of-custody log from genesis and
    reports whether it's still intact -- i.e. whether any past entry has
    been edited, deleted, or reordered since it was written."""
    intact, checked, broken_id = await audit_log_service.verify_chain(session)
    return ChainIntegrity(intact=intact, entries_checked=checked, first_broken_entry_id=broken_id)


@router.get("/{record_type}/{record_id}", response_model=AuditLogRead)
async def get_audit_log(
    record_type: str,
    record_id: str,
    session: AsyncSession = Depends(get_db),
    _user: TokenPayload = Depends(require_role("admin")),
) -> AuditLogRead:
    """M25: every recorded view/download/verify of one snapshot or
    recording, oldest first -- the chain-of-custody trail for that piece
    of evidence."""
    if record_type not in _VALID_RECORD_TYPES:
        raise NotFoundError(f"Unknown record type {record_type}")
    try:
        parsed_id = uuid.UUID(record_id)
    except ValueError:
        raise NotFoundError(f"No {record_type} with id {record_id}") from None

    entries = await audit_log_service.entries_for_record(session, record_type=record_type, record_id=parsed_id)
    return AuditLogRead(
        record_type=record_type,
        record_id=record_id,
        entries=[
            AuditLogEntryRead(
                id=str(e.id), record_type=e.record_type, record_id=str(e.record_id), action=e.action,
                actor=e.actor, result=e.result, entry_hash=e.entry_hash, created_at=e.created_at,
            )
            for e in entries
        ],
    )
