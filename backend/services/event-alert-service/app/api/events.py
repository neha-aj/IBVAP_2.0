import datetime as dt
import time

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ibvap_common.auth import TokenPayload, require_role
from ibvap_common.errors import NotFoundError

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.repositories.event_repo import EventRepository
from app.schemas.event import (
    CameraOption,
    EventDetail,
    EventFilterOptions,
    EventListResponse,
    EventUpdate,
    ValueCount,
    to_event_detail,
    to_event_read,
)

router = APIRouter(prefix="/api/v1/events", tags=["events"])

# The dropdown options are a handful of GROUP BYs over the whole events
# table; a short in-process cache keeps repeated page loads cheap without
# letting the list go meaningfully stale.
_OPTIONS_TTL_SECONDS = 15.0
_SEVERITY_ORDER = ["critical", "high", "medium", "low"]
_options_cache: tuple[float, EventFilterOptions] | None = None


@router.get("", response_model=EventListResponse)
async def list_events(
    camera: str | None = Query(default=None),
    event_type: str | None = Query(default=None, alias="eventType"),
    severity: str | None = Query(default=None),
    status: str | None = Query(default=None),
    date: str | None = Query(default=None, description="YYYY-MM-DD, filters events created on that date"),
    date_from: dt.datetime | None = Query(
        default=None, alias="dateFrom", description="Events created at or after this instant (ISO 8601)."
    ),
    date_to: dt.datetime | None = Query(
        default=None, alias="dateTo", description="Events created at or before this instant (ISO 8601)."
    ),
    has_recording: bool | None = Query(
        default=None, alias="hasRecording",
        description="Evidence page: filter to only events with an attached recording clip.",
    ),
    page: int = Query(default=1, ge=1),
    # Ceiling raised from 200 so an export can fetch a large filtered set in
    # a few requests; the default (50) is unchanged for every existing caller.
    page_size: int = Query(default=50, ge=1, le=1000, alias="pageSize"),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _user: TokenPayload = Depends(require_role("viewer")),
) -> EventListResponse:
    # An explicit from/to range takes precedence over the single-day `date`.
    if date and date_from is None and date_to is None:
        day = dt.datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=dt.UTC)
        date_from, date_to = day, day + dt.timedelta(days=1)

    rows, total = await EventRepository(session).list_paginated(
        camera_id=camera, event_type=event_type, severity=severity, status=status,
        date_from=date_from, date_to=date_to, has_recording=has_recording, page=page, page_size=page_size,
    )
    return EventListResponse(
        items=[to_event_read(row, settings, subject=_user.username) for row in rows],
        total=total, page=page, page_size=page_size,
    )


@router.get("/filter-options", response_model=EventFilterOptions)
async def filter_options(
    session: AsyncSession = Depends(get_db),
    _user: TokenPayload = Depends(require_role("viewer")),
) -> EventFilterOptions:
    """Choices for the Events page's camera / event type / severity
    dropdowns. Declared before `/{event_id}` so "filter-options" isn't
    read as an event id."""
    global _options_cache
    now = time.monotonic()
    if _options_cache is not None and now - _options_cache[0] < _OPTIONS_TTL_SECONDS:
        return _options_cache[1]

    raw = await EventRepository(session).filter_options()
    by_severity = {value: count for value, count in raw["severities"]}
    options = EventFilterOptions(
        cameras=[CameraOption(id=cid, name=name, count=count) for cid, name, count in raw["cameras"]],
        event_types=[ValueCount(value=value, count=count) for value, count in raw["event_types"]],
        severities=[ValueCount(value=s, count=by_severity.get(s, 0)) for s in _SEVERITY_ORDER],
    )
    _options_cache = (now, options)
    return options


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
    return to_event_detail(event, settings, subject=_user.username)


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
