"""Moderation-queue confidence assist (backlog #10). Advisory only — never gates publish.

Per pending offer, derive a coarse tier + signal chips from (a) the source host's
published/rejected reputation (the decisive signal proven in track #34) and (b) offer
completeness (has discount / location / category)."""

from app.crud.offer import _source_host, host_reputation
from app.models.enums import OfferStatus  # noqa: F401 — kept for parity/imports clarity
from app.schemas.offer import ConfidenceOut


def _primary_host(offer) -> str:
    for v in (offer.site_url, offer.article_url, offer.provider):
        h = _source_host(v)   # bare host only if it has a dot (free-text provider safe)
        if h:
            return h
    return ""


def score_offer(db, offer, memo: dict) -> ConfidenceOut:
    host = _primary_host(offer)
    pub, rej = host_reputation(db, host, memo) if host else (0, 0)
    has_discount = offer.discount_type is not None or bool(getattr(offer, "discounts", []))
    has_location = bool(getattr(offer, "locations", []))
    has_category = bool(getattr(offer, "offer_categories", []))

    signals: list[str] = []
    if pub >= 1 and rej == 0:
        signals.append("proven_host")
    elif rej >= 1 and pub == 0:
        signals.append("noisy_host")
    elif pub == 0 and rej == 0:
        signals.append("new_host")
    if not has_discount:
        signals.append("no_discount")
    if not has_location:
        signals.append("no_location")
    if not has_category:
        signals.append("no_category")

    if pub >= 1 and rej == 0 and has_discount:
        tier = "high"
    elif (rej >= 1 and pub == 0) or not has_discount:
        tier = "low"
    else:
        tier = "medium"

    return ConfidenceOut(tier=tier, host=host, host_published=pub,
                         host_rejected=rej, signals=signals)


def enrich_pending(db, offers) -> None:
    """Attach a transient `.confidence` (ConfidenceOut) to each offer. Memoizes host
    reputation across the batch so a repeated host is queried once."""
    memo: dict = {}
    for o in offers:
        o.confidence = score_offer(db, o, memo)
