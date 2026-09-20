"""Internal-only housekeeping for event evidence (snapshots + recording clips).

Every event stores a snapshot and every critical event a video clip, so these
grow without bound unless something removes them -- on a busy camera set that
is tens of GB. `event-alert-service`'s data reset calls `POST /purge` after it
deletes the event/alert rows themselves.

Only evidence *linked to an event* is ever touched (`event_id IS NOT NULL`).
Camera source uploads live elsewhere (`/internal/media/sources`) and are never
deleted here.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ibvap_common.internal_auth import verify_internal_token
from ibvap_common.logging import get_logger

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.recording import Recording
from app.models.snapshot import Snapshot

logger = get_logger(__name__)

router = APIRouter(
    prefix="/internal/media", tags=["internal"], dependencies=[Depends(verify_internal_token)]
)

# Rows (and their files) removed per round trip: small enough that a huge
# purge holds no long transaction and reports steady progress.
_BATCH_SIZE = 500


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class PurgeRequest(_CamelModel):
    # Evidence created before this instant is removed; None removes all
    # event-linked evidence.
    before: dt.datetime | None = None


class SnapshotIdsPurgeRequest(_CamelModel):
    # A bounded batch: the caller works through a large set a slice at a time.
    ids: list[uuid.UUID] = Field(max_length=5000)


class PurgeResult(_CamelModel):
    snapshots_removed: int
    recordings_removed: int
    bytes_freed: int
    files_missing: int


class MediaSummary(_CamelModel):
    snapshots: int
    recordings: int


def _disk_path(media_root: Path, url_prefix: str, stored_path: str) -> Path | None:
    """Maps a stored URL-style path (`/media/snapshots/...`) to its file on
    disk, or None if it doesn't resolve to somewhere strictly inside
    `media_root` -- a corrupt/hostile row must never be able to point a delete
    at anything else on the filesystem."""
    prefix = url_prefix.rstrip("/") + "/"
    if not stored_path.startswith(prefix):
        return None
    root = media_root.resolve()
    target = (root / stored_path[len(prefix):]).resolve()
    return target if root in target.parents else None


def _delete_files(media_root: Path, url_prefix: str, stored_paths: list[str]) -> tuple[int, int]:
    """Deletes the given evidence files; returns (bytes_freed, files_missing).
    A file that's already gone counts as missing, not an error. Empty date /
    camera folders left behind are tidied up too."""
    freed = missing = 0
    parents: set[Path] = set()
    for stored in stored_paths:
        target = _disk_path(media_root, url_prefix, stored)
        if target is None:
            continue
        try:
            size = target.stat().st_size
            target.unlink()
            freed += size
            parents.add(target.parent)
        except FileNotFoundError:
            missing += 1
        except OSError as exc:  # noqa: BLE001 -- keep purging; the row is still removed below
            logger.warning("evidence_file_delete_failed", path=str(target), error=str(exc))
    root = media_root.resolve()
    for folder in sorted(parents, key=lambda p: len(p.parts), reverse=True):
        # Date folder, then its camera folder -- rmdir only succeeds when empty.
        for candidate in (folder, folder.parent):
            if candidate != root and root in candidate.parents:
                try:
                    candidate.rmdir()
                except OSError:
                    break
    return freed, missing


async def _purge_table(
    session: AsyncSession, model, before: dt.datetime | None, settings: Settings
) -> tuple[int, int, int]:
    removed = freed = missing = 0
    media_root = Path(settings.media_root)
    while True:
        stmt = select(model.id, model.file_path).where(model.event_id.is_not(None))
        if before is not None:
            stmt = stmt.where(model.created_at < before)
        rows = (await session.execute(stmt.limit(_BATCH_SIZE))).all()
        if not rows:
            break
        batch_freed, batch_missing = await asyncio.to_thread(
            _delete_files, media_root, settings.media_url_prefix, [row.file_path for row in rows]
        )
        await session.execute(delete(model).where(model.id.in_([row.id for row in rows])))
        await session.commit()
        removed += len(rows)
        freed += batch_freed
        missing += batch_missing
    return removed, freed, missing


@router.get("/summary", response_model=MediaSummary)
async def summary(session: AsyncSession = Depends(get_db)) -> MediaSummary:
    snapshots = await session.scalar(select(func.count()).select_from(Snapshot).where(Snapshot.event_id.is_not(None)))
    recordings = await session.scalar(
        select(func.count()).select_from(Recording).where(Recording.event_id.is_not(None))
    )
    return MediaSummary(snapshots=snapshots or 0, recordings=recordings or 0)


@router.post("/purge", response_model=PurgeResult)
async def purge(
    payload: PurgeRequest,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> PurgeResult:
    """Removes event-linked snapshots and recordings created before
    `payload.before` (all of them if omitted): the file first, then its row,
    in batches. Long-running by design for a large backlog -- the caller runs
    it in the background."""
    snapshots_removed, snapshot_bytes, snapshot_missing = await _purge_table(
        session, Snapshot, payload.before, settings
    )
    recordings_removed, recording_bytes, recording_missing = await _purge_table(
        session, Recording, payload.before, settings
    )
    logger.info(
        "evidence_purged",
        snapshots=snapshots_removed, recordings=recordings_removed,
        bytes_freed=snapshot_bytes + recording_bytes,
    )
    return PurgeResult(
        snapshots_removed=snapshots_removed,
        recordings_removed=recordings_removed,
        bytes_freed=snapshot_bytes + recording_bytes,
        files_missing=snapshot_missing + recording_missing,
    )


@router.post("/snapshots/purge", response_model=PurgeResult)
async def purge_snapshots_by_id(
    payload: SnapshotIdsPurgeRequest,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> PurgeResult:
    """Removes exactly the given event-linked snapshots (file, then row) and
    nothing else -- e.g. the images of one event type, whose events are kept.
    Ids that don't exist, or that aren't linked to an event, are ignored."""
    if not payload.ids:
        return PurgeResult(snapshots_removed=0, recordings_removed=0, bytes_freed=0, files_missing=0)
    rows = (
        await session.execute(
            select(Snapshot.id, Snapshot.file_path).where(
                Snapshot.id.in_(payload.ids), Snapshot.event_id.is_not(None)
            )
        )
    ).all()
    freed, missing = await asyncio.to_thread(
        _delete_files, Path(settings.media_root), settings.media_url_prefix, [row.file_path for row in rows]
    )
    if rows:
        await session.execute(delete(Snapshot).where(Snapshot.id.in_([row.id for row in rows])))
        await session.commit()
    return PurgeResult(
        snapshots_removed=len(rows), recordings_removed=0, bytes_freed=freed, files_missing=missing
    )
