from datetime import datetime
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.core.urlnorm import normalize_source_ref
from app.crud import source as source_crud
from app.models import Offer
from app.models.enums import CreatedBy, SourceType


def _origin(url: str | None) -> str | None:
    """scheme://host of an http(s) URL — drops path/query so a promoted source is the
    SITE, not the single offer page. The page-targeted walker then discovers NEW offers
    across the business (bounded by domain_page_cap), instead of re-checking one page."""
    p = urlsplit(url or "")
    if p.scheme in ("http", "https") and p.netloc:
        return f"{p.scheme}://{p.netloc}"
    return None


def maybe_promote_on_publish(db: Session, offer: Offer) -> None:
    """On publish, promote a crawler offer's SITE ORIGIN to an active passive-crawl
    source and link the offer to it, so the walker re-crawls the business for offers.
    No-op unless the offer is a crawler offer, not already sourced, with a valid http(s)
    site_url/article_url. Idempotent by host (one active website source per host)."""
    if offer.created_by != CreatedBy.crawler or offer.source_id is not None:
        return
    ref = normalize_source_ref(_origin(offer.site_url) or _origin(offer.article_url) or "")
    if ref is None:
        return
    source = source_crud.get_or_create_source_by_ref(
        db, SourceType.website, ref, offer.provider, CreatedBy.crawler)
    if offer.content_hash is not None:
        clash = db.query(Offer).filter(Offer.source_id == source.id,
                                       Offer.content_hash == offer.content_hash,
                                       Offer.id != offer.id).first()
        if clash is not None:
            # Existing row already represents this offer under the source; do not
            # violate UniqueConstraint(source_id, content_hash). Leave it unlinked.
            offer.last_seen_at = datetime.utcnow()
            db.commit()
            return
    offer.source_id = source.id
    offer.last_seen_at = datetime.utcnow()
    db.commit()
    db.refresh(offer)
