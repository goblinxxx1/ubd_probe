from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.crud import category as category_crud
from app.crud import offer as offer_crud
from app.deps import get_db
from app.models import OfferCategory, TargetCategory
from app.models.enums import OfferStatus, OfferType
from app.schemas.category import CategoryOut
from app.schemas.common import Page
from app.schemas.offer import OfferOut

router = APIRouter(prefix="/api", tags=["public"])


@router.get("/target-categories", response_model=list[CategoryOut])
def list_target_categories(db: Session = Depends(get_db)):
    return category_crud.list_categories(db, TargetCategory)


@router.get("/offer-categories", response_model=list[CategoryOut])
def list_offer_categories(db: Session = Depends(get_db)):
    return category_crud.list_categories(db, OfferCategory)


@router.get("/offers", response_model=Page[OfferOut])
def list_offers(type: OfferType | None = None, target_category: int | None = None,
                offer_category: int | None = None, location: str | None = None,
                q: str | None = None, page: int = 1, size: int = 20,
                db: Session = Depends(get_db)):
    items, total = offer_crud.list_offers(
        db, status=OfferStatus.published, type=type, target_category_id=target_category,
        offer_category_id=offer_category, location=location, search=q, page=page, size=size,
    )
    return Page(items=items, total=total, page=page, size=size)


@router.get("/offers/{offer_id}", response_model=OfferOut)
def get_offer(offer_id: int, db: Session = Depends(get_db)):
    return offer_crud.get_offer(db, offer_id, published_only=True)
