"""Async SQLAlchemy engine/session factory, schema-aware.

Each service calls `build_session_factory(settings)` once at startup and
exposes a `get_db` FastAPI dependency from it. Keeping this in the shared
lib avoids every service re-writing identical engine/session boilerplate,
while each service still owns its own models/migrations (DB spec §6:
no cross-schema foreign keys, no shared ORM models).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from ibvap_common.settings import CommonSettings


def build_engine(settings: CommonSettings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={"server_settings": {"search_path": settings.db_schema}},
    )


def build_session_factory(settings: CommonSettings) -> async_sessionmaker[AsyncSession]:
    engine = build_engine(settings)
    return async_sessionmaker(engine, expire_on_commit=False)


async def check_db_ready(session_factory: async_sessionmaker[AsyncSession]) -> bool:
    from sqlalchemy import text

    try:
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
