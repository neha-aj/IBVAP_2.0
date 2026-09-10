from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sector import Sector


class SectorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_name_or_code(self, value: str) -> Sector | None:
        result = await self._session.execute(
            select(Sector).where((Sector.name == value) | (Sector.code == value))
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, name_or_code: str) -> Sector:
        existing = await self.get_by_name_or_code(name_or_code)
        if existing is not None:
            return existing
        sector = Sector(name=name_or_code, code=name_or_code)
        self._session.add(sector)
        await self._session.flush()
        return sector

    async def list_all(self) -> list[Sector]:
        result = await self._session.execute(select(Sector).order_by(Sector.name))
        return list(result.scalars().all())
