import json

from fastapi import APIRouter, Depends, Query, Request, Response, UploadFile
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from ibvap_common.auth import TokenPayload, require_role
from ibvap_common.errors import ApiError, NotFoundError
from ibvap_common.stream_auth import create_resource_token

from app.clients.ingestion_client import IngestionClient
from app.clients.media_client import MediaClient
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.redis_client import get_redis_client
from app.repositories.camera_repo import CameraRepository
from app.repositories.sector_repo import SectorRepository
from app.schemas.camera import (
    CameraCreate,
    CameraDetail,
    CameraListResponse,
    CameraStatusSummary,
    CameraUpdate,
    StreamInfo,
)
from app.schemas.detection import DetectionRead
from app.services.camera_service import CameraService

router = APIRouter(prefix="/api/v1/cameras", tags=["cameras"])


def get_camera_service(session: AsyncSession = Depends(get_db)) -> CameraService:
    return CameraService(CameraRepository(session), SectorRepository(session))


def get_media_client(request: Request, settings: Settings = Depends(get_settings)) -> MediaClient:
    return MediaClient(request.app.state.http_client, settings)


def get_ingestion_client(request: Request, settings: Settings = Depends(get_settings)) -> IngestionClient:
    return IngestionClient(request.app.state.http_client, settings)


@router.get("", response_model=CameraListResponse)
async def list_cameras(
    status: str | None = Query(default=None),
    sector: str | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    service: CameraService = Depends(get_camera_service),
    _user: TokenPayload = Depends(require_role("viewer")),
) -> CameraListResponse:
    return await service.list_cameras(
        status=status, sector=sector, search=search, page=page, page_size=page_size
    )


@router.get("/status/summary", response_model=CameraStatusSummary)
async def status_summary(
    service: CameraService = Depends(get_camera_service),
    _user: TokenPayload = Depends(require_role("viewer")),
) -> CameraStatusSummary:
    return await service.status_summary()


@router.get("/{camera_id}", response_model=CameraDetail)
async def get_camera(
    camera_id: str,
    service: CameraService = Depends(get_camera_service),
    _user: TokenPayload = Depends(require_role("viewer")),
) -> CameraDetail:
    return await service.get_camera(camera_id)


@router.get("/{camera_id}/stream", response_model=StreamInfo)
async def get_stream_info(
    camera_id: str,
    modality: str | None = Query(default=None, pattern="^(thermal)$"),
    service: CameraService = Depends(get_camera_service),
    settings: Settings = Depends(get_settings),
    _user: TokenPayload = Depends(require_role("viewer")),
) -> StreamInfo:
    """Confirms the camera exists, then returns the live-preview URL served
    by the Stream Ingestion Service (M3) and proxied through NGINX at
    `/stream/...` -- see nginx/conf.d/api-gateway.conf.

    The URL carries a short-lived signed `?token=` (M24 security review):
    it's rendered straight into an `<img src="...">` by the frontend, which
    can't attach an `Authorization` header, so without this the stream
    itself would be reachable by anyone who has (or guesses) a camera_id --
    this endpoint is the only gate, since it's the only place that's
    actually checked `require_role` before handing the URL out.

    `modality` (M11 gap-fill): pass `modality=thermal` to get a 'dual'
    camera's thermal half instead of its default RGB stream -- forwarded
    as-is to the ingestion-service mjpeg route, which reads the matching
    `CameraWorker._cache_key` slot. Not folded into the token itself (still
    scoped to just `resource=camera_id`), since it only selects between two
    halves of the same already-authorized camera."""
    await service.get_camera(camera_id)  # 404s if unknown
    token = create_resource_token(
        resource=camera_id, ttl_seconds=settings.stream_token_ttl_seconds, settings=settings
    )
    modality_qs = f"&modality={modality}" if modality else ""
    return StreamInfo(mjpeg_url=f"/stream/{camera_id}/mjpeg?token={token}{modality_qs}", hls_url=None)


