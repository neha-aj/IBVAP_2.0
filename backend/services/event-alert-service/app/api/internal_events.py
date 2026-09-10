"""Phase 2 doc08 §4's shared internal event contract -- see
`schemas/internal.py::ExternalDetectionEvent`'s docstring for the full
rationale. This is the one new endpoint every Category B AI service (ANPR
first, M15) posts a positive detection to."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ibvap_common.internal_auth import verify_internal_token

from app.db.session import get_db
from app.rules.engine import EventDraft
from app.schemas.internal import ExternalDetectionEvent
from app.streaming.pubsub_publisher import PubSubPublisher

router = APIRouter(
    prefix="/internal/events",
    tags=["internal"],
    dependencies=[Depends(verify_internal_token)],
)


def get_publisher(request: Request) -> PubSubPublisher:
    return request.app.state.reconcile_manager.publisher


@router.post("", status_code=201)
async def ingest_external_event(
    payload: ExternalDetectionEvent,
    session: AsyncSession = Depends(get_db),
    publisher: PubSubPublisher = Depends(get_publisher),
) -> dict:
    draft = EventDraft(
        camera_id=payload.camera_id,
        event_type=payload.event_type,
        object_type=payload.object_type,
        severity=payload.severity,
        description=payload.description,
        requires_review=payload.requires_review,
    )
    await publisher.persist_and_publish(session, draft)
    return {"status": "accepted"}
