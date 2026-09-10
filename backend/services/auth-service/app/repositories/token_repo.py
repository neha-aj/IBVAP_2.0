import datetime as dt
import hashlib
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token import RefreshToken


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


class TokenRepository:
    """Data-access layer for `auth.refresh_tokens` (revocable refresh tokens)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def store(self, *, user_id: uuid.UUID, raw_token: str, expires_at: dt.datetime) -> None:
        record = RefreshToken(
            user_id=user_id, token_hash=_hash_token(raw_token), expires_at=expires_at
        )
        self._session.add(record)
        await self._session.commit()

    async def is_valid(self, raw_token: str) -> bool:
        token_hash = _hash_token(raw_token)
        result = await self._session.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked.is_(False),
                RefreshToken.expires_at > dt.datetime.now(dt.UTC),
            )
        )
        return result.scalar_one_or_none() is not None

    async def revoke(self, raw_token: str) -> None:
        token_hash = _hash_token(raw_token)
        await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .values(revoked=True)
        )
        await self._session.commit()
