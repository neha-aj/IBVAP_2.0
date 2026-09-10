from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.setting import Setting
from app.schemas.setting import DEFAULT_SETTINGS


class SettingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_grouped(self) -> dict[str, list[Setting]]:
        result = await self._session.execute(select(Setting).order_by(Setting.group_name, Setting.key))
        grouped: dict[str, list[Setting]] = {}
        for row in result.scalars().all():
            grouped.setdefault(row.group_name, []).append(row)
        return grouped

    async def get(self, group_name: str, key: str) -> Setting | None:
        result = await self._session.execute(
            select(Setting).where(Setting.group_name == group_name, Setting.key == key)
        )
        return result.scalar_one_or_none()

    async def upsert(self, group_name: str, key: str, value: dict) -> Setting:
        existing = await self.get(group_name, key)
        if existing is not None:
            existing.value = value
            await self._session.commit()
            await self._session.refresh(existing)
            return existing
        setting = Setting(group_name=group_name, key=key, value=value)
        self._session.add(setting)
        await self._session.commit()
        await self._session.refresh(setting)
        return setting

    async def seed_defaults_if_empty(self) -> None:
        result = await self._session.execute(select(Setting).limit(1))
        if result.scalar_one_or_none() is not None:
            return
        for group_name, keys in DEFAULT_SETTINGS.items():
            for key, value in keys.items():
                self._session.add(Setting(group_name=group_name, key=key, value=value))
        await self._session.commit()
