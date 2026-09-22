import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ibvap_common.errors import NotFoundError
from ibvap_common.internal_auth import verify_internal_token

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.anchor import AnchorRead, AnchorRequest, ChainIntegrity, LedgerVerification
from app.services import chain_service

router = APIRouter(prefix="/ledger", tags=["ledger"])


@router.post("/anchor", response_model=AnchorRead, status_code=201, dependencies=[Depends(verify_internal_token)])
async def create_anchor(
    payload: AnchorRequest,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AnchorRead:
    """M25 blockchain-style anchoring: records `content_hash` for
    (record_type, record_id) as the next link in this service's own
    independent, signed hash chain. Internal-only -- called by media-
    service right after it signs a new snapshot/recording."""
    try:
        record_id = uuid.UUID(payload.record_id)
    except ValueError:
        raise NotFoundError(f"Invalid record id {payload.record_id}") from None

    entry = await chain_service.anchor(
        session, key_root=settings.ledger_key_root, record_type=payload.record_type,
        record_id=record_id, content_hash=payload.content_hash,
    )
    return AnchorRead(id=str(entry.id), entry_hash=entry.entry_hash, signature=entry.signature, created_at=entry.created_at)


@router.get("/verify", response_model=LedgerVerification, dependencies=[Depends(verify_internal_token)])
async def verify_anchor(
    record_type: str = Query(alias="recordType"),
    record_id: str = Query(alias="recordId"),
    content_hash: str = Query(alias="contentHash"),
    session: AsyncSession = Depends(get_db),
) -> LedgerVerification:
    """Whether `content_hash` matches what's anchored for this record --
    `not_anchored` (nothing anchored yet), `mismatch` (something else was
    anchored, i.e. the hash media-service holds today disagrees with the
    independent copy), or `anchored`. Internal-only, called by
    media-service's own `/verify` route."""
    try:
        parsed_id = uuid.UUID(record_id)
    except ValueError:
        raise NotFoundError(f"Invalid record id {record_id}") from None

    latest = await chain_service.latest_anchor(session, record_type=record_type, record_id=parsed_id)
    if latest is None:
        return LedgerVerification(status="not_anchored")
    if latest.content_hash != content_hash:
        return LedgerVerification(status="mismatch", entry_hash=latest.entry_hash, anchored_at=latest.created_at)
    return LedgerVerification(status="anchored", entry_hash=latest.entry_hash, anchored_at=latest.created_at)


@router.get("/verify-chain", response_model=ChainIntegrity, dependencies=[Depends(verify_internal_token)])
async def verify_chain(session: AsyncSession = Depends(get_db)) -> ChainIntegrity:
    intact, checked, broken_id = await chain_service.verify_chain(session)
    return ChainIntegrity(intact=intact, entries_checked=checked, first_broken_entry_id=broken_id)
