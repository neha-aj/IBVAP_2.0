import uuid

from fastapi import APIRouter, Cookie, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ibvap_common.auth import TokenPayload, get_current_user
from ibvap_common.errors import UnauthorizedError

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.repositories.token_repo import TokenRepository
from app.repositories.user_repo import UserRepository
from app.schemas.token import LoginResponse
from app.schemas.user import MfaEnrollResponse, MfaStatus, MfaVerifyRequest, UserLogin, UserRead
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# M25 hardening: the refresh token now lives only in an httpOnly cookie,
# never in a JSON body a script could read or a frontend could choose to
# put in localStorage -- that was the actual XSS blast-radius issue (a
# compromised frontend could exfiltrate a long-lived credential). Scoped
# to this router's own path so it's never sent on ordinary API calls.
# `Secure` is honored by browsers on http://127.0.0.1 too (loopback is a
# "potentially trustworthy origin" by spec) so this works in local dev
# without HTTPS; `SameSite=Lax` alone is what actually blocks a cross-site
# POST from carrying this cookie at all -- Lax only attaches a cookie to a
# top-level cross-site *navigation* GET, never a cross-site POST/fetch --
# so no separate CSRF token is needed on top of it.
_REFRESH_COOKIE = "ibvap_refresh"
_REFRESH_COOKIE_PATH = "/api/v1/auth"


def get_auth_service(
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthService:
    return AuthService(UserRepository(session), TokenRepository(session), settings)


def _set_refresh_cookie(response: Response, refresh_token: str, settings: Settings) -> None:
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=refresh_token,
        max_age=settings.refresh_token_expire_days * 86400,
        path=_REFRESH_COOKIE_PATH,
        httponly=True,
        secure=True,
        samesite="lax",
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: UserLogin, response: Response, settings: Settings = Depends(get_settings),
    service: AuthService = Depends(get_auth_service),
) -> LoginResponse:
    pair = await service.login(payload)
    _set_refresh_cookie(response, pair.refresh_token, settings)
    return LoginResponse(access_token=pair.access_token, user=pair.user)


@router.post("/refresh", response_model=LoginResponse)
async def refresh(
    response: Response,
    settings: Settings = Depends(get_settings),
    service: AuthService = Depends(get_auth_service),
    ibvap_refresh: str | None = Cookie(default=None),
) -> LoginResponse:
    if not ibvap_refresh:
        raise UnauthorizedError("No refresh session")
    pair = await service.refresh(ibvap_refresh)
    _set_refresh_cookie(response, pair.refresh_token, settings)
    return LoginResponse(access_token=pair.access_token, user=pair.user)


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    service: AuthService = Depends(get_auth_service),
    _user: TokenPayload = Depends(get_current_user),
    ibvap_refresh: str | None = Cookie(default=None),
) -> None:
    if ibvap_refresh:
        await service.logout(ibvap_refresh)
    response.delete_cookie(key=_REFRESH_COOKIE, path=_REFRESH_COOKIE_PATH)


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
