from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from ibvap_common.stream_auth import build_resource_url

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.models.event import Event

Severity = Literal["critical", "high", "medium", "low"]
EventStatus = Literal["active", "reviewing", "resolved"]


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class EventRead(_CamelModel):
    """API Spec §5 `EventTable` shape
    (`{id,time,cameraName,event,objectType,location,severity,status}`) plus
    `description` -- added so the table can show what an ambiguous
    `event` label (e.g. "Direction Observed") actually means without
    needing the still-unwired per-event detail drawer (`EventDetail`
    below)."""

    id: str
    time: dt.datetime
    camera_name: str
    event: str  # human label, e.g. "Fence Intrusion" -- DB column `event_type`
    object_type: str | None
    location: str | None
    severity: Severity
    status: EventStatus
    description: str | None
    # Phase 2 M23 -- see Alert's own equivalent field. Optional/settings-gated
    # for the same reason `to_alert_read` accepts `settings=None`: existing
    # callers (`pubsub_publisher.py`'s WS `event.new` payload) that only care
    # about persistence, not a signed playback URL, don't need to construct
    # a full `Settings` just to get one. Added here (not just EventDetail)
    # for the evidence/recordings page -- a list view needs to know which
    # rows even have a clip without a per-row detail round trip.
    recording_url: str | None = None


class EventDetail(EventRead):
    """Adds fields for the future `EventDetails` per-event drawer (Frontend
    Analysis Report §3.5)."""

    camera_id: str
    snapshot_url: str | None


class EventUpdate(_CamelModel):
    status: EventStatus


class EventListResponse(_CamelModel):
    items: list[EventRead]
    total: int
    page: int
    page_size: int


def to_event_read(event: Event, settings: Settings | None = None) -> EventRead:
    """Explicit field-by-field mapping rather than `model_validate(...,
    from_attributes=True)` -- the ORM column is `event_type`, the API field
    is `event` (API Spec §5), so generic attribute-mode validation can't
    bridge the rename anyway.

    `settings` optional (see `EventRead.recording_url`'s own docstring) --
    `event.recording_url` is a denormalized raw file path (M24 security
    review follow-up, same issue `to_event_detail` already documents below);
    only rebuilt as a short-lived signed URL when `settings` is actually
    given, same pattern as `to_alert_read`."""
    return EventRead(
        id=str(event.id),
        time=event.created_at,
        camera_name=event.camera_name,
        event=event.event_type,
        object_type=event.object_type,
        location=event.location,
        severity=event.severity,  # type: ignore[arg-type]
        status=event.status,  # type: ignore[arg-type]
        description=event.description,
        recording_url=build_resource_url(
            path=f"/media/recordings/{event.recording_id}/file", resource=str(event.recording_id), settings=settings
        )
        if event.recording_id and settings
        else None,
    )


def to_event_detail(event: Event, settings: Settings) -> EventDetail:
    """`event.snapshot_url`/`event.recording_url` are denormalized raw file
    paths captured at event-creation time -- convenient for the DB, but
    (M24 security review follow-up) fetchable with zero auth if handed to
    the frontend verbatim, since they point at nginx's static alias
    directly rather than through either by-id route's own token check.
    Rebuilt here as short-lived signed URLs instead, from the stored ids,
    each time this event is actually read (a token baked in once at
    capture time could easily have expired by the time anyone views an
    old event)."""
    base = to_event_read(event, settings)
    return EventDetail(
        # recording_url excluded from the spread -- EventRead already
        # carries it (built above via `base`'s own `settings`), so keeping
        # it in the spread here would pass it twice (once from `**`, once
        # explicitly) and error. Re-declared below instead, only for
        # readability/parity with snapshot_url's own explicit build.
        **base.model_dump(exclude={"recording_url"}),
        camera_id=event.camera_id,
        snapshot_url=build_resource_url(
            path=f"/media/snapshots/{event.snapshot_id}", resource=str(event.snapshot_id), settings=settings
        )
        if event.snapshot_id
        else None,
        recording_url=base.recording_url,
    )
