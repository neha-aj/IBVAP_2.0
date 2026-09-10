import datetime as dt
import mimetypes
import uuid

from fastapi import APIRouter, Depends, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from ibvap_common.errors import ApiError, NotFoundError
from ibvap_common.internal_auth import verify_internal_token
from ibvap_common.stream_auth import verify_resource_token

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.snapshot import Snapshot
from app.repositories.media_repo import MediaRepository
from app.schemas.snapshot import SnapshotCreated
from app.storage.local_backend import LocalStorageBackend

router = APIRouter(prefix="/media/snapshots", tags=["snapshots"])


@router.post("", response_model=SnapshotCreated, status_code=201, dependencies=[Depends(verify_internal_token)])
async def create_snapshot(
    camera_id: str,
    file: UploadFile,
    event_id: str | None = None,
    width: int | None = None,
    height: int | None = None,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SnapshotCreated:
    """Stores a captured frame (SAS §5.5.2) -- called by whatever pipeline
    stage has a decoded frame in hand at trigger time (Event/Alert Service
    at event-creation time, today; Ingestion/Detection for future manual-
    capture or periodic-thumbnail triggers, SAS §5.5.1). Internal-only:
    the caller already validated `camera_id`/`event_id` against their own
    services."""
    data = await file.read()
    if len(data) > settings.max_upload_size_bytes:
        raise ApiError(status_code=413, title="File too large")

    backend = LocalStorageBackend(settings.media_root, url_prefix=settings.media_url_prefix)
    today = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d")
    url = await backend.save(subdir=f"snapshots/{camera_id}/{today}", filename="snapshot.jpg", data=data)

    snapshot = await MediaRepository(session).create_snapshot(
        Snapshot(camera_id=camera_id, event_id=event_id, file_path=url, width=width, height=height)
    )
    return SnapshotCreated(id=str(snapshot.id), url=snapshot.file_path)


@router.get("/{snapshot_id}")
async def get_snapshot(
    snapshot_id: str,
    token: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    """`GET /media/snapshots/{id}` (API Spec §6): "Snapshot image/binary or
    signed URL". M24 security review follow-up: this used to redirect the
    browser straight to the nginx-served static path with no auth at all --
    and that path is a plain public alias, so the redirect target was
    fetchable by anyone regardless of this route's own auth. Now gated the
    same way as the mjpeg preview stream (`stream_auth.py`): the endpoint
    that hands this URL to the frontend (anpr-service's `GET /reads`,
    reid-service's search endpoints, event-alert-service's event/alert
    detail endpoints -- all already `require_role`-gated) mints a short-
    lived `?token=` scoped to this exact `snapshot_id`; verified here.
    Once verified, the response is served via `X-Accel-Redirect` rather
    than a browser-visible redirect: nginx's `/media/` alias is now
    `internal` (unreachable directly), so this is the only path to the
    bytes, and nginx streams them without an extra round trip through
    this service."""
    try:
        parsed_id = uuid.UUID(snapshot_id)
    except ValueError:
        raise NotFoundError(f"No snapshot with id {snapshot_id}") from None

    verify_resource_token(token, resource=snapshot_id, settings=settings)

    snapshot = await MediaRepository(session).get_snapshot(parsed_id)
    if snapshot is None:
        raise NotFoundError(f"No snapshot with id {snapshot_id}")
    content_type = mimetypes.guess_type(snapshot.file_path)[0] or "image/jpeg"
    return Response(status_code=200, media_type=content_type, headers={"X-Accel-Redirect": snapshot.file_path})
