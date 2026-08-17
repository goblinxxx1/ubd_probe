"""One-off: collapse duplicate promo offers already sitting in the moderation queue.

Groups pending crawler offers by host and rejects same-promo duplicates (keeping the
oldest row per group), using the same host+magnitude+text rule as create_offer branch 3c.
Dry-run by default; pass --apply to write changes. Idempotent.

Run:  python -m app.dedup_queue          # dry-run
      python -m app.dedup_queue --apply  # reject duplicates
"""
import argparse

from app.core.config import settings
from app.core.db import SessionLocal
from app.crud.dedup import normalize_tokens, discount_magnitudes, is_duplicate_promo
from app.crud.offer import _source_host, _promo_text
from app.models import Offer
from app.models.enums import CreatedBy, OfferStatus


def find_duplicates(db, threshold):
    """Return [(dup_id, keep_id)] for pending crawler offers that duplicate an older kept
    offer on the same host. The oldest row of each promo group is kept."""
    pend = (db.query(Offer)
            .filter(Offer.created_by == CreatedBy.crawler,
                    Offer.status == OfferStatus.pending_review)
            .order_by(Offer.id).all())
    kept = []
    pairs = []
    for o in pend:
        host = _source_host(o.site_url) or _source_host(o.article_url)
        mags = discount_magnitudes(o.discounts, o.discount_type, o.discount_value)
        text = normalize_tokens(_promo_text(o))
        match = next((k for k in kept if k["host"] == host
                      and is_duplicate_promo(text, mags, k["text"], k["mags"], threshold)), None)
        if match is not None:
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
        for dup_id, keep_id in pairs:
            tag = "[REJECTED]" if args.apply else "[dry-run]"
            print(f"offer {dup_id} -> duplicate of {keep_id}  {tag}")
        if args.apply:
            for dup_id, _ in pairs:
                db.get(Offer, dup_id).status = OfferStatus.rejected
            db.commit()
        verb = "rejected" if args.apply else "found (dry-run)"
        print(f"{len(pairs)} duplicate(s) {verb}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
