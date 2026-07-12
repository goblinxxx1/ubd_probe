from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.crud import offer as offer_crud
from app.crud import source as source_crud
from app.crud import suggested_source as suggestion_crud
from app.deps import get_db, require_api_key
from app.models.enums import CreatedBy, OfferStatus
from app.schemas.offer import OfferCreate, OfferOut
from app.schemas.source import SourceOut
from app.schemas.suggested_source import SuggestedSourceCreate, SuggestedSourceOut

router = APIRouter(prefix="/api/internal", tags=["internal"],
                   dependencies=[Depends(require_api_key)])


@router.get("/sources", response_model=list[SourceOut])
def list_sources(is_active: bool | None = True, db: Session = Depends(get_db)):
    return source_crud.list_sources(db, is_active=is_active)


class InternalOfferCreate(OfferCreate):
    source_id: int | None = None
    content_hash: str | None = None


@router.post("/offers", response_model=OfferOut)
def create_offer(data: InternalOfferCreate, db: Session = Depends(get_db)):
    if data.source_id is not None:
        source_crud.get_source(db, data.source_id)
    payload = OfferCreate(**data.model_dump(exclude={"source_id", "content_hash"}))
    return offer_crud.create_offer(db, payload, CreatedBy.crawler,
                                   OfferStatus.pending_review, source_id=data.source_id,
                                   content_hash=data.content_hash)


@router.post("/suggested-sources", response_model=SuggestedSourceOut)
def submit_suggested_source(data: SuggestedSourceCreate, db: Session = Depends(get_db)):
    return suggestion_crud.create_suggestion(db, data)
