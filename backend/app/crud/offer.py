import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.errors import not_found, validation_error
from app.core.urlnorm import canonicalize_target_url
from app.crud.blocked_host import bare_host, list_approved_hosts
from app.models import Offer, OfferCategory, OfferDiscount, OfferLocation, TargetCategory
from app.models.enums import CreatedBy, DiscountType, OfferStatus, OfferType
from app.schemas.offer import OfferCreate, OfferUpdate

log = logging.getLogger(__name__)


def _host_blocked(h: str, approved: set[str]) -> bool:
    return bool(h) and any(h == b or h.endswith("." + b) for b in approved)


def _source_host(value) -> str:
    """bare_host of a value, but only if it looks like a real host (has a dot).
    Free-text provider names like 'Biz' must NOT be treated as hosts."""
    h = bare_host(value or "")
    return h if "." in h else ""


def _blocked_source_host(db: Session, data) -> str | None:
    approved = set(list_approved_hosts(db))
    if not approved:
        return None
    for val in (getattr(data, "site_url", None), getattr(data, "article_url", None),
                getattr(data, "provider", None)):
        h = _source_host(val)
        if _host_blocked(h, approved):
            return h
    return None


def _norm_locations(names):
    seen, out = set(), []
    for n in names or []:
        n = (n or "").strip()
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _load_categories(db: Session, target_ids, offer_ids):
    targets = db.query(TargetCategory).filter(TargetCategory.id.in_(target_ids)).all() if target_ids else []
    offers = db.query(OfferCategory).filter(OfferCategory.id.in_(offer_ids)).all() if offer_ids else []
    return targets, offers


def _discount_rows(data):
    """Discount rows for an offer: the payload list, else a single synthesized entry
    from the top-level discount, else empty (event / no-discount)."""
    if getattr(data, "discounts", None):
        return [OfferDiscount(label=d.label, discount_type=d.discount_type,
                              discount_value=d.discount_value, sort_order=i)
                for i, d in enumerate(data.discounts)]
    if data.discount_type is not None:
        return [OfferDiscount(label=None, discount_type=data.discount_type,
                              discount_value=data.discount_value, sort_order=0)]
    return []


