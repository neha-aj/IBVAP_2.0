from fastapi import APIRouter, Depends, Request

from ibvap_common.auth import TokenPayload, require_role

router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/health")
async def system_health(request: Request, _user: TokenPayload = Depends(require_role("viewer"))) -> list[dict]:
    """Current status of every monitored service, for the Sidebar's
    "System Status" widget's initial paint -- the `system.health` WS topic
    only ever carries *future* changes (see `HealthPoller`'s own
    docstring), so a client needs this once at connect time to know
    current state rather than assuming healthy until told otherwise."""
    poller = request.app.state.health_poller
    return [{"service": name, "status": status} for name, status in poller.snapshot().items()]
