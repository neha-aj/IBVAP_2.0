from fastapi import APIRouter, Depends, Response

from ibvap_common.errors import NotFoundError
from ibvap_common.internal_auth import verify_internal_token

from app.preview.frame_cache import frame_cache

router = APIRouter(
    prefix="/internal/cameras",
    tags=["internal"],
    dependencies=[Depends(verify_internal_token)],
)


@router.get("/{camera_id}/snapshot")
async def get_current_frame(camera_id: str) -> Response:
    """Returns this camera's most recently captured frame as a raw JPEG
    (SAS §5.5.2: "Detection/Ingestion service encodes the relevant frame
    as JPEG, sends to Media Storage Svc") -- the caller (Event/Alert
    Service, at event-creation time; a future manual-capture/periodic-
    thumbnail trigger) forwards these bytes to `POST /media/snapshots`.
    404s if this camera isn't currently streaming (no cached frame yet)."""
    jpeg_bytes = await frame_cache.get(camera_id)
    if jpeg_bytes is None:
        raise NotFoundError(f"No current frame cached for camera {camera_id}")
    return Response(content=jpeg_bytes, media_type="image/jpeg")
