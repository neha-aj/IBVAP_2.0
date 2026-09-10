from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from ibvap_common.auth import TokenPayload, require_role
from ibvap_common.errors import NotFoundError

from app.db.session import get_db
from app.schemas.reid import MatchResult, SearchByTrackRequest
from app.services.reid_service import ReidService

router = APIRouter(prefix="/api/v1/reid", tags=["reid"])

ObjectType = Literal["person", "vehicle"]


def get_reid_service(
    request: Request,
    object_type: ObjectType = Query(default="person", alias="objectType"),
    session: AsyncSession = Depends(get_db),
) -> ReidService:
    """Phase 2 M17: `objectType` picks which of the two Re-ID tables/models
    (person vs. vehicle) this request searches -- defaults to "person" so
    every existing M16 caller keeps working unchanged."""
    manager = request.app.state.reconcile_manager
    if object_type == "vehicle":
        return manager.build_vehicle_reid_service(session)
    return manager.build_person_reid_service(session)


@router.post("/search", response_model=list[MatchResult])
async def search_by_track(
    payload: SearchByTrackRequest,
    camera: str = Query(..., description="camera_id the reference track belongs to"),
    object_type: ObjectType = Query(default="person", alias="objectType"),
    service: ReidService = Depends(get_reid_service),
    _user: TokenPayload = Depends(require_role("operator")),
) -> list[MatchResult]:
    """doc09 §2.2/§2.3: search using an already-tracked person's or vehicle's
    own stored embedding -- the "Find this elsewhere" flow (doc10 §2.3)."""
    matches = await service.search_by_track(camera_id=camera, track_id=payload.track_id)
    if not matches and not await service.has_embedding(camera_id=camera, track_id=payload.track_id):
        raise NotFoundError(
            f"No {object_type} embedding found for track '{payload.track_id}' on camera '{camera}'"
        )
    return matches


@router.post("/search/upload", response_model=list[MatchResult])
async def search_by_upload(
    file: UploadFile,
    service: ReidService = Depends(get_reid_service),
    _user: TokenPayload = Depends(require_role("operator")),
) -> list[MatchResult]:
    """doc10 §2.3: "upload/select a reference snapshot" -- an operator's own
    photo, not something already tracked by the pipeline. `?objectType=`
    (default "person") picks person vs. vehicle Re-ID (M17)."""
    data = await file.read()
    return await service.search_by_image(data)


@router.get("/matches", response_model=list[MatchResult])
async def get_matches(
    person_ref: str = Query(..., alias="personRef"),
    camera: str = Query(..., description="camera_id the reference track belongs to"),
    service: ReidService = Depends(get_reid_service),
    _user: TokenPayload = Depends(require_role("operator")),
) -> list[MatchResult]:
    """doc09 §2.2's `GET /reid/matches?personRef=` -- a read-only convenience
    alias over the same search-by-track-id logic as `POST /reid/search`.
    Kept the `personRef` param name for M16 backward compatibility even
    when `?objectType=vehicle` (M17) -- it's just "the reference track's id"
    regardless of object type."""
    return await service.search_by_track(camera_id=camera, track_id=person_ref)
