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
        self.mfa_secret: str | None = None
        self.mfa_enabled = False


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

    async def set_mfa_secret(self, user: FakeUser, secret: str) -> FakeUser:
        user.mfa_secret = secret
        return user

    async def enable_mfa(self, user: FakeUser) -> FakeUser:
        user.mfa_enabled = True
        return user

    async def disable_mfa(self, user: FakeUser) -> FakeUser:
        user.mfa_enabled = False
        user.mfa_secret = None
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


# --- M25 MFA -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_for_an_account_without_mfa_ignores_a_stray_totp_code() -> None:
    """Passing a totp_code for an account that never enabled MFA must not
    change anything -- the field is opt-in, not "present means required"."""
    user_repo = FakeUserRepo()
    user_repo.users["alice"] = FakeUser("alice", hash_password("hunter2"))
    service = AuthService(user_repo, FakeTokenRepo(), _settings())

    result = await service.login(UserLogin(username="alice", password="hunter2", totp_code="000000"))

    assert result.access_token


@pytest.mark.asyncio
async def test_login_for_an_mfa_enabled_account_without_a_code_requires_mfa() -> None:
    from app.services.auth_service import MfaRequiredError
    from app.services.totp import generate_secret

    user_repo = FakeUserRepo()
    user = FakeUser("alice", hash_password("hunter2"))
    user.mfa_secret = generate_secret()
    user.mfa_enabled = True
    user_repo.users["alice"] = user
    service = AuthService(user_repo, FakeTokenRepo(), _settings())

    with pytest.raises(MfaRequiredError):
        await service.login(UserLogin(username="alice", password="hunter2"))


@pytest.mark.asyncio
async def test_login_for_an_mfa_enabled_account_with_a_valid_code_succeeds() -> None:
    from app.services.totp import generate_secret, provisioning_uri  # noqa: F401  (import parity check)
    from pyotp import TOTP

    user_repo = FakeUserRepo()
    secret = "JBSWY3DPEHPK3PXP"
    user = FakeUser("alice", hash_password("hunter2"))
    user.mfa_secret = secret
    user.mfa_enabled = True
    user_repo.users["alice"] = user
    service = AuthService(user_repo, FakeTokenRepo(), _settings())

    valid_code = TOTP(secret).now()
    result = await service.login(UserLogin(username="alice", password="hunter2", totp_code=valid_code))

    assert result.access_token


@pytest.mark.asyncio
async def test_login_for_an_mfa_enabled_account_with_a_wrong_code_is_rejected() -> None:
    from ibvap_common.errors import UnauthorizedError

    user_repo = FakeUserRepo()
    user = FakeUser("alice", hash_password("hunter2"))
    user.mfa_secret = "JBSWY3DPEHPK3PXP"
    user.mfa_enabled = True
    user_repo.users["alice"] = user
    service = AuthService(user_repo, FakeTokenRepo(), _settings())

    with pytest.raises(UnauthorizedError, match="Invalid authenticator code"):
        await service.login(UserLogin(username="alice", password="hunter2", totp_code="000000"))


@pytest.mark.asyncio
async def test_enroll_mfa_stores_a_secret_but_does_not_enable_it() -> None:
    user_repo = FakeUserRepo()
    user_repo.users["alice"] = FakeUser("alice", hash_password("hunter2"))
    service = AuthService(user_repo, FakeTokenRepo(), _settings())

    secret, uri = await service.enroll_mfa(user_repo.users["alice"].id)

    assert secret
    assert "alice" in uri
    assert user_repo.users["alice"].mfa_enabled is False


@pytest.mark.asyncio
async def test_verify_mfa_with_the_right_code_enables_it() -> None:
    from pyotp import TOTP

    user_repo = FakeUserRepo()
    user_repo.users["alice"] = FakeUser("alice", hash_password("hunter2"))
    service = AuthService(user_repo, FakeTokenRepo(), _settings())
    secret, _uri = await service.enroll_mfa(user_repo.users["alice"].id)

    await service.verify_mfa(user_repo.users["alice"].id, TOTP(secret).now())

    assert user_repo.users["alice"].mfa_enabled is True


@pytest.mark.asyncio
async def test_verify_mfa_with_the_wrong_code_does_not_enable_it() -> None:
    from ibvap_common.errors import UnauthorizedError

    user_repo = FakeUserRepo()
    user_repo.users["alice"] = FakeUser("alice", hash_password("hunter2"))
    service = AuthService(user_repo, FakeTokenRepo(), _settings())
    await service.enroll_mfa(user_repo.users["alice"].id)

    with pytest.raises(UnauthorizedError):
        await service.verify_mfa(user_repo.users["alice"].id, "000000")
    assert user_repo.users["alice"].mfa_enabled is False


@pytest.mark.asyncio
async def test_disable_mfa_clears_the_secret_and_flag() -> None:
    from pyotp import TOTP

    user_repo = FakeUserRepo()
    user_repo.users["alice"] = FakeUser("alice", hash_password("hunter2"))
    service = AuthService(user_repo, FakeTokenRepo(), _settings())
    secret, _uri = await service.enroll_mfa(user_repo.users["alice"].id)
    await service.verify_mfa(user_repo.users["alice"].id, TOTP(secret).now())

    await service.disable_mfa(user_repo.users["alice"].id)

    user = user_repo.users["alice"]
    assert user.mfa_enabled is False
    assert user.mfa_secret is None
    # And login no longer requires a code.
    result = await service.login(UserLogin(username="alice", password="hunter2"))
    assert result.access_token


@pytest.mark.asyncio
async def test_re_enrolling_replaces_a_pending_secret_without_enabling_mfa() -> None:
    """An abandoned enrollment attempt must not lock anyone out -- calling
    enroll again just issues a fresh secret."""
    user_repo = FakeUserRepo()
    user_repo.users["alice"] = FakeUser("alice", hash_password("hunter2"))
    service = AuthService(user_repo, FakeTokenRepo(), _settings())

    first_secret, _uri = await service.enroll_mfa(user_repo.users["alice"].id)
    second_secret, _uri = await service.enroll_mfa(user_repo.users["alice"].id)

    assert first_secret != second_secret
    assert user_repo.users["alice"].mfa_enabled is False
