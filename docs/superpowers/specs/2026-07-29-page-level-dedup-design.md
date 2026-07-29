# Page-level offer identity + multi-discount cards

**Date:** 2026-07-29
**Track:** #6 (P0 backlog) — page-level dedup
**Scope:** crawler + backend (migration) + public + admin

## Problem

A single promo page of a source is split by the heuristic extractor into **many separate
"offers"** — one per text block. Live example: `rezervist.com.ua/promotions-and-discounts`
(source_id=3) yields **6 offers from one page**: published #29 (general 10%) plus pending
#153 (МВС 10%), #154 (курсанти 15%), #155 (ЗСУ 15%), #158 (Black Friday 50%), #163 (FAQ 15%).
All share the same `article_url`, differ in `content_hash`.

The moderator publishes one (general) page offer; the rest of the page's fragments keep
appearing in the queue → "the same site floods moderation."

### Why current dedup misses

- `WebsiteFetcher.fetch` (`crawler/crawler/fetchers/website.py`) emits **one `RawItem` per
  block** (`article`/`li`/`p`), all with the same page `url` (= `article_url`), different `text`.
- `runner._process_item` and `harvest._process_page` submit **each block as a separate offer**.
- Backend `create_offer` branch 1 dedups on `(source_id, content_hash)` → different hash =
  new row. These offers have `target_url=NULL → target_url_canonical=NULL`, so branches 2/3/4
  (canonical) are skipped. `article_url` (stable, identical across a page's fragments) is
  **not used** for dedup today.

## Goal

- **One source page = one live offer**, carrying a **list of discounts** (МВС 10%, курсанти
  15%, ЗСУ 15%…) rendered on the public card — not an offer-per-text-block.
- Page-content changes between crawl passes route to **shadow re-moderation** of the published
  page offer, instead of spawning a fresh unlinked pending row.

## Key design insight

Backend-only dedup on `article_url` is **unsafe**: sibling blocks within one crawl pass
(МВС 10% vs курсанти 15%) have different `content_hash`; the backend, finding the first row by
`article_url`, would treat each following block as a "change" → shadow-thrash every pass
(blocks alternate). Therefore the **crawler must collapse a page into one candidate before
submit**; the backend `article_url` identity is the **complement** that routes *cross-pass*
page changes to re-moderation (because `target_url` is NULL for page-scoped offers).

## Design

### 1. Data model (backend)

New child entity **`offer_discounts`** (peer of `offer_locations`/`offer_links`):

| column | type | notes |
|---|---|---|
| `id` | PK | |
| `offer_id` | FK→offers, `cascade all, delete-orphan` | |
| `label` | String(255), nullable | "Курсантам ВВНЗ", "МВС"… |
| `discount_type` | Enum(percent/fixed/free) | reuses `DiscountType` |
| `discount_value` | Numeric(10,2), nullable | null for free |
| `sort_order` | Integer | stable card order |

- Top-level `offers.discount_type`/`discount_value` are **kept** as the "primary/headline"
  discount = the best from the list (free > max percent > max fixed). Always populated
  (a single-discount offer = a 1-item list). The list is **additive**: `OfferBadge`,
  public sort/filter, `SupersedesOut` preview, admin, and API keep working unchanged.
- New `offers.article_url_canonical` String(1024) + index `ix_offers_article_url_canonical`
  (mysql_length 255), computed via the existing `canonicalize_target_url` (URL-agnostic).
  This is the page-identity key.

### 2. Backend `create_offer` — page identity

- **Same-source change detection (branches 2 & 3)** switches its match key from
  `target_url_canonical` to **`article_url_canonical`** (page-identity, source-scoped). This
  closes the gap: previously `target_url=NULL` → branch skipped → new pending; now a change to
  the page's discounts between passes → **shadow re-moderation** against the published parent
  offer for that same page.
- **Branch 1** (unchanged) stays on `(source_id, content_hash)` — fast "nothing changed → bump
  `last_seen_at`" path, incl. the existing shadow/revert logic.
- **Branch 4** (cross-source canonical merge, aggregator/cross-platform) stays on
  `target_url_canonical` — not page-scoped.
- The unique constraint `(source_id, content_hash)` is retained; `content_hash` is now
  page-level (see §4).
- `_apply_content` replaces the `offer_discounts` list (replace-all) alongside existing fields.

### 3. Crawler — collapse a page into one candidate

`HeuristicExtractor.extract` stays per-block (still needed for corpus recording / `is_offer`
gating). Add **`aggregate_page(block_candidates) -> OfferCandidate`**:

- `discounts` = one entry per passing block: `{label, discount_type, discount_value}`,
  de-duplicating identical `(type, value, label)`. **`label = _title_from(block.body)`,
  fallback → the block's matched target-category name** when the snippet is empty/too long.
- `target_category_ids`, `offer_category_matches`, `locations` = **union** across blocks.
- `title` = page-level (`site_tagline` as today); `site_url`/`article_url`/`image_url` = page
  values; `target_url` = first outbound link across the page; primary `discount_type`/
  `discount_value` = best of the list.
- Both call sites — `runner._process_item` (registered sources) and `harvest._process_page`
  (active harvest) — converge on a shared page helper: collect the page's passing block
  candidates → `aggregate_page` → **one** `submit_offer`. One `fetcher.fetch` = one page
  (the natural grouping boundary already exists).
- Active harvest attributes provider per block; the aggregate uses the page's attributed
  provider (first/majority — same for a first-party business page).

### 4. content_hash — page-level

`content_hash = content_hash(title, provider, sorted[(type, value, label) for each discount])`.
Stable across DOM re-ordering of blocks; changes when a discount is added/removed/edited →
re-moderation. A pure prose edit that leaves discounts unchanged does **not** trigger
re-moderation (accepted — discounts are the moderated substance). This is both the
change-detection key and the churn-guard.

### 5. Public + Admin

- **Backend `OfferOut`** gains `discounts: list[DiscountOut]` (`label`, `discount_type`,
  `discount_value`), ordered by `sort_order`.
- **OfferCard** (`public/src/components/OfferCard.vue`): keep the primary `OfferBadge`, and
  render the discount list below it — one "label — value" row per entry. Falls back to the
  single badge when the list is empty (legacy/single-discount offers).
- **OfferDetailView**: same list, full.
- **Admin OfferForm** (`admin/src/components/OfferForm.vue`): a discounts-rows editor
  (add/remove: label, type, value); `update_offer` syncs `offer_discounts`. `OffersListView`
  queue preview shows a discount count / summary.

### 6. Non-goals

- Catalog pages listing **different businesses** (not a single promo page). Blocklisted
  aggregators already take a separate path and create no offers; a registered source page is
  assumed to be one business. We do **not** collapse distinct businesses.
- Retroactive merge of legacy duplicate rows in the DB (as in the canonical-dedup track —
  application-level dedup; the live queue is cleaned manually).

## Testing & delivery

- TDD, subagent-driven with a checkpoint after **each** task (ask "continue?" — see project
  workflow), not an auto-run.
- Branch `feat/page-level-dedup` off `main` → merge back.
- Full live Docker run end-to-end (crawler hot-copy stopgap as agreed while pypi is
  unreachable for a canonical rebuild).
- Expected suites: backend (new `offer_discounts` + `article_url_canonical` + `create_offer`
  branch tests), crawler (`aggregate_page` + both call-site page helpers), public
  (OfferCard/OfferDetail multi-discount render), admin (OfferForm discounts editor).
