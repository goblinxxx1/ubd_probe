"""One-off: collapse duplicate promo offers already sitting in the moderation queue.

Groups pending crawler offers by host and rejects same-promo duplicates (keeping the
oldest row per group), using the same host+magnitude+text rule as create_offer branch 3c.
Dry-run by default; pass --apply to write changes. Idempotent.

Run:  python -m app.dedup_queue          # dry-run
      python -m app.dedup_queue --apply  # reject duplicates
"""
import argparse

from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.db import SessionLocal
from app.crud.dedup import normalize_tokens, discount_magnitudes, is_duplicate_promo
from app.crud.offer import _source_host, _promo_text
from app.models import Offer
from app.models.enums import CreatedBy, OfferStatus


def find_duplicates(db, threshold):
    """Return [(dup_id, keep_id)] for pending crawler offers that duplicate an already-decided
    offer on the same host, mirroring create_offer branch 3c.

    Representatives ("kept") are seeded from ALL non-expired crawler offers -- published,
    pending, and rejected alike -- walked in id (creation) order. Published and rejected rows
    always become representatives (they're already decided; never a match target for removal,
    never rejected here). A pending offer that matches an earlier representative is recorded as
    a duplicate to be rejected; otherwise it becomes a representative itself, so the oldest
    pending row of a still-undecided group stands in for the group. Only pending offers are
    ever produced as dup_id -- published/rejected offers are never rejected by this script.
    """
    offers = (db.query(Offer)
              .filter(Offer.created_by == CreatedBy.crawler,
                      Offer.status != OfferStatus.expired)
              .options(selectinload(Offer.discounts))
              .order_by(Offer.id).all())
    kept = []
    pairs = []
    for o in offers:
        host = _source_host(o.site_url) or _source_host(o.article_url)
        mags = discount_magnitudes(o.discounts, o.discount_type, o.discount_value)
        text = normalize_tokens(_promo_text(o))
        if not host or not mags:
            continue
        match = next((k for k in kept if k["host"] == host
                      and is_duplicate_promo(text, mags, k["text"], k["mags"], threshold)), None)
        if match is not None and o.status == OfferStatus.pending_review:
            pairs.append((o.id, match["id"]))
        else:
            kept.append({"id": o.id, "host": host, "mags": mags, "text": text})
    return pairs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    args = ap.parse_args()
    db = SessionLocal()
    try:
        pairs = find_duplicates(db, settings.dedup_text_similarity_threshold)
        if args.apply:
            for dup_id, _ in pairs:
                db.get(Offer, dup_id).status = OfferStatus.rejected
            db.commit()
        # Print after the commit above, so an [REJECTED] tag only appears once the status
        # change has actually been written -- not merely intended.
        for dup_id, keep_id in pairs:
            tag = "[REJECTED]" if args.apply else "[dry-run]"
            print(f"offer {dup_id} -> duplicate of {keep_id}  {tag}")
        verb = "rejected" if args.apply else "found (dry-run)"
        print(f"{len(pairs)} duplicate(s) {verb}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
