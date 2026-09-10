from fastapi import APIRouter

from ibvap_common.db import check_db_ready

from app.db.session import get_session_factory

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict:
    ok = await check_db_ready(get_session_factory())
    return {"status": "ok" if ok else "unavailable", "database": ok}
