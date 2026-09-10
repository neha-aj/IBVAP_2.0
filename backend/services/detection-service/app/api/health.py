from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request) -> dict:
    manager = getattr(request.app.state, "consumer_manager", None)
    active_consumers = manager.active_consumer_count if manager else 0
    return {"status": "ok", "activeConsumers": active_consumers}
