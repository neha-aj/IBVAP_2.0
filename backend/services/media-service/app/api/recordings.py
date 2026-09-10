import datetime as dt
import mimetypes
import uuid

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
    url = await backend.save(subdir=f"recordings/{camera_id}/{today}", filename="clip.mp4", data=data)

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
    content_type = mimetypes.guess_type(recording.file_path)[0] or "video/mp4"
    return Response(status_code=200, media_type=content_type, headers={"X-Accel-Redirect": recording.file_path})
