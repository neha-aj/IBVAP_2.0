import datetime as dt
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ibvap_common.auth import TokenPayload, require_role
from ibvap_common.errors import NotFoundError
from ibvap_common.stream_auth import build_resource_url

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.watchlist import WatchlistEntry
from app.repositories.plate_read_repo import PlateReadRepository
from app.repositories.watchlist_repo import WatchlistRepository
from app.schemas.plate_read import PlateReadListResponse, PlateReadRead
from app.schemas.watchlist import WatchlistCreate, WatchlistRead

router = APIRouter(prefix="/api/v1/anpr", tags=["anpr"])


def _to_plate_read(row, settings: Settings) -> PlateReadRead:
    snapshot_id = str(row.snapshot_id) if row.snapshot_id else None
    return PlateReadRead(
        id=str(row.id),
        camera_id=row.camera_id,
        track_id=row.track_id,
        plate_text=row.plate_text,
        confidence=float(row.confidence),
        snapshot_id=snapshot_id,
        snapshot_url=build_resource_url(path=f"/media/snapshots/{snapshot_id}", resource=snapshot_id, settings=settings)
        if snapshot_id
        else None,
        watchlist_match=row.watchlist_match,
        created_at=row.created_at,
    )


def _to_watchlist_read(row: WatchlistEntry) -> WatchlistRead:
    return WatchlistRead(id=str(row.id), plate_text=row.plate_text, reason=row.reason, created_at=row.created_at)


@router.get("/reads", response_model=PlateReadListResponse)
async def list_plate_reads(
    camera: str | None = Query(default=None),
    plate: str | None = Query(default=None),
    date_from: str | None = Query(default=None, alias="from", description="YYYY-MM-DD"),
    date_to: str | None = Query(default=None, alias="to", description="YYYY-MM-DD"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200, alias="pageSize"),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _user: TokenPayload = Depends(require_role("viewer")),
) -> PlateReadListResponse:
    parsed_from = dt.datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=dt.UTC) if date_from else None
    parsed_to = dt.datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=dt.UTC) if date_to else None

    rows, total = await PlateReadRepository(session).list_paginated(
        camera_id=camera, plate=plate, date_from=parsed_from, date_to=parsed_to, page=page, page_size=page_size,
    )
    return PlateReadListResponse(
        items=[_to_plate_read(row, settings) for row in rows], total=total, page=page, page_size=page_size
    )


@router.get("/watchlist", response_model=list[WatchlistRead])
async def list_watchlist(
    session: AsyncSession = Depends(get_db),
    _user: TokenPayload = Depends(require_role("viewer")),
) -> list[WatchlistRead]:
    rows = await WatchlistRepository(session).list_all()
    return [_to_watchlist_read(row) for row in rows]


@router.post("/watchlist", response_model=WatchlistRead, status_code=201)
async def create_watchlist_entry(
    payload: WatchlistCreate,
    session: AsyncSession = Depends(get_db),
    user: TokenPayload = Depends(require_role("admin")),
) -> WatchlistRead:
    entry = await WatchlistRepository(session).create(
        WatchlistEntry(plate_text=payload.plate_text.upper(), reason=payload.reason, added_by=uuid.UUID(user.sub))
    )
    return _to_watchlist_read(entry)


@router.delete("/watchlist/{entry_id}", status_code=204)
async def delete_watchlist_entry(
    entry_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _user: TokenPayload = Depends(require_role("admin")),
) -> None:
    deleted = await WatchlistRepository(session).delete(entry_id)
    if not deleted:
        raise NotFoundError(f"No watchlist entry with id {entry_id}")