@router.get("/{camera_id}/snapshot")
async def get_snapshot(
    camera_id: str,
    service: CameraService = Depends(get_camera_service),
    client: IngestionClient = Depends(get_ingestion_client),
    _user: TokenPayload = Depends(require_role("viewer")),
) -> Response:
    """Phase 2 M23 -- the documented Phase 1 M7 gap: a public, JWT-
    protected still-frame endpoint (Ingestion Service's own equivalent is
    internal/M2M-only, for other services, not a user's browser)."""
    await service.get_camera(camera_id)  # 404s if unknown
    jpeg_bytes = await client.get_snapshot(camera_id)
    if jpeg_bytes is None:
        raise NotFoundError(f"No current frame available for camera {camera_id}")
    return Response(content=jpeg_bytes, media_type="image/jpeg")


@router.get("/{camera_id}/detections/current", response_model=list[DetectionRead])
async def get_current_detections(
    camera_id: str,
    service: CameraService = Depends(get_camera_service),
    redis_client: Redis = Depends(get_redis_client),
    _user: TokenPayload = Depends(require_role("viewer")),
) -> list[DetectionRead]:
    """Live overlay data for the Surveillance page (API Spec §2). Detection
    Service (M4) writes `cam:{id}:current_detections` with a short TTL, so an
    offline/idle camera naturally reads back empty once the key expires."""
    await service.get_camera(camera_id)  # 404s if unknown
    raw = await redis_client.get(f"cam:{camera_id}:current_detections")
    if raw is None:
        return []
    return [DetectionRead(**item) for item in json.loads(raw)]


@router.post("", response_model=CameraDetail, status_code=201)
async def create_camera(
    payload: CameraCreate,
    service: CameraService = Depends(get_camera_service),
    _user: TokenPayload = Depends(require_role("admin")),
) -> CameraDetail:
    return await service.create_camera(payload)


@router.put("/{camera_id}", response_model=CameraDetail)
async def update_camera(
    camera_id: str,
    payload: CameraUpdate,
    service: CameraService = Depends(get_camera_service),
    _user: TokenPayload = Depends(require_role("admin")),
) -> CameraDetail:
    return await service.update_camera(camera_id, payload)


@router.delete("/{camera_id}", status_code=204)
async def delete_camera(
    camera_id: str,
    service: CameraService = Depends(get_camera_service),
    _user: TokenPayload = Depends(require_role("admin")),
) -> None:
    await service.delete_camera(camera_id)


@router.post("/{camera_id}/upload", response_model=CameraDetail)
async def upload_video(
    camera_id: str,
    file: UploadFile,
    slot: str = Query(default="rgb", pattern="^(rgb|thermal)$"),
    service: CameraService = Depends(get_camera_service),
    settings: Settings = Depends(get_settings),
    media_client: MediaClient = Depends(get_media_client),
    _user: TokenPayload = Depends(require_role("admin")),
) -> CameraDetail:
    """Uploads a video file for a `file`-type camera (per the "any source
    video I insert" requirement). The Stream Ingestion Service (M3) reads
    from the resulting path exactly as it would an RTSP URL. Phase 2 M23:
    the actual file write is now proxied to Media Service rather than
    handled by this service's own (now-retired) storage backend -- see
    `MediaClient.upload_source`'s own docstring.

    M11: `thermal`/`dual` cameras accept uploads too now (see
    `CameraService.set_uploaded_source`'s own docstring for why) --
    `slot=thermal` on a `dual` camera fills its second stream instead of
    the primary one."""
    # Validate the camera exists (and is upload-eligible) *before*
    # forwarding anything -- a bad/unknown camera_id must never result in
    # a stored file with nothing to attach it to.
    await service.get_camera(camera_id)

    if file.content_type is None or not file.content_type.startswith("video/"):
        raise ApiError(status_code=415, title="Unsupported media type", detail="Expected a video file")

    data = await file.read()
    if len(data) > settings.max_upload_size_bytes:
        raise ApiError(status_code=413, title="File too large")

    stored_path = await media_client.upload_source(camera_id=camera_id, filename=file.filename or "video", data=data)
    return await service.set_uploaded_source(camera_id, stored_path, slot=slot)
