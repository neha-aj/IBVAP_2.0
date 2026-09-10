from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ibvap_common.auth import TokenPayload, require_role

from app.db.session import get_db
from app.repositories.setting_repo import SettingRepository
from app.schemas.setting import SettingsGroup, SettingUpdate, SettingValue
from app.services.settings_service import SettingsService

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


def get_settings_service(session: AsyncSession = Depends(get_db)) -> SettingsService:
    return SettingsService(SettingRepository(session))


@router.get("", response_model=list[SettingsGroup])
async def get_all_settings(
    service: SettingsService = Depends(get_settings_service),
    _user: TokenPayload = Depends(require_role("viewer")),
) -> list[SettingsGroup]:
    return await service.get_all()


@router.put("/{group}/{key}", response_model=SettingValue)
async def update_setting(
    group: str,
    key: str,
    payload: SettingUpdate,
    service: SettingsService = Depends(get_settings_service),
    _user: TokenPayload = Depends(require_role("admin")),
) -> SettingValue:
    return await service.update(group, key, payload)
