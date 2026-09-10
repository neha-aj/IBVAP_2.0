from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from ibvap_common.auth import TokenPayload, require_role
from ibvap_common.errors import NotFoundError
from ibvap_common.redis_pubsub import publish_event

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.redis_client import get_redis_client
from app.repositories.alert_repo import AlertRepository
from app.schemas.alert import AlertDetail, AlertListResponse, AlertStatusUpdate, to_alert_detail, to_alert_read

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


@router.get("", response_model=AlertListResponse)
async def list_alerts(
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    camera: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200, alias="pageSize"),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _user: TokenPayload = Depends(require_role("viewer")),
) -> AlertListResponse:
    rows, total = await AlertRepository(session).list_paginated(
        camera_id=camera, severity=severity, status=status, page=page, page_size=page_size
    )
    return AlertListResponse(
        items=[to_alert_read(row, settings) for row in rows], total=total, page=page, page_size=page_size
    )


@router.get("/{alert_id}", response_model=AlertDetail)
async def get_alert(
    alert_id: str,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _user: TokenPayload = Depends(require_role("viewer")),
) -> AlertDetail:
    alert = await AlertRepository(session).get_by_id(alert_id)
    if alert is None:
        raise NotFoundError(f"No alert with id {alert_id}")
    return to_alert_detail(alert, settings)


@router.patch("/{alert_id}/status", response_model=AlertDetail)
async def update_alert_status(
    alert_id: str,
    payload: AlertStatusUpdate,
    session: AsyncSession = Depends(get_db),
    redis_client: Redis = Depends(get_redis_client),
    settings: Settings = Depends(get_settings),
    user: TokenPayload = Depends(require_role("operator")),
) -> AlertDetail:
    """Sets `acknowledgedBy`/`acknowledgedAt`/`resolvedAt` server-side
    (API Spec §5) and publishes `alert.updated` (SAS §5.4 step 5)."""
    repo = AlertRepository(session)
    alert = await repo.get_by_id(alert_id)
    if alert is None:
        raise NotFoundError(f"No alert with id {alert_id}")
    alert = await repo.update_status(alert, status=payload.status, acknowledged_by=user.sub)

    await publish_event(
        redis_client, "alert.updated", to_alert_read(alert, settings).model_dump(mode="json", by_alias=True)
    )
    return to_alert_detail(alert, settings)
