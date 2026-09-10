from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all reid-service ORM models (schema=reid)."""


def _build_reid_engine() -> AsyncEngine:
    # Not ibvap_common.db.build_engine(): that sets search_path to this
    # service's own schema only ("reid"), which is right for every other
    # service but breaks pgvector here -- the `vector` type AND its `<=>`
    # operator both live in `public` (where the extension was installed),
    # and unqualified type/operator names only resolve against schemas on
    # search_path. Confirmed live: search_path="reid" alone produced
    # "type vector does not exist" (an explicit CAST) and then, once that
    # was qualified, "operator does not exist: public.vector <=> public.
    # vector" (the operator itself unresolved). Prepending "reid" keeps
    # this service's own unqualified table/column references finding
    # `reid.*` first, exactly as before.
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={"server_settings": {"search_path": f"{settings.db_schema},public"}},
    )


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(_build_reid_engine(), expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session
