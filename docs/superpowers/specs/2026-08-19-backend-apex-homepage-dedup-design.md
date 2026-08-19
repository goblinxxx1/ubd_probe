# Backend: apex-homepage promo dedup (Track 3)

**Date:** 2026-08-19
**Status:** Design approved (approach chosen: apex-homepage dedup)
**Program:** crawler precision fixes (Track 3). See [[ubd-crawler-precision-program]].

## Problem

The moderation queue holds offers that duplicate an already-published offer of the
**same promo on the same host**, surfaced from the site's **apex homepage**.

**Evidence (queue 2026-08-19), after ruling out false leads by execution:**

| Pending dup | host | discount | `article_url_canonical` | duplicates published |
|---|---|---|---|---|
| #332 (src 47) | compass-group.com.ua | 10% | `compass-group.com.ua` (apex) | #304 (`…/pytannya-ta-vidpovidi`, 10%) |
| #333 (src 48) | smartlab.ua | 30% (+20%) | `smartlab.ua` (apex) | #302 (`…/discont/…/about`, 30%) |

Ruled out (not bugs): **#334** carries `supersedes_offer_id=302` — a legitimate
re-moderation **shadow**, not a duplicate; left untouched.

### Why existing dedup misses these (investigated in code + data)

- Branches 1/2/3 key on `(source_id, article_url_canonical)` — the apex URL
  (`smartlab.ua`) differs from the deep offer-page URL (`…/about`), so no match.
- Branch 3b is gated `source_id is None` (discovered only); these are source crawls.
- Branch 3c (host + magnitude-subset + **text** Jaccard ≥ 0.6) is cross-source and the
  host + magnitude match, **but the apex homepage's generic marketing text**
  ("СМАРТЛАБ — мережа лабораторій, 1500+ аналізів" / "Квитки на автобус, 250
  перевізників") is dissimilar to the offer-page text, so Jaccard < 0.6 and 3c
  correctly (conservatively) keeps them separate.

The pattern: **an apex-homepage promo banner** shares a host and a discount magnitude
with a real deep offer page, but its generic text defeats the (rightly conservative)
text gate.

## Goal

Collapse an incoming apex-homepage crawler offer onto an existing same-host,
non-shadow, non-expired offer that shares a discount magnitude — without a text gate —
so the duplicate never enters the queue. Do not touch legitimate shadows, deep-page
offers, or offers whose only same-host peer has a different magnitude.

Non-goal: the reverse direction (a deep offer created after an apex one) — rare, and
handled acceptably by existing branches / conservative fall-through. Non-goal: merging
two genuinely distinct same-% offers that each have their own deep page.

## Design

### New helper — none required

Magnitude overlap is a plain frozenset intersection on the existing
`discount_magnitudes(...)` output (`a_mags & b_mags`), so no new function in `dedup.py`.

### New branch 3d in `create_offer` (`backend/app/crud/offer.py`)

Insert a branch **after 3c** (line ~267) and **before branch 4** (cross-source
canonical merge, line ~269):

```python
    # 3d) Apex-homepage dedup: a homepage/source crawl surfaces a promo banner on the
    #     bare apex host (canon_article has no path). Its generic homepage text defeats
    #     3c's text gate, yet it is the same promo as a deep offer page on the same host
    #     sharing a discount magnitude. Collapse the apex offer onto an existing same-host
    #     non-shadow non-expired offer (deep pages preferred), bump last_seen, and never
    #     insert the duplicate. One-directional (incoming apex only); requires a magnitude
    #     overlap, so distinct-magnitude same-host offers stay separate.
    if (crawler and not blocked and canon_article and "/" not in canon_article
            and data.discount_type is not None):
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
            # prefer a deep (path-bearing) peer over another apex row, then lowest id
            def _rank(c):
                ca = c.article_url_canonical or ""
                return (0 if "/" in ca else 1, c.id)
            for c in sorted(cands, key=_rank):
                if (c.article_url_canonical or "") == canon_article:
                    continue                      # same apex page → branches 1/3b own it
                c_host = _source_host(c.site_url) or _source_host(c.article_url)
                if c_host != host:
                    continue
                c_mags = discount_magnitudes(c.discounts, c.discount_type, c.discount_value)
                if new_mags & c_mags:
                    c.last_seen_at = datetime.utcnow()
                    db.commit()
                    db.refresh(c)
                    return c
```

- **Apex detection:** `canon_article` has no `/` — verified `canonicalize_target_url`
  maps `https://smartlab.ua`, `https://www.smartlab.ua/` → `smartlab.ua`, and deep
  pages keep their path.
- **Collapse target:** existing same-host crawler offer, `supersedes IS NULL`
  (skip shadows), `status != expired`, magnitude-overlapping; deep peers ranked first
  so the apex banner folds onto the real offer page, not another apex row.
- **Effect:** returns the existing row (bumps `last_seen_at`); the apex duplicate is
  never inserted. Mirrors 3b/3c's "return existing" contract.

### Ordering

3d runs only if 1/2/3/3b/3c did not already return. For the evidence rows this is the
case (text gate missed them). Placing 3d before branch 4 keeps the cross-source
`target_url_canonical` merge as the final catch-all.

## Blast radius

- One new branch in `create_offer`; no new file, no schema/migration, no crawler
  change, no config. Reuses `discount_magnitudes`, `_source_host`, `selectinload`.

## Risks

1. **Two genuinely distinct same-% offers on one host, one only on the homepage** →
   collapsed. Rare (a homepage banner almost always mirrors a deep offer). Accepted
   by design choice; conservative guards: magnitude overlap required, shadows/expired
   excluded, deep peers preferred.
2. **Apex offer created before its deep peer** → 3d (incoming apex) does not fire for
   the later deep offer; a dup could persist. Rare (deep pages are the primary crawl
   target); acceptable fall-through.

## Testing

`backend/tests/` (mirror `test_offer_discovered_dedup.py` / `test_offer_banner_dedup.py`):

- apex offer (`article_url = https://smartlab.ua`, 30%) with an existing published deep
  same-host offer (`…/about`, 30%) → `create_offer` returns the deep offer, inserts no
  new row, bumps its `last_seen_at`.
- apex offer with **no** same-host offer → inserted (kept).
- apex offer whose same-host peer has a **different** magnitude (10% vs 30%) → inserted
  (kept, no false collapse).
- apex offer collapses onto a **deep** peer even when an apex peer of the same magnitude
  also exists (ranking prefers deep).
- a **deep** offer (path-bearing article) is unaffected by 3d (normal path).
- a shadow peer (`supersedes_offer_id` set) is **not** a collapse target.

## Rollout

Rebuild backend container. Clean the two existing queue dups (#332, #333) by rejection
(the branch prevents new ones going forward; it is not retroactive).
