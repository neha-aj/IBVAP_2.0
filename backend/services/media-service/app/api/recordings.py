import datetime as dt
import mimetypes
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from ibvap_common.auth import TokenPayload, require_role
from ibvap_common.errors import ApiError, NotFoundError
from ibvap_common.internal_auth import verify_internal_token
from ibvap_common.stream_auth import build_resource_url, verify_resource_token

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.recording import Recording
from app.repositories.media_repo import MediaRepository
from app.schemas.recording import RecordingCreated, RecordingRead
from app.storage.local_backend import LocalStorageBackend

router = APIRouter(prefix="/media/recordings", tags=["recordings"])


@router.post("", response_model=RecordingCreated, status_code=201, dependencies=[Depends(verify_internal_token)])
async def create_recording(
    camera_id: str,
    start_time: dt.datetime,
    end_time: dt.datetime,
    duration_seconds: int,
    file: UploadFile,
    event_id: str | None = None,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RecordingCreated:
    """Stores a captured video clip (Phase 2 M23 -- the recording-segment
    producer doc09/doc08 anticipated but no milestone actually wired
    until now, see `models/recording.py`'s own "stays empty" docstring).
    Internal-only, same pattern as `POST /media/snapshots`: the caller
    (event-alert-service, on a critical-severity event) already validated
    `camera_id`/`event_id` against its own data."""
    data = await file.read()
    if len(data) > settings.max_recording_upload_size_bytes:
        raise ApiError(status_code=413, title="File too large")

    backend = LocalStorageBackend(settings.media_root, url_prefix=settings.media_url_prefix)
    today = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d")
    # .webm, not .mp4: event-alert-service's RecordingClient encodes clips as
    # VP8/WebM (no browser-playable H.264 encoder is available in that
    # container, and MP4's mp4v fallback isn't supported by any browser's
    # <video> element -- see recording_client.py's own comment). Storing
    # under the real extension keeps `mimetypes.guess_type` below correct
    # for whatever the caller actually uploaded, rather than mislabeling it.
    extension = Path(file.filename).suffix if file.filename else ".webm"
    url = await backend.save(subdir=f"recordings/{camera_id}/{today}", filename=f"clip{extension}", data=data)

    recording = await MediaRepository(session).create_recording(
        Recording(
            camera_id=camera_id, event_id=event_id, file_path=url,
            start_time=start_time, end_time=end_time, duration_seconds=duration_seconds,
        )
    )
    return RecordingCreated(id=str(recording.id), url=recording.file_path)


@router.get("/{recording_id}", response_model=RecordingRead)
async def get_recording(
    recording_id: str,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _user: TokenPayload = Depends(require_role("viewer")),
) -> RecordingRead:
    try:
        parsed_id = uuid.UUID(recording_id)
    except ValueError:
        raise NotFoundError(f"No recording with id {recording_id}") from None

    recording = await MediaRepository(session).get_recording(parsed_id)
    if recording is None:
        raise NotFoundError(f"No recording with id {recording_id}")
    return RecordingRead(
        id=str(recording.id),
        camera_id=recording.camera_id,
        start_time=recording.start_time,
        end_time=recording.end_time,
        duration_seconds=recording.duration_seconds,
        # M24 security review follow-up: same gap and fix as
        # `GET /media/snapshots/{id}` -- `recording.file_path` used to be
        # handed to the browser verbatim as a `<video src>`, which is
        # fetchable with zero auth via nginx's (now internal) static
        # alias. `require_role` above already gates *this* metadata call
        # (fetched via authenticated JS, not a plain `<video>` tag), so the
        # token here only needs to prove "the caller who fetched this JSON
        # is the one requesting the bytes", exactly like the mjpeg pattern.
        playback_url=build_resource_url(
            path=f"/media/recordings/{recording_id}/file", resource=recording_id, settings=settings
        ),
    )


@router.get("/{recording_id}/file")
async def get_recording_file(
    recording_id: str,
    token: str | None = Query(default=None),
    download: bool = Query(
        default=False,
        description="Evidence export: adds Content-Disposition: attachment so the "
        "browser saves the clip instead of playing it inline. Default False preserves "
        "the existing <video src> inline-playback behavior exactly.",
    ),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Byte-serving counterpart to `GET /media/recordings/{id}` above --
    split out because that route returns recording metadata as JSON, not
    the clip itself. No `require_role` here: the token (verified against
    this exact `recording_id`) is the auth, minted only after the metadata
    call's own role check already passed -- same shape as `GET /media/
    snapshots/{id}` and the mjpeg preview stream."""
    try:
        parsed_id = uuid.UUID(recording_id)
    except ValueError:
        raise NotFoundError(f"No recording with id {recording_id}") from None

    verify_resource_token(token, resource=recording_id, settings=settings)

    recording = await MediaRepository(session).get_recording(parsed_id)
    if recording is None:
        raise NotFoundError(f"No recording with id {recording_id}")
    content_type = mimetypes.guess_type(recording.file_path)[0] or "video/webm"
    headers = {"X-Accel-Redirect": recording.file_path}
    if download:
        # Evidence export for investigation -- a stable, human-readable
        # filename (camera + start time) rather than the on-disk "clip.webm"
        # every recording shares, so multiple exported clips don't collide
        # or need renaming by hand.
        stamp = recording.start_time.strftime("%Y%m%d-%H%M%S")
        extension = content_type.split("/")[-1] or "webm"
        headers["Content-Disposition"] = (
            f'attachment; filename="{recording.camera_id}_{stamp}.{extension}"'
        )
    return Response(status_code=200, media_type=content_type, headers=headers)
