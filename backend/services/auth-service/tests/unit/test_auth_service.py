"""Unit tests for AuthService using in-memory fakes instead of a real DB,
per Implementation Guide §9 (unit tests should not require a live database)."""

import datetime as dt
import uuid

import pytest

from ibvap_common.settings import CommonSettings

from app.schemas.user import UserCreate, UserLogin
from app.services.auth_service import AuthService
from app.services.security import hash_password


class FakeUser:
    def __init__(self, username: str, password_hash: str, role: str = "viewer") -> None:
        self.id = uuid.uuid4()
        self.username = username
        self.password_hash = password_hash
        self.role = role
        self.is_active = True


class FakeUserRepo:
    def __init__(self) -> None:
        self.users: dict[str, FakeUser] = {}

    async def get_by_username(self, username: str) -> FakeUser | None:
        return self.users.get(username)

    async def get_by_id(self, user_id: uuid.UUID) -> FakeUser | None:
        return next((u for u in self.users.values() if u.id == user_id), None)

    async def count(self) -> int:
        return len(self.users)

    async def create(self, data: UserCreate, password_hash: str) -> FakeUser:
        user = FakeUser(data.username, password_hash, data.role)
        self.users[data.username] = user
        return user


class FakeTokenRepo:
    def __init__(self) -> None:
        self.valid: set[str] = set()

    async def store(self, *, user_id, raw_token: str, expires_at: dt.datetime) -> None:
        self.valid.add(raw_token)

    async def is_valid(self, raw_token: str) -> bool:
        return raw_token in self.valid

    async def revoke(self, raw_token: str) -> None:
        self.valid.discard(raw_token)


def _settings() -> CommonSettings:
    return CommonSettings(
        postgres_user="u",
        postgres_password="p",
        postgres_db="d",
        jwt_secret="test-secret",
    )


@pytest.mark.asyncio
async def test_login_success_returns_token_pair() -> None:
    user_repo = FakeUserRepo()
    user_repo.users["alice"] = FakeUser("alice", hash_password("hunter2"), role="operator")
    service = AuthService(user_repo, FakeTokenRepo(), _settings())

    result = await service.login(UserLogin(username="alice", password="hunter2"))

    assert result.access_token
    assert result.refresh_token
    assert result.user.username == "alice"
    assert result.user.role == "operator"


@pytest.mark.asyncio
async def test_login_wrong_password_raises_unauthorized() -> None:
    from ibvap_common.errors import UnauthorizedError

    user_repo = FakeUserRepo()
    user_repo.users["alice"] = FakeUser("alice", hash_password("hunter2"))
    service = AuthService(user_repo, FakeTokenRepo(), _settings())

    with pytest.raises(UnauthorizedError):
        await service.login(UserLogin(username="alice", password="wrong"))


@pytest.mark.asyncio
async def test_login_unknown_username_raises_same_unauthorized_error() -> None:
    """Must fail via the same generic error as a wrong password (not a
    distinct "user not found" message) -- and, per the dummy-hash path in
    AuthService.login, without ever short-circuiting past a bcrypt check,
    which is what keeps username enumeration from being timeable."""
    from ibvap_common.errors import UnauthorizedError

    service = AuthService(FakeUserRepo(), FakeTokenRepo(), _settings())

    with pytest.raises(UnauthorizedError, match="Invalid username or password"):
        await service.login(UserLogin(username="nobody", password="whatever123"))


@pytest.mark.asyncio
async def test_register_duplicate_username_raises_conflict() -> None:
    from ibvap_common.errors import ConflictError

    user_repo = FakeUserRepo()
    service = AuthService(user_repo, FakeTokenRepo(), _settings())
    await service.register(UserCreate(username="bob", password="pw123456", role="viewer"))

    with pytest.raises(ConflictError):
        await service.register(UserCreate(username="bob", password="pw123456", role="viewer"))


@pytest.mark.asyncio
async def test_refresh_rotates_token() -> None:
    user_repo = FakeUserRepo()
    token_repo = FakeTokenRepo()
    service = AuthService(user_repo, token_repo, _settings())
    user_repo.users["carol"] = FakeUser("carol", hash_password("pw123456"))
    login_result = await service.login(UserLogin(username="carol", password="pw123456"))

    refreshed = await service.refresh(login_result.refresh_token)

    assert refreshed.access_token != login_result.access_token
    assert refreshed.refresh_token != login_result.refresh_token
    assert not await token_repo.is_valid(login_result.refresh_token)  # old one revoked


@pytest.mark.asyncio
async def test_ensure_bootstrap_admin_creates_admin_when_empty() -> None:
    user_repo = FakeUserRepo()
    service = AuthService(user_repo, FakeTokenRepo(), _settings())

    await service.ensure_bootstrap_admin("admin", "adminpass123")

    admin = await user_repo.get_by_username("admin")
    assert admin is not None
    assert admin.role == "admin"

    # Calling again must not create a second admin / duplicate error.
    await service.ensure_bootstrap_admin("admin", "adminpass123")
    assert await user_repo.count() == 1
