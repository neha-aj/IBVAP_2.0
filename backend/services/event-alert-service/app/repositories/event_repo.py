import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, event: Event) -> Event:
        self._session.add(event)
        await self._session.commit()
        await self._session.refresh(event)
        return event

    async def get_by_id(self, event_id: str) -> Event | None:
        result = await self._session.execute(select(Event).where(Event.id == event_id))
        return result.scalar_one_or_none()

    async def set_snapshot(self, event: Event, *, snapshot_id: str, snapshot_url: str) -> Event:
        event.snapshot_id = snapshot_id
        event.snapshot_url = snapshot_url
        await self._session.commit()
        await self._session.refresh(event)
        return event

    async def set_recording(self, event: Event, *, recording_id: str, recording_url: str) -> Event:
        event.recording_id = recording_id
        event.recording_url = recording_url
        await self._session.commit()
        await self._session.refresh(event)
        return event

    async def update_status(self, event: Event, status: str) -> Event:
        event.status = status
        await self._session.commit()
        await self._session.refresh(event)
        return event

    async def list_paginated(
        self,
        *,
        camera_id: str | None,
        event_type: str | None,
        severity: str | None,
        status: str | None,
        date_from: dt.datetime | None,
        date_to: dt.datetime | None,
        page: int,
        page_size: int,
        has_recording: bool | None = None,
    ) -> tuple[list[Event], int]:
        stmt = select(Event)
        if camera_id:
            stmt = stmt.where(Event.camera_id == camera_id)
        if event_type:
            stmt = stmt.where(Event.event_type == event_type)
        if severity:
            stmt = stmt.where(Event.severity == severity)
        if status:
            stmt = stmt.where(Event.status == status)
        if date_from:
            stmt = stmt.where(Event.created_at >= date_from)
        if date_to:
            stmt = stmt.where(Event.created_at <= date_to)
        # Evidence page: only events with an attached recording clip.
        if has_recording is True:
            stmt = stmt.where(Event.recording_id.is_not(None))
        elif has_recording is False:
            stmt = stmt.where(Event.recording_id.is_(None))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = stmt.order_by(Event.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        rows = (await self._session.execute(stmt)).scalars().all()
        return list(rows), int(total)
