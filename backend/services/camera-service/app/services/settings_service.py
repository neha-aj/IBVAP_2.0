from ibvap_common.errors import NotFoundError

from app.repositories.setting_repo import SettingRepository
from app.schemas.setting import SettingsGroup, SettingUpdate, SettingValue


class SettingsService:
    def __init__(self, repo: SettingRepository) -> None:
        self._repo = repo

    async def get_all(self) -> list[SettingsGroup]:
        await self._repo.seed_defaults_if_empty()
        grouped = await self._repo.list_grouped()
        return [
            SettingsGroup(
                group=group_name,
                items=[SettingValue(key=row.key, value=row.value) for row in rows],
            )
            for group_name, rows in grouped.items()
        ]

    async def update(self, group: str, key: str, data: SettingUpdate) -> SettingValue:
        existing = await self._repo.get(group, key)
        if existing is None:
            raise NotFoundError(f"No setting '{group}/{key}'")
        updated = await self._repo.upsert(group, key, data.value)
        return SettingValue(key=updated.key, value=updated.value)
