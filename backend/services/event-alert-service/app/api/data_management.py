"""Operator-facing data housekeeping for the Events / Alerts pages.

Nothing else in the system ever deletes events, alerts or their evidence
(snapshot images, recording clips), so on a busy camera set they grow without
bound -- most of the volume being informational events, each of which stores a
snapshot. This is the manual release valve: see what's stored, then clear
everything or just what's older than N days.

Two modes: a full reset (all events + alerts, or those older than N days,
with their evidence), and a lighter "Direction Observed images only" mode that
deletes just those events' snapshot images and keeps every event and alert.

Scope is deliberately narrow: only `events.events`, `events.alerts` and the
evidence files linked to them. Cameras, zones, settings, users and the
tracking history behind the Analytics people/vehicle counts are untouched.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from dataclasses import dataclass, field
from typing import Literal

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from ibvap_common.auth import TokenPayload, require_role
from ibvap_common.errors import ApiError, ConflictError
from ibvap_common.logging import get_logger

from app.core.config import Settings, get_settings
from app.db.session import get_db, get_session_factory
from app.models.alert import Alert
from app.models.event import Event

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/events/data", tags=["data-management"])

CONFIRMATION_WORD = "RESET"
DIRECTION_EVENT_TYPE = "Direction Observed"
# Snapshot ids handed to media-service per call in the images-only mode.
_IMAGE_BATCH = 1000


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ResetRequest(_CamelModel):
    # None = everything; N = only events/alerts (and their evidence) older
    # than N days.
    older_than_days: int | None = Field(default=None, ge=1, le=3650)
    # "direction_images": delete only the snapshot images of Direction Observed
    # events and keep every event and alert. None = the full reset above.
    only: Literal["direction_images"] | None = None
    # A typed word, not just a flag: this permanently deletes data, so a
    # stray/replayed request without it must do nothing.
    confirm: str

    @field_validator("confirm")
    @classmethod
    def _must_be_the_confirmation_word(cls, value: str) -> str:
        if value != CONFIRMATION_WORD:
            raise ValueError(f"confirm must be exactly '{CONFIRMATION_WORD}'")
        return value


class CleanupStatus(_CamelModel):
    status: str  # idle | running | done | failed
    started_at: dt.datetime | None = None
    finished_at: dt.datetime | None = None
    snapshots_removed: int = 0
    recordings_removed: int = 0
    bytes_freed: int = 0
    error: str | None = None
    # Images-only mode: how many there were to remove when it started, for a
    # "X of Y" progress display (0 for the full reset, which doesn't count).
    snapshots_total: int = 0


class DataSummary(_CamelModel):
    events: int
    alerts: int
    snapshots: int | None  # None when media-service couldn't be reached
    recordings: int | None
    # Direction Observed events that still have a snapshot image.
    direction_images: int
    oldest_event_at: dt.datetime | None
    newest_event_at: dt.datetime | None
    cleanup: CleanupStatus


class ResetResult(_CamelModel):
    events_removed: int
    alerts_removed: int
    cleanup: CleanupStatus


@dataclass
class _CleanupJob:
    """State of the background evidence-file cleanup. In-process, which is
    fine for the single event-alert-service replica; if the service restarts
    mid-cleanup the state resets to idle, and running the reset again simply
    finishes the job (it targets whatever evidence still exists)."""

    status: str = "idle"
    started_at: dt.datetime | None = None
    finished_at: dt.datetime | None = None
    snapshots_removed: int = 0
    recordings_removed: int = 0
    bytes_freed: int = 0
    error: str | None = None
    snapshots_total: int = 0
    task: asyncio.Task | None = field(default=None, repr=False)

    def public(self) -> CleanupStatus:
        return CleanupStatus(
            status=self.status, started_at=self.started_at, finished_at=self.finished_at,
            snapshots_removed=self.snapshots_removed, recordings_removed=self.recordings_removed,
            bytes_freed=self.bytes_freed, error=self.error, snapshots_total=self.snapshots_total,
        )


_job = _CleanupJob()


def compute_cutoff(now: dt.datetime, older_than_days: int | None) -> dt.datetime:
    """Everything created strictly before this instant is removed. With no
    day count it's `now` -- so evidence for events created *after* the reset
    began (the cleanup can take minutes) is never swept up."""
    if older_than_days is None:
        return now
    return now - dt.timedelta(days=older_than_days)


def _media_headers(settings: Settings) -> dict[str, str]:
    return {"X-Internal-Token": settings.internal_service_token}


async def _run_media_cleanup(settings: Settings, before: dt.datetime) -> None:
    try:
        # No overall timeout: a large backlog of evidence files can take
        # minutes to delete, and this runs in the background.
        async with httpx.AsyncClient(timeout=None) as client:
            response = await client.post(
                f"{settings.media_service_url}/internal/media/purge",
                json={"before": before.isoformat()},
                headers=_media_headers(settings),
            )
            response.raise_for_status()
            result = response.json()
        _job.snapshots_removed = result.get("snapshotsRemoved", 0)
        _job.recordings_removed = result.get("recordingsRemoved", 0)
        _job.bytes_freed = result.get("bytesFreed", 0)
        _job.status = "done"
    except Exception as exc:  # noqa: BLE001 -- surfaced to the operator via the status, not raised
        logger.warning("evidence_cleanup_failed", error=str(exc))
        _job.status = "failed"
        _job.error = str(exc) or exc.__class__.__name__
    finally:
        _job.finished_at = dt.datetime.now(dt.UTC)


def _direction_images_filter(before: dt.datetime | None):
    conditions = [Event.event_type == DIRECTION_EVENT_TYPE, Event.snapshot_id.is_not(None)]
    if before is not None:
        conditions.append(Event.created_at < before)
    return conditions


async def _run_direction_image_cleanup(settings: Settings, before: dt.datetime | None) -> None:
    """Deletes the snapshot images of Direction Observed events, a batch at a
    time: media-service removes the files/rows, then the event's image
    reference is cleared so it doesn't point at a file that's gone. The
    events themselves are kept. Safe to re-run -- it only ever selects
    events that still have an image, so an interrupted run just resumes."""
    factory = get_session_factory()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            while True:
                async with factory() as session:
                    rows = (
                        await session.execute(
                            select(Event.id, Event.snapshot_id)
                            .where(*_direction_images_filter(before))
                            .limit(_IMAGE_BATCH)
                        )
                    ).all()
                    if not rows:
                        break
                    response = await client.post(
                        f"{settings.media_service_url}/internal/media/snapshots/purge",
                        json={"ids": [str(row.snapshot_id) for row in rows]},
                        headers=_media_headers(settings),
                    )
                    response.raise_for_status()
                    result = response.json()
                    await session.execute(
                        update(Event)
                        .where(Event.id.in_([row.id for row in rows]))
                        .values(snapshot_id=None, snapshot_url=None)
                    )
                    await session.commit()
                _job.snapshots_removed += result.get("snapshotsRemoved", 0)
                _job.bytes_freed += result.get("bytesFreed", 0)
        _job.status = "done"
    except Exception as exc:  # noqa: BLE001 -- surfaced to the operator via the status, not raised
        logger.warning("direction_image_cleanup_failed", error=str(exc))
        _job.status = "failed"
        _job.error = str(exc) or exc.__class__.__name__
    finally:
        _job.finished_at = dt.datetime.now(dt.UTC)


async def _media_summary(settings: Settings) -> tuple[int | None, int | None]:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{settings.media_service_url}/internal/media/summary", headers=_media_headers(settings)
            )
            response.raise_for_status()
            body = response.json()
            return body["snapshots"], body["recordings"]
    except Exception:  # noqa: BLE001 -- the summary is still useful without the file counts
        return None, None


def _begin_job(now: dt.datetime, *, snapshots_total: int = 0) -> None:
    _job.status = "running"
    _job.started_at = now
    _job.finished_at = None
    _job.snapshots_removed = _job.recordings_removed = _job.bytes_freed = 0
    _job.snapshots_total = snapshots_total
    _job.error = None


@router.get("/summary", response_model=DataSummary)
async def summary(
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _user: TokenPayload = Depends(require_role("operator")),
) -> DataSummary:
    events = await session.scalar(select(func.count()).select_from(Event)) or 0
    alerts = await session.scalar(select(func.count()).select_from(Alert)) or 0
    oldest, newest = (await session.execute(select(func.min(Event.created_at), func.max(Event.created_at)))).one()
    snapshots, recordings = await _media_summary(settings)
    direction_images = (
        await session.scalar(select(func.count()).select_from(Event).where(*_direction_images_filter(None))) or 0
    )
    return DataSummary(
        events=events, alerts=alerts, snapshots=snapshots, recordings=recordings,
        direction_images=direction_images,
        oldest_event_at=oldest, newest_event_at=newest, cleanup=_job.public(),
    )


@router.post("/reset", response_model=ResetResult)
async def reset(
    payload: ResetRequest,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _user: TokenPayload = Depends(require_role("admin")),
) -> ResetResult:
    """Deletes events + alerts (all, or older than N days) immediately, then
    removes their evidence files in the background -- poll `GET /summary` for
    the cleanup's progress. Analytics charts built from events/alerts update
    on their own refresh cycle (about a minute)."""
    if _job.status == "running":
        raise ConflictError("A data cleanup is already in progress")

    now = dt.datetime.now(dt.UTC)
    cutoff = compute_cutoff(now, payload.older_than_days)

    if payload.only == "direction_images":
        # Events and alerts are untouched: only these events' image files (and
        # the reference to them) go. `before` is None for "all" -- new Direction
        # Observed events no longer get a snapshot, so there's no race to guard.
        before = cutoff if payload.older_than_days is not None else None
        total = (
            await session.scalar(select(func.count()).select_from(Event).where(*_direction_images_filter(before)))
            or 0
        )
        logger.info("direction_image_cleanup_started", images=total)
        _begin_job(now, snapshots_total=total)
        _job.task = asyncio.create_task(
            _run_direction_image_cleanup(settings, before), name="direction-image-cleanup"
        )
        return ResetResult(events_removed=0, alerts_removed=0, cleanup=_job.public())

    try:
        if payload.older_than_days is None:
            alerts_removed = await session.scalar(select(func.count()).select_from(Alert)) or 0
            events_removed = await session.scalar(select(func.count()).select_from(Event)) or 0
            # TRUNCATE (not DELETE) for "everything": instant, and returns the
            # disk space immediately instead of leaving it as dead rows.
            await session.execute(text("TRUNCATE TABLE events.alerts, events.events"))
        else:
            alerts_removed = (
                await session.scalar(select(func.count()).select_from(Alert).where(Alert.created_at < cutoff)) or 0
            )
            # Alerts go with their event (FK ON DELETE CASCADE).
            result = await session.execute(delete(Event).where(Event.created_at < cutoff))
            events_removed = result.rowcount or 0
        await session.commit()
    except Exception as exc:
        await session.rollback()
        logger.error("data_reset_failed", error=str(exc))
        raise ApiError(status_code=500, title="Data reset failed", detail="Nothing was deleted.") from exc

    logger.info(
        "data_reset", events=events_removed, alerts=alerts_removed, older_than_days=payload.older_than_days
    )

    _begin_job(now)
    _job.task = asyncio.create_task(_run_media_cleanup(settings, cutoff), name="evidence-cleanup")

    return ResetResult(events_removed=events_removed, alerts_removed=alerts_removed, cleanup=_job.public())
