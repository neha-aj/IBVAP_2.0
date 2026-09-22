import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ibvap_common.auth import TokenPayload, get_current_user

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.repositories.token_repo import TokenRepository
from app.repositories.user_repo import UserRepository
from app.schemas.token import RefreshRequest, TokenPair
from app.schemas.user import MfaEnrollResponse, MfaStatus, MfaVerifyRequest, UserLogin, UserRead
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
    record = await repo.get_by_id(uuid.UUID(user.sub))
    return UserRead.model_validate(record, from_attributes=True)


# --- M25 MFA -----------------------------------------------------------------


@router.get("/mfa/status", response_model=MfaStatus)
async def mfa_status(
    user: TokenPayload = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> MfaStatus:
    enabled = await service.mfa_status(uuid.UUID(user.sub))
    return MfaStatus(enabled=enabled)


@router.post("/mfa/enroll", response_model=MfaEnrollResponse)
async def mfa_enroll(
    user: TokenPayload = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> MfaEnrollResponse:
    """Starts enrollment -- MFA isn't enabled yet, only `POST /mfa/verify`
    with a valid code turns it on (see AuthService.enroll_mfa)."""
    secret, uri = await service.enroll_mfa(uuid.UUID(user.sub))
    return MfaEnrollResponse(secret=secret, provisioning_uri=uri)


@router.post("/mfa/verify", status_code=204)
async def mfa_verify(
    payload: MfaVerifyRequest,
    user: TokenPayload = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> None:
    await service.verify_mfa(uuid.UUID(user.sub), payload.code)


@router.post("/mfa/disable", status_code=204)
async def mfa_disable(
    user: TokenPayload = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> None:
    await service.disable_mfa(uuid.UUID(user.sub))