def _apply_content(obj, data, canon, canon_article, content_hash, targets, offers, mk_link):
    obj.type = data.type
    obj.title = data.title
    obj.description = data.description
    obj.provider = data.provider
    obj.location_names = _norm_locations(data.locations)
    obj.valid_from = data.valid_from
    obj.valid_until = data.valid_until
    obj.discount_type = data.discount_type
    obj.discount_value = data.discount_value
    obj.site_url = data.site_url
    obj.article_url = data.article_url
    obj.image_url = data.image_url
    obj.target_url = data.target_url
    obj.target_url_canonical = canon
    obj.article_url_canonical = canon_article
    obj.content_hash = content_hash
    obj.target_categories = targets
    obj.offer_categories = offers
    obj.discounts = _discount_rows(data)
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
    canon_article = canonicalize_target_url(data.article_url) if data.article_url else None
    crawler = created_by == CreatedBy.crawler
    blocked = crawler and _blocked_source_host(db, data) is not None
    if blocked:
        status = OfferStatus.rejected   # force-reject a blocked-source offer

    # 1) Unchanged (or idempotent repeat of an existing shadow): same source + content_hash.
    # NOTE: intentionally NOT guarded with `and not blocked` — this branch only bumps
    # last_seen_at / handles supersedes-shadow bookkeeping and returns the existing row; it
    # never appends a link, so it can't leak a blocked link into a published offer. It MUST run
    # for blocked offers too, otherwise a re-crawl of an already-rejected (source_id,
    # content_hash) row falls through and re-INSERTs, violating the unique constraint.
    if content_hash is not None and crawler:
        # Ignore expired rows here: a revert to an expired offer's content must fall through to
        # branch 2 for re-moderation, not short-circuit onto the dead row. Published/pending/
        # rejected still short-circuit (rejected stays final; unchanged live just bumps).
        q = db.query(Offer).filter(Offer.content_hash == content_hash,
                                   Offer.status != OfferStatus.expired)
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
    if crawler and canon_article and source_id is not None and not blocked:
        # 2) Change of a live (published) offer from this same source+page -> shadow.
        parent = (db.query(Offer)
                  .filter(Offer.source_id == source_id,
                          Offer.article_url_canonical == canon_article,
                          Offer.status == OfferStatus.published)
                  .order_by(Offer.id).first())
        if parent is not None:
            targets, offers = _load_categories(db, data.target_category_ids, data.offer_category_ids)
            # The shadow row is uniquely keyed by (source_id, content_hash). If a physical row with
            # this exact content already exists it can only be an expired one (branch 1 caught any
            # live/rejected match) — revive it so a revert to a previously-seen discount re-enters
            # moderation without colliding with the unique constraint. Otherwise reuse the in-flight
            # pending shadow for this parent, else create a fresh shadow.
            live_shadow = (db.query(Offer)
                           .filter(Offer.supersedes_offer_id == parent.id,
                                   Offer.status == OfferStatus.pending_review)
                           .order_by(Offer.id).first())
            revive = (db.query(Offer)
                      .filter(Offer.source_id == source_id, Offer.content_hash == content_hash)
                      .first()) if content_hash is not None else None
            if revive is not None:
                # Keep at most one pending shadow per parent: drop a different in-flight one.
                if live_shadow is not None and live_shadow.id != revive.id:
                    live_shadow.status = OfferStatus.rejected
                revive.supersedes_offer_id = parent.id
                revive.status = OfferStatus.pending_review
                shadow = revive
            elif live_shadow is not None:
                shadow = live_shadow
            else:
                shadow = Offer(status=OfferStatus.pending_review, created_by=CreatedBy.crawler,
                               source_id=source_id, supersedes_offer_id=parent.id)
                db.add(shadow)
            _apply_content(shadow, data, canon, canon_article, content_hash, targets, offers, _mk_link)
            parent.last_seen_at = datetime.utcnow()
            db.commit()
            db.refresh(shadow)
            return shadow

        # 3) First submission still pending (not yet approved) -> update in place, no shadow.
        pending = (db.query(Offer)
                   .filter(Offer.source_id == source_id,
                           Offer.article_url_canonical == canon_article,
                           Offer.status == OfferStatus.pending_review,
                           Offer.supersedes_offer_id.is_(None))
                   .order_by(Offer.id).first())
        if pending is not None:
            targets, offers = _load_categories(db, data.target_category_ids, data.offer_category_ids)
            _apply_content(pending, data, canon, canon_article, content_hash, targets, offers, _mk_link)
            db.commit()
            db.refresh(pending)
            return pending

    # 3b) Discovered-offer page dedup (active search, source_id=None). Branches 2/3 above are
    #     gated on `source_id is not None`, so an active-search offer for a page already in the
    #     queue would fall through and re-INSERT. Short-circuit here on article_url_canonical:
    #     bump last_seen and return the existing row without touching its content. Mirrors
    #     branch 1 but keyed on the page URL, so it also catches drifted-content re-crawls that
    #     branch 1 (exact content_hash) misses. NOT guarded with `and not blocked`: a blocked
    #     re-crawl with drifted content must collapse onto the existing rejected row, not
    #     re-INSERT. Excludes shadows (supersedes IS NULL) and expired rows (a revert to an
    #     expired page must fall through to re-moderation).
    if crawler and canon_article and source_id is None:
        existing = (db.query(Offer)
                    .filter(Offer.source_id.is_(None),
                            Offer.article_url_canonical == canon_article,
                            Offer.status != OfferStatus.expired,
                            Offer.supersedes_offer_id.is_(None))
                    .order_by(Offer.id).first())
        if existing is not None:
            existing.last_seen_at = datetime.utcnow()
            db.commit()
            db.refresh(existing)
            return existing

    # 4) Cross-source canonical merge (aggregator / cross-platform) — existing behavior.
    if crawler and canon and not blocked:
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
        valid_from=data.valid_from, valid_until=data.valid_until,
        discount_type=data.discount_type, discount_value=data.discount_value,
        site_url=data.site_url, article_url=data.article_url, image_url=data.image_url,
        target_url=data.target_url, target_url_canonical=canon,
        article_url_canonical=canon_article, source_id=source_id,
        status=status, created_by=created_by, content_hash=content_hash,
        last_seen_at=datetime.utcnow(),
        target_categories=targets, offer_categories=offers,
        discounts=_discount_rows(data),
        links=[_mk_link()],
    )
    obj.location_names = _norm_locations(data.locations)
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
                locations: list[str] | None = None, search: str | None = None,
                page: int = 1, size: int = 20):
    q = db.query(Offer)
    if status is not None:
        q = q.filter(Offer.status == status)
    if type is not None:
        q = q.filter(Offer.type == type)
    if locations:
        q = q.filter(Offer.locations.any(OfferLocation.name.in_(locations)))
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
    from app.models.offer_link import OfferLink  # local import avoids cycle
    obj = get_offer(db, offer_id)
    old_site, old_article = obj.site_url, obj.article_url
    payload = data.model_dump(exclude_unset=True)
    target_ids = payload.pop("target_category_ids", None)
    offer_ids = payload.pop("offer_category_ids", None)
    locations = payload.pop("locations", None)
    discounts = payload.pop("discounts", None)
    for field, value in payload.items():
        setattr(obj, field, value)
    if locations is not None:
        obj.location_names = _norm_locations(locations)
    if "target_url" in payload:
        obj.target_url_canonical = canonicalize_target_url(obj.target_url)
    if "article_url" in payload:
        obj.article_url_canonical = (canonicalize_target_url(obj.article_url)
                                     if obj.article_url else None)
    if discounts is not None:
        obj.discounts = _discount_rows(data)
    # Public renders offer.links (offer_links table), not the offer-level columns — keep the
    # offer's link(s) in sync so admin edits to provider/site_url/article_url reach the public site.
    if any(k in payload for k in ("provider", "site_url", "article_url")):
        if not obj.links:
            obj.links.append(OfferLink(provider=obj.provider, site_url=obj.site_url,
                                       article_url=obj.article_url))
        elif len(obj.links) == 1:
            link = obj.links[0]
            link.provider, link.site_url, link.article_url = obj.provider, obj.site_url, obj.article_url
        else:
            for link in obj.links:
                if link.site_url == old_site and link.article_url == old_article:
                    link.provider, link.site_url, link.article_url = obj.provider, obj.site_url, obj.article_url
                    break
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


