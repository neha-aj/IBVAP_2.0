import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recording import Recording
from app.models.snapshot import Snapshot


class MediaRepository:
    """Both snapshots and recordings live here (matching the project
    structure's single `repositories/media_repo.py`) since neither is
    complex enough to need its own file yet."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_snapshot(self, snapshot: Snapshot) -> Snapshot:
        self._session.add(snapshot)
        await self._session.commit()
        await self._session.refresh(snapshot)
        return snapshot

    async def get_snapshot(self, snapshot_id: uuid.UUID) -> Snapshot | None:
        result = await self._session.execute(select(Snapshot).where(Snapshot.id == snapshot_id))
        return result.scalar_one_or_none()

    async def get_recording(self, recording_id: uuid.UUID) -> Recording | None:
        result = await self._session.execute(select(Recording).where(Recording.id == recording_id))
        return result.scalar_one_or_none()

    async def create_recording(self, recording: Recording) -> Recording:
        self._session.add(recording)
        await self._session.commit()
        await self._session.refresh(recording)
        return recording
