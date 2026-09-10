from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ibvap_common.auth import TokenPayload, require_role

from app.db.session import get_db
from app.repositories.sector_repo import SectorRepository
from app.schemas.sector import SectorRead

router = APIRouter(prefix="/api/v1/sectors", tags=["sectors"])


@router.get("", response_model=list[SectorRead])
async def list_sectors(
    session: AsyncSession = Depends(get_db),
    _user: TokenPayload = Depends(require_role("viewer")),
) -> list[SectorRead]:
    repo = SectorRepository(session)
    sectors = await repo.list_all()
    return [SectorRead.model_validate(s, from_attributes=True) for s in sectors]
