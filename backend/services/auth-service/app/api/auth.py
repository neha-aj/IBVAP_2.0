from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ibvap_common.auth import TokenPayload, get_current_user

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.repositories.token_repo import TokenRepository
from app.repositories.user_repo import UserRepository
from app.schemas.token import RefreshRequest, TokenPair
from app.schemas.user import UserLogin, UserRead
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def get_auth_service(
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthService:
    return AuthService(UserRepository(session), TokenRepository(session), settings)


@router.post("/login", response_model=TokenPair)
async def login(
    payload: UserLogin, service: AuthService = Depends(get_auth_service)
) -> TokenPair:
    return await service.login(payload)


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    payload: RefreshRequest, service: AuthService = Depends(get_auth_service)
) -> TokenPair:
    return await service.refresh(payload.refresh_token)


@router.post("/logout", status_code=204)
async def logout(
    payload: RefreshRequest,
    service: AuthService = Depends(get_auth_service),
    _user: TokenPayload = Depends(get_current_user),
) -> None:
    await service.logout(payload.refresh_token)


@router.get("/me", response_model=UserRead)
async def me(
    user: TokenPayload = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> UserRead:
    repo = UserRepository(session)
    import uuid

    record = await repo.get_by_id(uuid.UUID(user.sub))
    return UserRead.model_validate(record, from_attributes=True)
