
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.camera import Camera


class CameraRepository:
    """Data-access layer for `camera.cameras` (Repository Pattern, IG §3)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_external_id(self, external_id: str) -> Camera | None:
        result = await self._session.execute(
            select(Camera).where(Camera.external_id == external_id)
        )
        return result.scalar_one_or_none()

    async def exists_external_id(self, external_id: str) -> bool:
        return await self.get_by_external_id(external_id) is not None

    async def list_paginated(
        self,
        *,
        status: str | None,
        sector: str | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Camera], int]:
        stmt = select(Camera)
        if status:
            stmt = stmt.where(Camera.status == status)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Camera.name.ilike(like),
                    Camera.external_id.ilike(like),
                    Camera.location.ilike(like),
                )
            )
        if sector:
            stmt = stmt.join(Camera.sector).where(
                or_(Camera.sector.has(name=sector), Camera.sector.has(code=sector))
            )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = stmt.order_by(Camera.name).offset((page - 1) * page_size).limit(page_size)
        rows = (await self._session.execute(stmt)).scalars().all()
        return list(rows), int(total)

    async def status_counts(self) -> dict[str, int]:
        result = await self._session.execute(
            select(Camera.status, func.count()).group_by(Camera.status)
        )
        counts = dict(result.all())
        return {
            "online": counts.get("online", 0),
            "warning": counts.get("warning", 0),
            "offline": counts.get("offline", 0),
            "total": sum(counts.values()),
        }

    async def list_all(self) -> list[Camera]:
        result = await self._session.execute(select(Camera))
        return list(result.scalars().all())

    async def create(self, camera: Camera) -> Camera:
        self._session.add(camera)
        await self._session.commit()
        await self._session.refresh(camera)
        return camera

    async def update(self, camera: Camera) -> Camera:
        await self._session.commit()
        await self._session.refresh(camera)
        return camera

    async def delete(self, camera: Camera) -> None:
        await self._session.delete(camera)
        await self._session.commit()
