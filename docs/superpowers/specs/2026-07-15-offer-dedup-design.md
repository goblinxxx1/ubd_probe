# UBD Discounts — Offer Dedup & Merge by Target Link Design — Track C

**Date:** 2026-07-15
**Scope:** Crawler + backend + public — dedup/merge offers by their target link
**Status:** Approved design, ready for implementation planning
**Branch:** `feat/offer-dedup` (cut from `main`)

## Context

With two discovery providers and multiple sources, the same discount is found more
than once — often on different aggregator sites (`army.gov.ua`, `mva.gov.ua`, …).
Today the backend only dedups **within one source** (`unique (source_id,
content_hash)`), and `content_hash` includes `provider` (= source name), so the
same discount from two sources becomes two rows.

Naive dedup on the discount text/title is unsafe: two *different* businesses can
advertise an identically-worded discount and would wrongly collapse. The reliable
signal for "same offer" is the **target link** — where the discount actually leads
(the business/offer page). Different businesses have different sites, so:

- same `target_url` from two aggregators → the **same** offer → merge (keep both
  source links so the public site can link to both);
- different `target_url` → different businesses → separate offers.

This is Track C. Segmentation (several discounts on one page → separate offers) is
a later sub-track (C2); fuzzy/semantic dedup is out of scope.

## Goals

- Crawler extracts a **`target_url`** for each offer — the offer's outbound target
  link (first external link in the block; social/utility links filtered).
- Backend dedups/merges crawler offers by normalised `target_url`: same
  `target_url` → one offer, additional discovery **sources** recorded, not a new row.
- Preserve every **source where the offer was found** (`provider`, `site_url`,
  `article_url`) in a new `offer_links` table, so the public site shows multiple
  links for a merged offer.
- Offers without a `target_url` are never auto-merged (stay separate — no false
  collapses).

## Non-Goals

- **Segmentation** (multiple discounts on one page → separate offers) — Track C2.
- **Fuzzy/semantic** dedup — only exact normalised `target_url` matching.
- **Manual merge UI / retroactive merge** of existing rows — only new crawler
  inserts merge; admin offers are not auto-merged.
- Reliable business identification beyond the target link (heuristic, best-effort).

## Architecture

### Crawler: extract `target_url`

- `WebsiteFetcher` already collects `RawItem.links` (all `href`s in the block).
  Add a helper that picks the **target link**: the first link whose host differs
  from the source host, excluding social/utility hosts
  (facebook/instagram/t.me/twitter/youtube/…) and non-http schemes; normalise it
  with the existing `_normalize_url`. `None` if no clean external link.
- Carry `target_url` on `RawItem` → `OfferCandidate` → `offer_payload` →
  backend internal create schema. Heuristic extractor copies it through.

### Backend: model + migration

- `Offer` gains `target_url: str | None` (String 1024, nullable, **indexed**).
- New table **`offer_links`**: `id`, `offer_id` (FK→offers, cascade),
  `provider` (String), `site_url` (String|None), `article_url` (String|None),
  `created_at`. One row per source where the offer was found.
- Alembic migration adds the column+index and the table. (The single-valued
  `site_url`/`article_url` columns on `offers` stay for admin-entered offers and
  backward compatibility; the crawler now also writes an `offer_links` row.)

### Backend: dedup/merge on create (crawler path)

- `create_offer(..., created_by=crawler)` with a non-null `target_url`:
  - look up an existing offer with the same normalised `target_url`;
  - if found → **merge**: append an `offer_links` row (this pass's `provider`,
    `site_url`, `article_url`) to it (deduping identical link rows) and return it —
    no new offer;
  - else → insert the offer (with `target_url`) plus its first `offer_links` row.
- `target_url` null, or admin path → no merge lookup; insert as today (admin offers
  may still get one `offer_links` row from their `site_url`/`article_url`).
- The existing `(source_id, content_hash)` guard stays as a secondary check.

### Schema

- `OfferOut` gains `links: list[OfferLinkOut]` (`provider`, `site_url`,
  `article_url`) so the public API exposes all sources of a merged offer.

### Public: multiple links

- `OfferCard` / `OfferDetailView` iterate `offer.links` and render a "Сайт" /
  "Сторінка новини" pair per source (dedupe empty). A merged offer shows 2+ links.
  Falls back to the offer's own `site_url`/`article_url` if `links` is empty.

## Data flow

```
website block → links[] → pick target_url (first external, non-social)
   → OfferCandidate(target_url, site_url, article_url, provider)
   → internal create_offer (crawler):
        target_url matches existing? → append offer_links row (merge), return it
        else → insert offer + first offer_links row
   → public offer shows all offer_links as separate links
```

## Error handling & edge cases

- No external link in block → `target_url=None` → offer stays separate.
- Target link is itself the source domain / a social host → filtered → `None`.
- Duplicate `offer_links` (same provider+site+article merged twice) → deduped on
  insert (idempotent pass re-runs don't stack rows).
- Admin offer with a manual `target_url` colliding with a crawler offer → not
  merged (merge only on crawler path); acceptable.
- Existing rows have `target_url=NULL`, no `offer_links` — not backfilled; only new
  inserts participate.

## Testing & verification

- **crawler:** `target_url` = first external non-social link; `None` when only
  same-host/social links; normalisation applied.
- **backend:** two crawler offers with the same `target_url` (different providers)
  → one offer with two `offer_links`; different `target_url` → two offers; no
  `target_url` → two offers; duplicate merge is idempotent (no stacked links).
- **public:** an offer with two `offer_links` renders two link pairs; single/none
  falls back cleanly.
- **end-to-end (Docker):** two fixture pages linking to the same target URL → one
  merged offer with two source links, visible in public.

## Open decisions (defaulted, override at planning time)

- `offer_links` as a separate table (vs JSON column) — chosen for clean relations.
- Target heuristic: first external (host ≠ source host), excluding
  facebook/instagram/t.me/twitter/x/youtube/telegram; else `None`.
- `target_url` String(1024), indexed, nullable, not backfilled.
- Merge only on `created_by=crawler`; admin offers unaffected.
