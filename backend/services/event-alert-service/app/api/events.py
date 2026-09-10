import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ibvap_common.auth import TokenPayload, require_role
from ibvap_common.errors import NotFoundError

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.repositories.event_repo import EventRepository
from app.schemas.event import EventDetail, EventListResponse, EventUpdate, to_event_detail, to_event_read

router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.get("", response_model=EventListResponse)
async def list_events(
    camera: str | None = Query(default=None),
    event_type: str | None = Query(default=None, alias="eventType"),
    severity: str | None = Query(default=None),
    status: str | None = Query(default=None),
    date: str | None = Query(default=None, description="YYYY-MM-DD, filters events created on that date"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200, alias="pageSize"),
    session: AsyncSession = Depends(get_db),
    _user: TokenPayload = Depends(require_role("viewer")),
) -> EventListResponse:
    date_from = date_to = None
    if date:
        day = dt.datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=dt.UTC)
        date_from, date_to = day, day + dt.timedelta(days=1)

    rows, total = await EventRepository(session).list_paginated(
        camera_id=camera, event_type=event_type, severity=severity, status=status,
        date_from=date_from, date_to=date_to, page=page, page_size=page_size,
    )
    return EventListResponse(
        items=[to_event_read(row) for row in rows], total=total, page=page, page_size=page_size
    )


@router.get("/{event_id}", response_model=EventDetail)
async def get_event(
    event_id: str,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _user: TokenPayload = Depends(require_role("viewer")),
) -> EventDetail:
    event = await EventRepository(session).get_by_id(event_id)
    if event is None:
        raise NotFoundError(f"No event with id {event_id}")
    return to_event_detail(event, settings)


@router.patch("/{event_id}", response_model=EventDetail)
async def update_event(
    event_id: str,
    payload: EventUpdate,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _user: TokenPayload = Depends(require_role("operator")),
) -> EventDetail:
    repo = EventRepository(session)
    event = await repo.get_by_id(event_id)
    if event is None:
        raise NotFoundError(f"No event with id {event_id}")
    event = await repo.update_status(event, payload.status)
    return to_event_detail(event, settings)
