import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plate_read import PlateRead


class PlateReadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, plate_read: PlateRead) -> PlateRead:
        self._session.add(plate_read)
        await self._session.commit()
        await self._session.refresh(plate_read)
        return plate_read

    async def list_paginated(
        self,
        *,
        camera_id: str | None,
        plate: str | None,
        date_from: dt.datetime | None,
        date_to: dt.datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[PlateRead], int]:
        stmt = select(PlateRead)
        if camera_id:
            stmt = stmt.where(PlateRead.camera_id == camera_id)
        if plate:
            stmt = stmt.where(PlateRead.plate_text.ilike(f"%{plate}%"))
        if date_from:
            stmt = stmt.where(PlateRead.created_at >= date_from)
        if date_to:
            stmt = stmt.where(PlateRead.created_at <= date_to)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = stmt.order_by(PlateRead.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        rows = (await self._session.execute(stmt)).scalars().all()
        return list(rows), int(total)
