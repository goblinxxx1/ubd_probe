import logging
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session, selectinload

from app.core.errors import conflict, not_found, validation_error
from app.core.urlnorm import canonicalize_target_url
from app.crud.blocked_host import bare_host, list_approved_hosts
from app.crud import directory_host as directory_host_crud
from app.models import Offer, OfferCategory, OfferDiscount, OfferLocation, TargetCategory
from app.models.enums import CreatedBy, DiscountType, OfferStatus, OfferType, VALUE_DISCOUNT_TYPES
from app.core.config import settings
from app.crud.dedup import normalize_tokens, discount_magnitudes, is_duplicate_promo, is_hub_page
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


def _directory_source_host(db: Session, data) -> str | None:
    """Джерело офера — зареєстрований хост-каталог (Task 6/7): такий офер належить
    каталогу-агрегатору, а не бізнесу, і в модерацію не має потрапляти (belt-and-suspenders
    до краулерного пригнічення)."""
    for val in (getattr(data, "site_url", None), getattr(data, "article_url", None)):
        h = _source_host(val)
        if h and directory_host_crud.is_directory(db, h):
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


def _promo_text(obj) -> str:
    """Text identifying a promo: its discount paragraph plus all discount labels.
    Excludes title (business tagline, identical across a host's pages)."""
    parts = [getattr(obj, "description", None) or ""]
    for d in (getattr(obj, "discounts", None) or []):
        lbl = getattr(d, "label", None)
        if lbl:
            parts.append(lbl)
    return " ".join(parts)


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
    obj.logo_url = data.logo_url
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
    blocked = crawler and (_blocked_source_host(db, data) is not None
                           or _directory_source_host(db, data) is not None)
    if blocked:
        status = OfferStatus.rejected   # force-reject a blocked- or directory-source offer

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
            # Re-moderate only on a MEANINGFUL discount change. If the published offer's
            # discount magnitudes are still fully present in the re-crawl, the difference is
            # extraction noise (relabeled text, provider drift, spurious free footnotes, dup
            # rows) — not a merchant change — so bump last_seen and keep the published row
            # instead of spawning a shadow that floods the moderation queue every re-crawl.
            new_mags = discount_magnitudes(getattr(data, "discounts", None),
                                           data.discount_type, data.discount_value)
            parent_mags = discount_magnitudes(parent.discounts, parent.discount_type,
                                              parent.discount_value)
            if parent_mags and parent_mags <= new_mags:
                parent.last_seen_at = datetime.utcnow()
                db.commit()
                db.refresh(parent)
                return parent
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

    # 3c) Same-promo dedup (host + discount-magnitude subset + text similarity). One promo
    #     appears on many pages worded differently (apex, /pro-nas, /category, /promotions);
    #     exact-label matching missed the reworded copies. Candidates are crawler offers on the
    #     SAME host with status != expired, which includes published, pending, AND rejected
    #     rows. This is intentional: collapsing a re-discovered, similarly-worded promo onto a
    #     previously rejected row keeps it rejected rather than re-flooding the moderation
    #     queue with the same rejected promo under a new URL — mirroring the "rejected stays
    #     final" behavior of branches 1 and 3b. Shadows are INCLUDED as targets, so a new page's
    #     offer collapses onto an in-flight shadow of the same promo. Conservative: below the
    #     threshold the offers stay distinct (two real same-% offers survive). The candidate
    #     query scans all same-host crawler offers in Python (magnitude-subset matching can't
    #     be pushed to SQL); acceptable at current scale.
    if crawler and not blocked and data.discount_type is not None:
        host = _source_host(getattr(data, "site_url", None)) or _source_host(getattr(data, "article_url", None))
        new_text = normalize_tokens(_promo_text(data))
        new_mags = discount_magnitudes(getattr(data, "discounts", None),
                                       data.discount_type, data.discount_value)
        if host and new_mags:
            threshold = settings.dedup_text_similarity_threshold
            cands = (db.query(Offer)
                     .options(selectinload(Offer.discounts))
                     .filter(Offer.created_by == CreatedBy.crawler,
                             Offer.status != OfferStatus.expired)
                     .order_by(Offer.id).all())
            for c in cands:
                c_host = _source_host(c.site_url) or _source_host(c.article_url)
                if c_host != host:
                    continue
                c_mags = discount_magnitudes(c.discounts, c.discount_type, c.discount_value)
                if is_duplicate_promo(new_text, new_mags, normalize_tokens(_promo_text(c)),
                                      c_mags, threshold):
                    c.last_seen_at = datetime.utcnow()
                    db.commit()
                    db.refresh(c)
                    return c

    # 3d) Hub-page dedup (generalizes the old apex-only branch): a hub/listing page — the bare
    #     apex, a URL-parent of a peer, or a generic-hub slug (/promotions, /category/aktsii,
    #     /about, …) — surfaces a promo already covered by a more specific deep offer on the same
    #     host. Its generic wording defeats 3c's text gate, so collapse it onto an existing
    #     same-host non-shadow non-expired offer (deep pages preferred), bump last_seen, and never
    #     insert. SUBSET (not intersection): the incoming hub's magnitudes must all be covered by
    #     the peer, so a hub that introduces a NEW magnitude the peer lacks is NOT collapsed and
    #     the genuinely new promo still reaches moderation.
    if crawler and not blocked and canon_article and data.discount_type is not None:
        host = (_source_host(getattr(data, "site_url", None))
                or _source_host(getattr(data, "article_url", None)))
        new_mags = discount_magnitudes(getattr(data, "discounts", None),
                                       data.discount_type, data.discount_value)
        if host and new_mags:
            cands = (db.query(Offer)
                     .options(selectinload(Offer.discounts))
                     .filter(Offer.created_by == CreatedBy.crawler,
                             Offer.status != OfferStatus.expired,
                             Offer.supersedes_offer_id.is_(None))
                     .all())

            def _rank(c):
                ca = c.article_url_canonical or ""
                return (0 if "/" in ca else 1, c.id)   # deep peers first, then lowest id

            for c in sorted(cands, key=_rank):
                peer_canon = c.article_url_canonical or ""
                if peer_canon == canon_article:
                    continue                            # same page → branches 1/3b own it
                c_host = _source_host(c.site_url) or _source_host(c.article_url)
                if c_host != host:
                    continue
                if not is_hub_page(canon_article, peer_canon):
                    continue                            # only a hub/listing page collapses here
                c_mags = discount_magnitudes(c.discounts, c.discount_type, c.discount_value)
                if new_mags <= c_mags:                  # subset: peer covers all incoming mags
                    c.last_seen_at = datetime.utcnow()
                    db.commit()
                    db.refresh(c)
                    return c

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
        logo_url=data.logo_url,
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
    # published_only is the public path: also hide offers whose valid_until has passed
    # (soft-expiry). Preview (published_only=False) still renders them for moderation.
    expired = published_only and obj is not None and obj.valid_until is not None \
        and obj.valid_until < date.today()
    if obj is None or expired or (published_only and obj.status != OfferStatus.published):
        raise not_found(f"Offer {offer_id} not found")
    return obj


