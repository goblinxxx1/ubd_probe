from sqlalchemy.orm import Session

from app.core.errors import not_found, validation_error
from app.models import Offer, OfferCategory, TargetCategory
from app.models.enums import CreatedBy, DiscountType, OfferStatus, OfferType
from app.schemas.offer import OfferCreate, OfferUpdate


def _load_categories(db: Session, target_ids, offer_ids):
    targets = db.query(TargetCategory).filter(TargetCategory.id.in_(target_ids)).all() if target_ids else []
    offers = db.query(OfferCategory).filter(OfferCategory.id.in_(offer_ids)).all() if offer_ids else []
    return targets, offers


def create_offer(db: Session, data: OfferCreate, created_by: CreatedBy,
                 status: OfferStatus, source_id: int | None = None) -> Offer:
    targets, offers = _load_categories(db, data.target_category_ids, data.offer_category_ids)
    obj = Offer(
        type=data.type, title=data.title, description=data.description, provider=data.provider,
        location=data.location, valid_from=data.valid_from, valid_until=data.valid_until,
        discount_type=data.discount_type, discount_value=data.discount_value,
        contacts=data.contacts, image_url=data.image_url, source_id=source_id,
        status=status, created_by=created_by,
        target_categories=targets, offer_categories=offers,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_offer(db: Session, offer_id: int, published_only: bool = False) -> Offer:
    obj = db.get(Offer, offer_id)
    if obj is None or (published_only and obj.status != OfferStatus.published):
        raise not_found(f"Offer {offer_id} not found")
    return obj


def list_offers(db: Session, *, status: OfferStatus | None = None, type: OfferType | None = None,
                target_category_id: int | None = None, offer_category_id: int | None = None,
                location: str | None = None, search: str | None = None,
                page: int = 1, size: int = 20):
    q = db.query(Offer)
    if status is not None:
        q = q.filter(Offer.status == status)
    if type is not None:
        q = q.filter(Offer.type == type)
    if location:
        q = q.filter(Offer.location.ilike(f"%{location}%"))
    if search:
        like = f"%{search}%"
        q = q.filter((Offer.title.ilike(like)) | (Offer.description.ilike(like)) | (Offer.provider.ilike(like)))
    if target_category_id is not None:
        q = q.filter(Offer.target_categories.any(TargetCategory.id == target_category_id))
    if offer_category_id is not None:
        q = q.filter(Offer.offer_categories.any(OfferCategory.id == offer_category_id))
    total = q.count()
    items = q.order_by(Offer.created_at.desc()).offset((page - 1) * size).limit(size).all()
    return items, total


def update_offer(db: Session, offer_id: int, data: OfferUpdate) -> Offer:
    obj = get_offer(db, offer_id)
    payload = data.model_dump(exclude_unset=True)
    target_ids = payload.pop("target_category_ids", None)
    offer_ids = payload.pop("offer_category_ids", None)
    for field, value in payload.items():
        setattr(obj, field, value)
    if target_ids is not None:
        obj.target_categories = _load_categories(db, target_ids, [])[0]
    if offer_ids is not None:
        obj.offer_categories = _load_categories(db, [], offer_ids)[1]
    if obj.valid_from and obj.valid_until and obj.valid_until < obj.valid_from:
        raise validation_error("valid_until must be on or after valid_from")
    if obj.discount_type in (DiscountType.percent, DiscountType.fixed):
        if obj.discount_value is None:
            raise validation_error("discount_value required for percent/fixed discounts")
    else:
        if obj.discount_value is not None:
            raise validation_error("discount_value must be empty unless discount_type is percent/fixed")
    db.commit()
    db.refresh(obj)
    return obj


def set_status(db: Session, offer_id: int, status: OfferStatus, reviewed_by: int) -> Offer:
    obj = get_offer(db, offer_id)
    obj.status = status
    obj.reviewed_by = reviewed_by
    db.commit()
    db.refresh(obj)
    return obj


def delete_offer(db: Session, offer_id: int) -> None:
    obj = get_offer(db, offer_id)
    db.delete(obj)
    db.commit()
