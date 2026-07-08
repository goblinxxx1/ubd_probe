from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.crud import offer as offer_crud
from app.crud import source as source_crud
from app.deps import get_db, require_api_key
from app.models.enums import CreatedBy, OfferStatus
from app.schemas.offer import OfferCreate, OfferOut
from app.schemas.source import SourceOut

router = APIRouter(prefix="/api/internal", tags=["internal"],
                   dependencies=[Depends(require_api_key)])


@router.get("/sources", response_model=list[SourceOut])
def list_sources(is_active: bool | None = True, db: Session = Depends(get_db)):
    return source_crud.list_sources(db, is_active=is_active)


class InternalOfferCreate(OfferCreate):
    source_id: int | None = None


@router.post("/offers", response_model=OfferOut)
def create_offer(data: InternalOfferCreate, db: Session = Depends(get_db)):
    payload = OfferCreate(**data.model_dump(exclude={"source_id"}))
    return offer_crud.create_offer(db, payload, CreatedBy.crawler,
                                   OfferStatus.pending_review, source_id=data.source_id)