def list_offers(db: Session, *, status: OfferStatus | None = None,
                types: list[OfferType] | None = None,
                target_category_ids: list[int] | None = None,
                offer_category_ids: list[int] | None = None,
                locations: list[str] | None = None, search: str | None = None,
                hide_expired: bool = False,
                page: int = 1, size: int = 20):
    q = db.query(Offer)
    if status is not None:
        q = q.filter(Offer.status == status)
    if hide_expired:
        # soft-expiry: drop offers whose "діє до" date has passed (valid through it,
        # inclusive). NULL valid_until = no end date, always shown.
        q = q.filter((Offer.valid_until.is_(None)) | (Offer.valid_until >= date.today()))
    if types:
        q = q.filter(Offer.type.in_(types))
    if locations:
        q = q.filter(Offer.locations.any(OfferLocation.name.in_(locations)))
    if search:
        like = f"%{search}%"
        q = q.filter((Offer.title.ilike(like)) | (Offer.description.ilike(like)) | (Offer.provider.ilike(like)))
    if target_category_ids:
        q = q.filter(Offer.target_categories.any(TargetCategory.id.in_(target_category_ids)))
    if offer_category_ids:
        q = q.filter(Offer.offer_categories.any(OfferCategory.id.in_(offer_category_ids)))
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
    if obj.discount_type in VALUE_DISCOUNT_TYPES:
        if obj.discount_value is None:
            raise validation_error("discount_value required for percent/fixed/special_price discounts")
    else:
        if obj.discount_value is not None:
            raise validation_error("discount_value must be empty unless discount_type is percent/fixed/special_price")
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


_CRAWLER_CREATED_BY = (CreatedBy.crawler, CreatedBy.crawler_suggestion)


def judge_reject(db: Session, offer_id: int, reason: str) -> Offer:
    """Суддя (LLM relevance judge) відхиляє непрожований crawler-офер: status=rejected,
    reviewed_by=None (не адмін), rejection_reason=reason. Guard: чіпає ЛИШЕ pending_review
    офери, створені краулером (crawler / crawler_suggestion) — адмінські, опубліковані чи
    вже прожовані офери суддя не чіпає (raise замість тихого no-op, щоб виклик не думав,
    що спрацювало)."""
    obj = get_offer(db, offer_id)
    if obj.status != OfferStatus.pending_review or obj.created_by not in _CRAWLER_CREATED_BY:
        raise conflict(
            f"judge_reject: offer {offer_id} is not an unjudged crawler offer "
            f"(status={obj.status}, created_by={obj.created_by})"
        )
    obj.status = OfferStatus.rejected
    obj.reviewed_by = None
    obj.rejection_reason = reason
    db.commit()
    db.refresh(obj)
    return obj


def list_pending_unjudged_for_crawler(db: Session, limit: int) -> list[Offer]:
    """pending_review офери від краулера (crawler / crawler_suggestion), найстаріші перші,
    обмежені limit — черга для судді на повторний прогон (re-queue sweep)."""
    return (db.query(Offer)
            .filter(Offer.status == OfferStatus.pending_review,
                    Offer.created_by.in_(_CRAWLER_CREATED_BY))
            .order_by(Offer.created_at.asc(), Offer.id.asc())
            .limit(limit).all())


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
    # public facet: don't advertise a city served only by a soft-expired offer
    rows = (db.query(OfferLocation.name)
            .join(Offer, Offer.id == OfferLocation.offer_id)
            .filter(Offer.status == status)
            .filter((Offer.valid_until.is_(None)) | (Offer.valid_until >= date.today()))
            .distinct().order_by(OfferLocation.name).all())
    return [r[0] for r in rows]
