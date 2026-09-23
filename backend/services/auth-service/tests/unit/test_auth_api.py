"""M25 hardening: the refresh token moved from the JSON response body into
an httpOnly cookie (see app/api/auth.py's own module docstring for why).
These exercise the route layer directly -- same convention media-service's
API tests use -- to prove the cookie is actually set/read/cleared, since
that behavior lives in the route, not AuthService itself (already covered
by test_auth_service.py)."""

import uuid

import pytest
from fastapi import Response

from ibvap_common.errors import UnauthorizedError

from app.api import auth as auth_api
from app.schemas.user import UserLogin
from app.services.security import hash_password


class FakeUser:
    def __init__(self, username: str, password_hash: str, role: str = "viewer") -> None:
        self.id = uuid.uuid4()
        self.username = username
        self.password_hash = password_hash
        self.role = role
        self.is_active = True
        self.mfa_secret = None
        self.mfa_enabled = False


class FakeUserRepo:
    def __init__(self) -> None:
        self.users: dict[str, FakeUser] = {}

    async def get_by_username(self, username):
        return self.users.get(username)

    async def get_by_id(self, user_id):
        return next((u for u in self.users.values() if u.id == user_id), None)


class FakeTokenRepo:
    def __init__(self) -> None:
        self.valid: set[str] = set()

    async def store(self, *, user_id, raw_token, expires_at) -> None:
        self.valid.add(raw_token)

    async def is_valid(self, raw_token: str) -> bool:
        return raw_token in self.valid

    async def revoke(self, raw_token: str) -> None:
        self.valid.discard(raw_token)


def _settings():
    from app.core.config import Settings

    return Settings(postgres_user="u", postgres_password="p", postgres_db="d", jwt_secret="test-secret-long-enough")


def _service():
    from app.services.auth_service import AuthService

    user_repo = FakeUserRepo()
    user_repo.users["alice"] = FakeUser("alice", hash_password("hunter2"), role="operator")
    return AuthService(user_repo, FakeTokenRepo(), _settings()), user_repo


def _cookie_value(response: Response) -> str | None:
    raw = response.headers.get("set-cookie")
    if not raw or "ibvap_refresh=" not in raw:
        return None
    return raw.split("ibvap_refresh=", 1)[1].split(";", 1)[0]


@pytest.mark.asyncio
async def test_login_sets_a_refresh_cookie_and_omits_it_from_the_body() -> None:
    service, _ = _service()
    response = Response()

    result = await auth_api.login(
        UserLogin(username="alice", password="hunter2"), response, _settings(), service
    )

    assert not hasattr(result, "refresh_token")
    assert result.access_token
    cookie_value = _cookie_value(response)
    assert cookie_value is not None and cookie_value != ""
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "Path=/api/v1/auth" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_refresh_without_a_cookie_is_rejected() -> None:
    service, _ = _service()

    with pytest.raises(UnauthorizedError):
        await auth_api.refresh(Response(), _settings(), service, ibvap_refresh=None)


@pytest.mark.asyncio
async def test_refresh_with_the_cookie_rotates_it() -> None:
    service, _ = _service()
    login_response = Response()
    login_result = await auth_api.login(
        UserLogin(username="alice", password="hunter2"), login_response, _settings(), service
    )
    old_cookie = _cookie_value(login_response)

    refresh_response = Response()
    refreshed = await auth_api.refresh(refresh_response, _settings(), service, ibvap_refresh=old_cookie)

    assert refreshed.access_token != login_result.access_token
    new_cookie = _cookie_value(refresh_response)
    assert new_cookie is not None and new_cookie != old_cookie


@pytest.mark.asyncio
async def test_logout_clears_the_cookie() -> None:
    from ibvap_common.auth import TokenPayload

    service, user_repo = _service()
    login_response = Response()
    await auth_api.login(UserLogin(username="alice", password="hunter2"), login_response, _settings(), service)
    refresh_cookie = _cookie_value(login_response)

    logout_response = Response()
    user = user_repo.users["alice"]
    import datetime as dt

    await auth_api.logout(
        logout_response, service,
        TokenPayload(
            sub=str(user.id), username=user.username, role=user.role, type="access",
            exp=int((dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5)).timestamp()),
        ),
        ibvap_refresh=refresh_cookie,
    )

    set_cookie = logout_response.headers.get("set-cookie")
    assert set_cookie is not None
    # A cleared cookie is expressed as an empty value with an immediately-past expiry.
    assert 'ibvap_refresh=""' in set_cookie or "ibvap_refresh=;" in set_cookie