_AUTOBLOCK_MIN_REJECTS = 2


def _offer_host_candidates(offer) -> set[str]:
    return {h for h in (_source_host(offer.site_url), _source_host(offer.article_url),
                        _source_host(offer.provider)) if h}


def host_reputation(db: Session, host: str, memo: dict) -> tuple[int, int]:
    """(published, rejected) count of offers whose bare source host matches `host`
    (exact-or-suffix on site_url/article_url/provider). Memoized per call-batch so a
    repeated host on the same page is counted once."""
    if host in memo:
        return memo[host]
    pub = rej = 0
    if host:
        like = f"%{host}%"
        rows = (db.query(Offer)
                .filter((Offer.site_url.like(like)) | (Offer.article_url.like(like))
                        | (Offer.provider.like(like))).all())
        for r in rows:
            if not any(_host_blocked(fh, {host}) for fh in _offer_host_candidates(r)):
                continue   # LIKE false-positive; exact/suffix host must match
            if r.status == OfferStatus.published:
                pub += 1
            elif r.status == OfferStatus.rejected:
                rej += 1
    memo[host] = (pub, rej)
    return memo[host]


def _maybe_autoblock_hosts(db: Session, offer) -> None:
    """After an offer is rejected, auto-block any source host with >=2 rejected and 0
    published offers (guard protects dual-status business hosts)."""
    from app.crud.blocked_host import auto_block
    approved = set(list_approved_hosts(db))
    for h in _offer_host_candidates(offer):
        if _host_blocked(h, approved):
            continue
        like = f"%{h}%"
        rows = (db.query(Offer)
                .filter((Offer.site_url.like(like)) | (Offer.article_url.like(like))
                        | (Offer.provider.like(like)))
                .all())
        rejected = published = 0
        for r in rows:
            if not any(_host_blocked(fh, {h}) for fh in _offer_host_candidates(r)):
                continue   # LIKE false-positive; exact/suffix host must match
            if r.status == OfferStatus.published:
                published += 1
            elif r.status == OfferStatus.rejected:
                rejected += 1
        if published == 0 and rejected >= _AUTOBLOCK_MIN_REJECTS:
            auto_block(db, h)


def set_status(db: Session, offer_id: int, status: OfferStatus, reviewed_by: int) -> Offer:
    obj = get_offer(db, offer_id)
    obj.status = status
    obj.reviewed_by = reviewed_by
    if status == OfferStatus.rejected:
        try:
            _maybe_autoblock_hosts(db, obj)
        except Exception as exc:  # noqa: BLE001 — learning is best-effort
            log.warning("auto-block learning failed for offer %s: %s", obj.id, exc)
    if status == OfferStatus.published:
        obj.last_seen_at = datetime.utcnow()
        if obj.supersedes_offer_id is not None:
            parent = db.get(Offer, obj.supersedes_offer_id)
            if parent is not None and parent.status == OfferStatus.published:
                parent.status = OfferStatus.expired
            # A published offer is the canonical live row — it no longer "supersedes" anything.
            # Clearing this after the parent-expire keeps the supersede graph acyclic (pending ->
            # published -> null), so reviving a former parent as a shadow can't form a 2-node FK
            # cycle (which selectin eager-load would flush as CircularDependencyError).
            obj.supersedes_offer_id = None
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


def list_rejected_since(db: Session, since: datetime | None = None):
    q = db.query(Offer).filter(Offer.status == OfferStatus.rejected,
                               Offer.created_by == CreatedBy.crawler)
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


def list_distinct_locations(db: Session, status: OfferStatus = OfferStatus.published):
    rows = (db.query(OfferLocation.name)
            .join(Offer, Offer.id == OfferLocation.offer_id)
            .filter(Offer.status == status)
            .distinct().order_by(OfferLocation.name).all())
    return [r[0] for r in rows]
