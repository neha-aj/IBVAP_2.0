import datetime as dt
import uuid

from ibvap_common.auth import create_token, decode_token
from ibvap_common.errors import ConflictError, UnauthorizedError
from ibvap_common.settings import CommonSettings

from app.repositories.token_repo import TokenRepository
from app.repositories.user_repo import UserRepository
from app.schemas.token import TokenPair
from app.schemas.user import UserCreate, UserLogin, UserRead
from app.services.security import DUMMY_PASSWORD_HASH, hash_password, verify_password


class AuthService:
    """Business logic for login/refresh/logout/bootstrap.
    Routes stay thin; all decisions live here (Implementation Guide §3)."""

    def __init__(
        self,
        user_repo: UserRepository,
        token_repo: TokenRepository,
        settings: CommonSettings,
    ) -> None:
        self._users = user_repo
        self._tokens = token_repo
        self._settings = settings

    async def register(self, data: UserCreate) -> UserRead:
        existing = await self._users.get_by_username(data.username)
        if existing is not None:
            raise ConflictError(f"Username '{data.username}' is already taken")
        user = await self._users.create(data, hash_password(data.password))
        return UserRead.model_validate(user, from_attributes=True)

    async def login(self, data: UserLogin) -> TokenPair:
        user = await self._users.get_by_username(data.username)
        # Always run the bcrypt check, even against a dummy hash when the
        # user doesn't exist -- a real lookup and a miss must cost the same
        # so response timing can't be used to enumerate valid usernames.
        password_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
        password_ok = verify_password(data.password, password_hash)
        if user is None or not user.is_active or not password_ok:
            raise UnauthorizedError("Invalid username or password")

        access_token = create_token(
            user_id=str(user.id),
            username=user.username,
            role=user.role,  # type: ignore[arg-type]
            token_type="access",
            settings=self._settings,
        )
        refresh_token = create_token(
            user_id=str(user.id),
            username=user.username,
            role=user.role,  # type: ignore[arg-type]
            token_type="refresh",
            settings=self._settings,
        )
        expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(
            days=self._settings.refresh_token_expire_days
        )
        await self._tokens.store(user_id=user.id, raw_token=refresh_token, expires_at=expires_at)

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            user=UserRead.model_validate(user, from_attributes=True),
        )

    async def refresh(self, raw_refresh_token: str) -> TokenPair:
        payload = decode_token(raw_refresh_token, self._settings)
        if payload.type != "refresh":
            raise UnauthorizedError("A refresh token is required")
        if not await self._tokens.is_valid(raw_refresh_token):
            raise UnauthorizedError("Refresh token has been revoked or expired")

        user = await self._users.get_by_id(uuid.UUID(payload.sub))
        if user is None or not user.is_active:
            raise UnauthorizedError("User no longer active")

        # Rotate: revoke the old refresh token, issue a new pair.
        await self._tokens.revoke(raw_refresh_token)
        return await self._reissue(user)

    async def logout(self, raw_refresh_token: str) -> None:
        await self._tokens.revoke(raw_refresh_token)

    async def _reissue(self, user) -> TokenPair:
        access_token = create_token(
            user_id=str(user.id),
            username=user.username,
            role=user.role,
            token_type="access",
            settings=self._settings,
        )
        refresh_token = create_token(
            user_id=str(user.id),
            username=user.username,
            role=user.role,
            token_type="refresh",
            settings=self._settings,
        )
        expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(
            days=self._settings.refresh_token_expire_days
        )
        await self._tokens.store(user_id=user.id, raw_token=refresh_token, expires_at=expires_at)
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            user=UserRead.model_validate(user, from_attributes=True),
        )

    async def ensure_bootstrap_admin(self, username: str, password: str) -> None:
        """Creates the first admin user if the users table is empty
        (fresh install convenience, IG M1 completion criteria: 'can log in')."""
        if await self._users.count() == 0:
            await self.register(UserCreate(username=username, password=password, role="admin"))
