from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.crud import source as source_crud
from app.deps import get_db, require_api_key
from app.schemas.source import SourceOut

router = APIRouter(prefix="/api/internal", tags=["internal"],
                   dependencies=[Depends(require_api_key)])


@router.get("/sources", response_model=list[SourceOut])
def list_sources(is_active: bool | None = True, db: Session = Depends(get_db)):
    return source_crud.list_sources(db, is_active=is_active)
