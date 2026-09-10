import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.track import TrackSummary


class TrackRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active(self, camera_id: str, track_ref: str) -> TrackSummary | None:
        # `.limit(1)` (matching `get_by_ref` below): track_ref is ByteTrack's
        # own per-camera counter, not a DB-enforced-unique key, so an
        # at-least-once redelivery of a `track.started` message (e.g. right
        # after a restart, reprocessing unacked stream entries) can leave two
        # rows briefly active for the same ref. Without this, a second match
        # made `scalar_one_or_none()` raise `MultipleResultsFound` and fail
        # rule evaluation for the whole message instead of just picking the
        # most-recently-touched row.
        result = await self._session.execute(
            select(TrackSummary)
            .where(
                TrackSummary.camera_id == camera_id,
                TrackSummary.track_ref == track_ref,
                TrackSummary.status == "active",
            )
            .order_by(TrackSummary.last_seen.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_ref(self, camera_id: str, track_ref: str) -> TrackSummary | None:
        """Fetch regardless of status -- used by the track-merge heuristic
        to reactivate a just-lost row instead of starting a new one."""
        result = await self._session.execute(
            select(TrackSummary)
            .where(TrackSummary.camera_id == camera_id, TrackSummary.track_ref == track_ref)
            .order_by(TrackSummary.last_seen.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def reactivate(self, track: TrackSummary, now: dt.datetime) -> None:
        """Revives a lost row for the merge heuristic -- `first_seen` stays
        untouched so the track's total dwell time still reflects when the
        real person first appeared, not when they were last reacquired."""
        track.status = "active"
        track.last_seen = now
        await self._session.commit()

    async def start(
        self, *, camera_id: str, track_ref: str, object_type: str, now: dt.datetime, loop_generation: int = 0
    ) -> TrackSummary:
        track = TrackSummary(
            camera_id=camera_id, track_ref=track_ref, object_type=object_type,
            first_seen=now, last_seen=now, status="active", loop_generation=loop_generation,
        )
        self._session.add(track)
        await self._session.commit()
        await self._session.refresh(track)
        return track

    async def touch(self, track: TrackSummary, now: dt.datetime) -> None:
        track.last_seen = now
        await self._session.commit()

    async def mark_lost(self, track: TrackSummary, now: dt.datetime) -> None:
        track.status = "lost"
        track.last_seen = now
        await self._session.commit()

    async def set_current_queue_zone(self, track: TrackSummary, zone_id: str | None) -> None:
        """Phase 2 M14 Queue Detection -- persisted so analytics-service can
        query live queue occupancy/dwell time directly (see the column's own
        docstring in `models/track.py`)."""
        track.current_queue_zone_id = zone_id
        await self._session.commit()
