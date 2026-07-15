# UBD Discounts — Cross-Source Offer Dedup Design — Track C

**Date:** 2026-07-15
**Scope:** Backend — cross-source offer deduplication
**Status:** Approved design, ready for implementation planning
**Branch:** `feat/offer-dedup` (cut from `main`)

## Context

With two discovery providers (DuckDuckGo + SearXNG) and multiple crawl sources,
the same discount can be found more than once — on different sites, from different
providers, across passes. Today the backend only dedups **within a single source**
via `unique (source_id, content_hash)`, and `content_hash = hash(title | provider |
body)` includes `provider` (= the source name), so the same offer from two
different sources produces two rows.

Track C adds **cross-source** dedup keyed on the *substance of the discount*
(title + discount), independent of which source/provider found it, so a moderator
sees one offer instead of duplicates.

This is the first of the dedup work; segmentation (splitting several discounts on
one page into separate offers) is a later sub-track (C2), and fuzzy/semantic dedup
is out of scope.

## Goals

- Add a `dedup_key` = `sha256(normalised_title | discount_type | discount_value)` —
  **no `provider`/source** — computed by the backend for every offer.
- On the **crawler** create path (`created_by=crawler`), if an offer with the same
  `dedup_key` already exists (any source, any status), return it instead of
  creating a duplicate.
- Check against **all statuses** (`pending_review` + `published`) so the crawler
  never re-adds an already-approved discount.
- Manual (admin) offers still get a `dedup_key` but are **not** blocked — the admin
  stays in control.
- Keep the existing per-source `(source_id, content_hash)` dedup intact.

## Non-Goals

- **Segmentation** (multiple discounts on one page → separate offers) — Track C2.
- **Fuzzy / semantic** dedup (same meaning, different wording that normalises
  differently) — the key handles casing/whitespace/punctuation only.
- Changing the crawler — `dedup_key` is computed server-side; the crawler is
  untouched.
- Deduping/merging offers already in the DB retroactively (only new inserts).

## Architecture

### Dedup key (`backend/app/core/dedup.py`, new)

```python
def offer_dedup_key(title, discount_type, discount_value) -> str
```
- Normalise `title`: lowercase, collapse whitespace, strip punctuation.
- Join normalised title with `discount_type` (enum value or "") and
  `discount_value` (decimal as plain string or "") by `"|"`, `sha256` it.
- Deterministic and provider-independent.

### Model + migration

- `Offer` gains `dedup_key: str | None` (String 64, nullable, **indexed** for the
  existence lookup). Alembic migration adds the column + index.

### CRUD (`backend/app/crud/offer.py`)

- `create_offer(...)` computes `dedup_key` from `data.title`,
  `data.discount_type`, `data.discount_value` and sets it on the row.
- **Before** inserting, when `created_by == CreatedBy.crawler`: query for any
  existing offer with the same `dedup_key`; if found, return it (no insert).
- The existing `(source_id, content_hash)` short-circuit stays as a second guard.
- Admin path (`created_by == CreatedBy.admin`) computes and stores `dedup_key` but
  does not run the blocking lookup.

### Schema

- `OfferOut` optionally exposes `dedup_key` (useful for debugging/admin); not
  required by the frontend. (Decide at planning: include or omit — leaning omit to
  keep the API surface unchanged.)

## Data flow

```
crawler offer → internal create_offer (created_by=crawler)
   → backend computes dedup_key(title, discount_type, discount_value)
   → if an offer with that dedup_key exists (any source/status) → return it
   → else insert with dedup_key
admin offer → create_offer (created_by=admin) → compute+store dedup_key, always insert
```

## Error handling & edge cases

- `discount_type`/`discount_value` null (e.g. event/free) → included as "" in the
  key; two free offers with the same normalised title dedup together.
- Empty/whitespace-only title → normalises to ""; still hashed (paired with the
  discount), so identical empty-title+same-discount collapse — acceptable.
- Race between two crawler inserts of the same key → the second finds the first (or
  falls back to the `content_hash` guard); worst case a rare duplicate, never a crash.
- Existing rows have `dedup_key = NULL` (migration doesn't backfill) — only new
  inserts are deduped, per non-goals.

## Testing & verification

- `offer_dedup_key`: title variants ("Знижка 20%!", " знижка  20% ") + same
  discount → identical key; different `%`/title → different key.
- CRUD: crawler creates offer with source 1, then the same discount with source 2
  (different provider) → one row, second returns the first; different discount →
  two rows; admin duplicate → not blocked (two rows).
- Cross-status: crawler offer duplicating a `published` one → returns the published,
  no new `pending_review` row.
- End-to-end (Docker): a second fixture source repeating the same discount → the
  crawler pass yields a single offer.

## Open decisions (defaulted, override at planning time)

- `dedup_key` String(64), indexed, nullable; not backfilled.
- Blocking only on `created_by=crawler`; admin computes but is unblocked.
- `OfferOut` does not expose `dedup_key` (keep API surface unchanged).
