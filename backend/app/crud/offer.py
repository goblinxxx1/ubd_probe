from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.errors import not_found, validation_error
from app.core.urlnorm import canonicalize_target_url
from app.models import Offer, OfferCategory, TargetCategory
from app.models.enums import CreatedBy, DiscountType, OfferStatus, OfferType
from app.schemas.offer import OfferCreate, OfferUpdate


def _load_categories(db: Session, target_ids, offer_ids):
    targets = db.query(TargetCategory).filter(TargetCategory.id.in_(target_ids)).all() if target_ids else []
    offers = db.query(OfferCategory).filter(OfferCategory.id.in_(offer_ids)).all() if offer_ids else []
    return targets, offers


def _apply_content(obj, data, canon, content_hash, targets, offers, mk_link):
    obj.type = data.type
    obj.title = data.title
    obj.description = data.description
    obj.provider = data.provider
    obj.location = data.location
    obj.valid_from = data.valid_from
    obj.valid_until = data.valid_until
    obj.discount_type = data.discount_type
    obj.discount_value = data.discount_value
    obj.site_url = data.site_url
    obj.article_url = data.article_url
    obj.image_url = data.image_url
    obj.target_url = data.target_url
    obj.target_url_canonical = canon
    obj.content_hash = content_hash
    obj.target_categories = targets
    obj.offer_categories = offers
    obj.links = [mk_link()]
    obj.last_seen_at = datetime.utcnow()


def create_offer(db: Session, data: OfferCreate, created_by: CreatedBy,
                 status: OfferStatus, source_id: int | None = None,
                 content_hash: str | None = None) -> Offer:
    from app.models.offer_link import OfferLink  # local import avoids cycle

    def _mk_link():
        return OfferLink(provider=data.provider, site_url=data.site_url,
                         article_url=data.article_url)

    canon = canonicalize_target_url(data.target_url) if data.target_url else None
    crawler = created_by == CreatedBy.crawler

    # 1) Unchanged (or idempotent repeat of an existing shadow): same source + content_hash.
    if content_hash is not None and crawler:
        q = db.query(Offer).filter(Offer.content_hash == content_hash)
        q = (q.filter(Offer.source_id == source_id) if source_id is not None
             else q.filter(Offer.source_id.is_(None)))
        existing = q.first()
        if existing is not None:
            existing.last_seen_at = datetime.utcnow()
            if existing.supersedes_offer_id is not None:
                parent = db.get(Offer, existing.supersedes_offer_id)
                if parent is not None:
                    parent.last_seen_at = datetime.utcnow()
            elif existing.status == OfferStatus.published:
                # Content reverted to this published offer's live value -> any pending
                # shadow proposing a now-gone change is stale; drop it from the queue.
                stale = (db.query(Offer)
                         .filter(Offer.supersedes_offer_id == existing.id,
                                 Offer.status == OfferStatus.pending_review)
                         .all())
                for sh in stale:
                    sh.status = OfferStatus.rejected
            db.commit()
            db.refresh(existing)
            return existing

    # Same-source change detection needs a canonical key and a source.
    if crawler and canon and source_id is not None:
        # 2) Change of a live (published) offer from this same source+target -> shadow.
        parent = (db.query(Offer)
                  .filter(Offer.source_id == source_id,
                          Offer.target_url_canonical == canon,
                          Offer.status == OfferStatus.published)
                  .order_by(Offer.id).first())
        if parent is not None:
            targets, offers = _load_categories(db, data.target_category_ids, data.offer_category_ids)
            shadow = (db.query(Offer)
                      .filter(Offer.supersedes_offer_id == parent.id,
                              Offer.status == OfferStatus.pending_review)
                      .order_by(Offer.id).first())
            if shadow is None:
                shadow = Offer(status=OfferStatus.pending_review, created_by=CreatedBy.crawler,
                               source_id=source_id, supersedes_offer_id=parent.id)
                db.add(shadow)
            _apply_content(shadow, data, canon, content_hash, targets, offers, _mk_link)
            parent.last_seen_at = datetime.utcnow()
            db.commit()
            db.refresh(shadow)
            return shadow

        # 3) First submission still pending (not yet approved) -> update in place, no shadow.
        pending = (db.query(Offer)
                   .filter(Offer.source_id == source_id,
                           Offer.target_url_canonical == canon,
                           Offer.status == OfferStatus.pending_review,
                           Offer.supersedes_offer_id.is_(None))
                   .order_by(Offer.id).first())
        if pending is not None:
            targets, offers = _load_categories(db, data.target_category_ids, data.offer_category_ids)
            _apply_content(pending, data, canon, content_hash, targets, offers, _mk_link)
            db.commit()
            db.refresh(pending)
            return pending

    # 4) Cross-source canonical merge (aggregator / cross-platform) — existing behavior.
    if crawler and canon:
        existing = (db.query(Offer).filter(Offer.target_url_canonical == canon)
                    .order_by(Offer.id).first())
        if existing is not None:
            already = any(l.provider == data.provider and l.site_url == data.site_url
                          and l.article_url == data.article_url for l in existing.links)
            if not already:
                existing.links.append(_mk_link())
            existing.last_seen_at = datetime.utcnow()
            db.commit()
            db.refresh(existing)
            return existing

    targets, offers = _load_categories(db, data.target_category_ids, data.offer_category_ids)
    obj = Offer(
        type=data.type, title=data.title, description=data.description, provider=data.provider,
        location=data.location, valid_from=data.valid_from, valid_until=data.valid_until,
        discount_type=data.discount_type, discount_value=data.discount_value,
        site_url=data.site_url, article_url=data.article_url, image_url=data.image_url,
        target_url=data.target_url, target_url_canonical=canon, source_id=source_id,
        status=status, created_by=created_by, content_hash=content_hash,
        last_seen_at=datetime.utcnow(),
        target_categories=targets, offer_categories=offers,
        links=[_mk_link()],
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
    if "target_url" in payload:
        obj.target_url_canonical = canonicalize_target_url(obj.target_url)
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
    if status == OfferStatus.published:
        obj.last_seen_at = datetime.utcnow()
        if obj.supersedes_offer_id is not None:
            parent = db.get(Offer, obj.supersedes_offer_id)
            if parent is not None and parent.status == OfferStatus.published:
                parent.status = OfferStatus.expired
    db.commit()
    db.refresh(obj)
    return obj


def delete_offer(db: Session, offer_id: int) -> None:
    obj = get_offer(db, offer_id)
    db.delete(obj)
    db.commit()


def list_published_since(db: Session, since: datetime | None = None):
    q = db.query(Offer).filter(Offer.status == OfferStatus.published)
    if since is not None:
        q = q.filter(Offer.updated_at > since)
    return q.order_by(Offer.updated_at.asc()).all()


def expire_stale(db: Session, older_than_days: int) -> int:
    cutoff = datetime.utcnow() - timedelta(days=older_than_days)
    rows = db.query(Offer).filter(
        Offer.status == OfferStatus.published,
        Offer.created_by == CreatedBy.crawler,
        Offer.source_id.isnot(None),
        Offer.last_seen_at < cutoff,
    ).all()
    for o in rows:
        o.status = OfferStatus.expired
    db.commit()
    return len(rows)
