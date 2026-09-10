"""No ORM models here -- this service's whole job is querying materialized
views (created by raw-SQL Alembic migrations) and, across schemas, other
services' tables directly (SAS §3: "Postgres (reads across schemas via
views)", an explicitly sanctioned exception to the usual per-service-schema
isolation, specifically for read-only aggregation). Plain SQLAlemy Core
(`text()` queries via a session) is all that's needed."""

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ibvap_common.db import build_session_factory

from app.core.config import get_settings


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return build_session_factory(get_settings())


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session
