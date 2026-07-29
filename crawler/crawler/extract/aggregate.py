from dataclasses import replace

from crawler.dedup import page_content_hash
from crawler.models import OfferCandidate

_RANK = {"free": 3, "percent": 2, "fixed": 1}


def _best(discounts: list[dict]) -> tuple[str | None, str | None]:
    """Primary/headline discount: free > highest percent > highest fixed."""
    best = None
    for d in discounts:
        dt = d.get("discount_type")
        if dt is None:
            continue
        val = float(d.get("discount_value") or 0)
        key = (_RANK.get(dt, 0), val)
        if best is None or key > best[0]:
            best = (key, dt, d.get("discount_value"))
    return (best[1], best[2]) if best else (None, None)


def aggregate_page(cands: list[OfferCandidate]) -> OfferCandidate | None:
    if not cands:
        return None
    head = cands[0]
    discounts: list[dict] = []
    seen = set()
    tcats: list[int] = []
    ocats: list[tuple[str, str]] = []
    locations: list[str] = []
    target_url = None
    for c in cands:
        for d in (c.discounts or []):
            k = (d.get("discount_type"), str(d.get("discount_value")), d.get("label"))
            if k not in seen:
                seen.add(k)
                discounts.append(d)
        for t in c.target_category_ids:
            if t not in tcats:
                tcats.append(t)
        for m in c.offer_category_matches:
            if m not in ocats:
                ocats.append(m)
        for loc in c.locations:
            if loc not in locations:
                locations.append(loc)
        if target_url is None and c.target_url:
            target_url = c.target_url
    dtype, dval = _best(discounts)
    return replace(
        head,
        discounts=discounts,
        target_category_ids=tcats,
        offer_category_matches=ocats,
        locations=locations,
        target_url=target_url,
        discount_type=dtype,
        discount_value=dval,
        offer_category_ids=[],
        content_hash=page_content_hash(head.title, head.provider, head.article_url, discounts),
    )
