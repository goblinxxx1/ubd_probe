from datetime import datetime

from sqlalchemy.orm import Session

from app.core.urlnorm import normalize_source_ref
from app.crud import source as source_crud
from app.models import Offer
from app.models.enums import CreatedBy, SourceType


def maybe_promote_on_publish(db: Session, offer: Offer) -> None:
    """On publish, promote a crawler offer's article page to an active passive-crawl
    source and link the offer to it, so the passive crawler re-confirms it (freshness).
    No-op unless the offer is a crawler offer, not already sourced, with a valid http(s)
    article_url (falls back to site_url). Idempotent by (type, url_or_handle)."""
    if offer.created_by != CreatedBy.crawler or offer.source_id is not None:
        return
    ref = normalize_source_ref(offer.article_url or offer.site_url or "")
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
