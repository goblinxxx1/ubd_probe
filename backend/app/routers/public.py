from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.crud import category as category_crud
from app.deps import get_db
from app.models import OfferCategory, TargetCategory
from app.schemas.category import CategoryOut

router = APIRouter(prefix="/api", tags=["public"])


@router.get("/target-categories", response_model=list[CategoryOut])
def list_target_categories(db: Session = Depends(get_db)):
    return category_crud.list_categories(db, TargetCategory)


@router.get("/offer-categories", response_model=list[CategoryOut])
def list_offer_categories(db: Session = Depends(get_db)):
    return category_crud.list_categories(db, OfferCategory)
