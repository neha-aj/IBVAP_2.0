import base64

from fastapi import APIRouter, Depends, Query, Response

from ibvap_common.errors import NotFoundError
from ibvap_common.internal_auth import verify_internal_token

from app.core.config import Settings, get_settings
from app.preview.frame_cache import frame_cache
from app.preview.frame_ring_buffer import frame_ring_buffer

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


@router.get("/{camera_id}/recent-frames")
async def get_recent_frames(
    camera_id: str,
    seconds: float = Query(default=30.0, gt=0),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Evidence pre-roll: returns up to the last `seconds` of this camera's
    rolling frame history (FrameRingBuffer), each frame base64-encoded JPEG
    with its capture timestamp (Unix seconds). Caller is event-alert-
    service's RecordingClient, assembling a pre+post-roll clip around an
    accident/event -- an internal, best-effort feed (may return fewer
    frames than requested, or none, if the camera only just started
    streaming), same spirit as `/snapshot` above.

    `seconds` is clamped to `preroll_buffer_seconds` -- the buffer itself
    never holds more than that regardless of what's asked for."""
    capped_seconds = min(seconds, settings.preroll_buffer_seconds)
    frames = await frame_ring_buffer.recent(camera_id, capped_seconds)
    return {
        "frames": [
            {"timestamp": ts, "jpeg": base64.b64encode(data).decode("ascii")} for ts, data in frames
        ]
    }
