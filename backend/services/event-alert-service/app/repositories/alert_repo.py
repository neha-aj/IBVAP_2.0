import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert


class AlertRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, alert: Alert) -> Alert:
        self._session.add(alert)
        await self._session.commit()
        await self._session.refresh(alert)
        return alert

    async def get_by_id(self, alert_id: str) -> Alert | None:
        result = await self._session.execute(select(Alert).where(Alert.id == alert_id))
        return result.scalar_one_or_none()

    async def set_recording(self, alert: Alert, *, recording_id: str, recording_url: str) -> Alert:
        alert.recording_id = recording_id
        alert.recording_url = recording_url
        await self._session.commit()
        await self._session.refresh(alert)
        return alert

    async def update_status(
        self, alert: Alert, *, status: str, acknowledged_by: str | None
    ) -> Alert:
        alert.status = status
        now = dt.datetime.now(dt.UTC)
        # Any status-transition action (API Spec §5) means an operator
        # touched this alert -- stamp who/when on first touch, whether they
        # went through "reviewing" or jumped straight to "resolved".
        if alert.acknowledged_at is None:
            alert.acknowledged_at = now
            alert.acknowledged_by = acknowledged_by
        if status == "resolved":
            alert.resolved_at = now
        await self._session.commit()
        await self._session.refresh(alert)
        return alert

    async def list_paginated(
        self,
        *,
        camera_id: str | None,
        severity: str | None,
        status: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Alert], int]:
        stmt = select(Alert)
        if camera_id:
            stmt = stmt.where(Alert.camera_id == camera_id)
        if severity:
            stmt = stmt.where(Alert.severity == severity)
        if status:
            stmt = stmt.where(Alert.status == status)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = stmt.order_by(Alert.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        rows = (await self._session.execute(stmt)).scalars().all()
        return list(rows), int(total)
