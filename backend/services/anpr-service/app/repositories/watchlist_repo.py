import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.watchlist import WatchlistEntry


class WatchlistRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[WatchlistEntry]:
        result = await self._session.execute(select(WatchlistEntry).order_by(WatchlistEntry.created_at.desc()))
        return list(result.scalars().all())

    async def get_by_plate(self, plate_text: str) -> WatchlistEntry | None:
        result = await self._session.execute(
            select(WatchlistEntry).where(WatchlistEntry.plate_text == plate_text)
        )
        return result.scalar_one_or_none()

    async def create(self, entry: WatchlistEntry) -> WatchlistEntry:
        self._session.add(entry)
        await self._session.commit()
        await self._session.refresh(entry)
        return entry

    async def delete(self, entry_id: uuid.UUID) -> bool:
        result = await self._session.execute(select(WatchlistEntry).where(WatchlistEntry.id == entry_id))
        entry = result.scalar_one_or_none()
        if entry is None:
            return False
        await self._session.delete(entry)
        await self._session.commit()
        return True
