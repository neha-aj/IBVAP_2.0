from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from ibvap_common.db import build_session_factory

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all media-service ORM models (schema=media)."""


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return build_session_factory(get_settings())


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session
