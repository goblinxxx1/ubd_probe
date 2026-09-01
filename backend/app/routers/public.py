from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.crud import category as category_crud
from app.crud import offer as offer_crud
from app.deps import get_db
from app.models import OfferCategory, TargetCategory
from app.models.enums import OfferStatus, OfferType
from app.schemas.category import CategoryOut
from app.schemas.common import Page
from app.schemas.facets import CategoryFacet, FacetsOut, LocationFacet, TypeFacet
from app.schemas.offer import OfferOut

router = APIRouter(prefix="/api", tags=["public"])


@router.get("/target-categories", response_model=list[CategoryOut])
def list_target_categories(db: Session = Depends(get_db)):
    return category_crud.list_categories(db, TargetCategory)


@router.get("/offer-categories", response_model=list[CategoryOut])
def list_offer_categories(db: Session = Depends(get_db)):
    return category_crud.list_categories(db, OfferCategory)


@router.get("/locations", response_model=list[str])
def list_locations(db: Session = Depends(get_db)):
    return offer_crud.list_distinct_locations(db)


@router.get("/facets", response_model=FacetsOut)
def list_facets(type: list[OfferType] | None = Query(None),
                target_category: list[int] | None = Query(None),
                offer_category: list[int] | None = Query(None),
                location: list[str] | None = Query(None),
                q: str | None = None, db: Session = Depends(get_db)):
    # Маркетплейс-стиль контекстних фасетів: лічильники кожного фасету враховують усі ІНШІ
    # активні фасети, але ігнорують власний вибір (дизʼюнктивність) — щоб опції ніколи
    # не занулювали самі себе.
    tc = offer_crud.facet_target_categories(db, types=type, offer_category_ids=offer_category,
                                            locations=location, search=q, selected_ids=target_category)
    oc = offer_crud.facet_offer_categories(db, types=type, target_category_ids=target_category,
                                           locations=location, search=q, selected_ids=offer_category)
    tp = offer_crud.facet_types(db, target_category_ids=target_category, offer_category_ids=offer_category,
                                locations=location, search=q, selected=type)
    loc = offer_crud.facet_locations(db, types=type, target_category_ids=target_category,
                                     offer_category_ids=offer_category, search=q, selected=location)
    return FacetsOut(
        target_categories=[CategoryFacet(id=i, name=n, count=c) for i, n, c in tc],
        offer_categories=[CategoryFacet(id=i, name=n, count=c) for i, n, c in oc],
        types=[TypeFacet(value=v, count=c) for v, c in tp],
        locations=[LocationFacet(name=n, count=c) for n, c in loc],
    )


@router.get("/offers", response_model=Page[OfferOut])
def list_offers(type: list[OfferType] | None = Query(None),
                target_category: list[int] | None = Query(None),
                offer_category: list[int] | None = Query(None),
                location: list[str] | None = Query(None),
                q: str | None = None, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                db: Session = Depends(get_db)):
    # All facets are multi-select checkbox groups on the public sidebar. Within a facet the
    # selected values are OR-ed; different facets are AND-ed. A single repeated value still
    # arrives as a one-element list, so old single-value links keep working.
    items, total = offer_crud.list_offers(
        db, status=OfferStatus.published, types=type, target_category_ids=target_category,
        offer_category_ids=offer_category, locations=location,
        search=q, hide_expired=True, page=page, size=size,
    )
    return Page(items=items, total=total, page=page, size=size)


@router.get("/offers/{offer_id}", response_model=OfferOut)
def get_offer(offer_id: int, preview: bool = False, db: Session = Depends(get_db)):
    # preview=true lets the admin moderation queue render an as-yet-unpublished offer on
    # the real public page. Offers are non-sensitive discount listings.
    return offer_crud.get_offer(db, offer_id, published_only=not preview)
