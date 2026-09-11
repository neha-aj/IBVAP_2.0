import asyncio

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from ibvap_common.stream_auth import verify_resource_token

from app.core.config import Settings, get_settings
from app.preview.frame_cache import frame_cache

router = APIRouter(tags=["preview"])

_BOUNDARY = "ibvapframe"


async def _mjpeg_generator(cache_key: str, *, interval_seconds: float):
    while True:
        jpeg_bytes = await frame_cache.get(cache_key)
        if jpeg_bytes is not None:
            yield (
                f"--{_BOUNDARY}\r\n"
                "Content-Type: image/jpeg\r\n"
                f"Content-Length: {len(jpeg_bytes)}\r\n\r\n"
            ).encode() + jpeg_bytes + b"\r\n"
        await asyncio.sleep(interval_seconds)


@router.get("/stream/{camera_id}/mjpeg")
async def mjpeg_stream(
    camera_id: str,
    token: str | None = Query(default=None),
    modality: str | None = Query(default=None, pattern="^(thermal)$"),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """Live preview for the Surveillance page's `VideoPlaceholder` slot
    (Frontend Analysis Report §3.2) -- an `<img src=".../mjpeg">` renders
    this directly, no video player library required.

    `token` (M24 security review): this route can't require the usual
    `Authorization` header (an `<img>` tag can't send one), so it instead
    requires the short-lived signed token that `GET /cameras/{id}/stream`
    -- which *is* gated by `require_role` -- mints and embeds in the URL
    it hands out. Without this, the stream was reachable by anyone who
    had (or guessed) a camera_id, regardless of role.

    `modality` (M11 gap-fill): a 'dual' camera's thermal half is cached
    under `f"{camera_id}:thermal"` by `CameraWorker._cache_key` -- this
    param selects that slot instead of the default RGB one. Not part of
    the token scope (the token is still just resource=camera_id) since it
    only ever selects between two halves of the same authorized camera."""
    verify_resource_token(token, resource=camera_id, settings=settings)
    cache_key = camera_id if modality is None else f"{camera_id}:{modality}"
    return StreamingResponse(
        _mjpeg_generator(cache_key, interval_seconds=1.0 / max(settings.preview_fps, 1)),
        media_type=f"multipart/x-mixed-replace; boundary={_BOUNDARY}",
    )
