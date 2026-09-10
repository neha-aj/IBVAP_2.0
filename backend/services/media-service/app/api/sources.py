"""Phase 2 M23 -- closes the documented Phase 1 M7 gap: `StorageBackend`'s
own docstring in camera-service said "Once M7 lands, camera uploads should
be proxied there instead" -- M7 (this service) has existed since then, but
camera-service kept writing uploaded source videos to its own local
`LocalStorageBackend` copy instead of ever being wired to call here. This
is that missing proxy target: Media Service becomes the single owner of
every stored file (snapshots, recordings, and now camera source uploads),
not just two of the three."""

import os

from fastapi import APIRouter, Depends, UploadFile

from ibvap_common.errors import ApiError
from ibvap_common.internal_auth import verify_internal_token

from app.core.config import Settings, get_settings
from app.schemas.source import SourceStored
from app.storage.local_backend import LocalStorageBackend

router = APIRouter(
    prefix="/internal/media/sources",
    tags=["internal"],
    dependencies=[Depends(verify_internal_token)],
)


@router.post("", response_model=SourceStored, status_code=201)
async def store_source(
    camera_id: str,
    file: UploadFile,
    settings: Settings = Depends(get_settings),
) -> SourceStored:
    data = await file.read()
    if len(data) > settings.max_source_upload_size_bytes:
        raise ApiError(status_code=413, title="File too large")

    # No `url_prefix` -- returns the raw filesystem path (see
    # `LocalStorageBackend`'s own docstring for why this one case differs
    # from every other call site in this service). `camera_id` is
    # freeform caller input reaching a filesystem path -- sanitized the
    # same way camera-service's own (now-retired) upload handler did.
    backend = LocalStorageBackend(settings.media_root)
    safe_camera_id = os.path.basename(camera_id)
    path = await backend.save(subdir=f"uploads/{safe_camera_id}", filename=file.filename or "video", data=data)
    return SourceStored(path=path)
