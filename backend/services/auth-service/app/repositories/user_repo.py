import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.user import UserCreate


class UserRepository:
    """Data-access layer for `auth.users`. Routes/services never build raw
    queries themselves (Implementation Guide §3, Repository Pattern)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_username(self, username: str) -> User | None:
        result = await self._session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self._session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def count(self) -> int:
        from sqlalchemy import func

        result = await self._session.execute(select(func.count()).select_from(User))
        return int(result.scalar_one())

    async def create(self, data: UserCreate, password_hash: str) -> User:
        user = User(username=data.username, password_hash=password_hash, role=data.role)
        self._session.add(user)
        await self._session.commit()
        await self._session.refresh(user)
        return user
