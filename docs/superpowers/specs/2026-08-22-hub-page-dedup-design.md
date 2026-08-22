# Hub-page dedup: stop re-flooding moderation with already-published promos

**Date:** 2026-08-22
**Status:** Design approved
**Builds on:** [[ubd-backend-promo-offer-dedup]] (3c host+magnitude-subset+text-Jaccard),
[[ubd-crawler-pagelevel-dedup-done]] (1 page = 1 offer with a discount list),
[[ubd-approved-source-passive-remoderation]] (passive shadow re-moderation — kept intact),
[[ubd-crawler-active-passive-split]] (active skips known hosts; passive re-confirms them).

## Problem

Offers for businesses **already published on the public site** keep re-appearing in the
moderation queue every passive cycle («знову насипає»). Confirmed on live data — 4 sources
right now each have 1 published + 1 fresh non-shadow pending duplicate:

| source | published (on public site) | new pending duplicate | discount |
|---|---|---|---|
| mebelmarket.ua | `/promotion/znyzhka-viyskovm` | `/promotions` | 8% ↔ 8% |
| whiteclinic.ua | `/promotions/znyzhka-10-…` | `/promotions` | 10% ↔ 10% |
| m2fit.com.ua | `/veteran` | `/about` | 15% ↔ 15% |
| tovpollar.org | `/znyzhky-…-zsu` | `/category/aktsii` | 30% ↔ 30% |

### Root cause (evidenced)

The **active** pass correctly skips these hosts — they are active website sources in
`known_hosts` ([runner.py:167](../../../crawler/crawler/runner.py#L167),
[harvest.py:102](../../../crawler/crawler/discovery/harvest.py#L102)). Host-skip is **not**
broken, and there are **zero** published discovered offers (`source_id IS NULL`), so this is
not a missing-source problem.

The leak is the **passive** deep-walk ([runner.py:324](../../../crawler/crawler/runner.py#L324)):
it re-crawls an already-published source across many pages (walker cap ~15: apex + `/promotions`
listing + deep offer pages). In one pass the deep offer page collapses onto the published row
(branch 1, same `content_hash`), but the **hub/listing page** carries the *same promo* (same
discount magnitude) worded differently, on a different URL, and slips past every dedup branch in
`create_offer` ([offer.py](../../../backend/app/crud/offer.py)):

- **branch 2/3** (shadow / update-in-place) require the same `article_url_canonical`.
- **branch 3c** ([dedup.py:48](../../../backend/app/crud/dedup.py#L48)) requires magnitude-subset
  **and** text-Jaccard ≥ 0.6 — the hub page's text differs too much → not a match.
- **branch 3d** (apex dedup) fires only for a bare apex (`"/" not in canon_article`) — a hub
  path like `/promotions` is excluded.

So it falls through to a fresh `INSERT` — a duplicate of a promo already on the public site.
Timing confirmed recurrence: all 4 duplicates were created in a single passive cycle
(2026-08-21 18:10–18:22), and offer 213's `last_seen_at` was bumped 13s after its `/promotions`
duplicate 379 was inserted — same walk, both pages.

## Goal

No **new** pending offer is created for a promo already represented by another offer on the same
host, when the incoming page is a **hub/listing** page. Keep everything else working.

**Non-goals / hard constraints (from the user):**
- **Do not break selection of new candidates.** New hosts, genuinely new distinct offers, and
  new discount magnitudes surfaced on a hub page MUST still reach moderation.
- **Do not create moderation duplicates of already-published offers with any crawler.** (The
  crawler may still *fetch* hub pages — needed to find new offers listed there — but a matching
  promo is collapsed, not re-inserted. Fetch-skipping hub pages was rejected: it would hide new
  offers listed on those pages.)
- Passive **change-detection** (shadow on a discount change of a published page) stays intact —
  it keys on the exact published page and is untouched by this change.
- No Russian-language forms in the hub-slug list ([[language-preference]]).

## Design

Backend-only change: **generalize the existing apex-dedup branch 3d into a hub-page dedup**.
Backend is the single source of truth (all published offers, magnitudes, existing dedup
branches), and the fix reuses 3d's candidate scan, deep-peer ranking, and shadow-exclusion.
No crawler change.

### Collapse rule

An incoming crawler offer collapses onto an existing same-host peer (non-shadow, non-expired;
deep pages preferred) — bump `last_seen_at`, return the peer, do **not** insert — when **both**:

1. the incoming page **is a hub/listing page** (`is_hub_page`, see below), **and**
2. the incoming offer's discount magnitudes are a **subset** of the peer's
   (`incoming_mags ⊆ peer_mags`).

The subset direction (not the current intersection) is what protects new-candidate selection:
if the hub page introduces a **new** magnitude the published offer lacks (e.g. published 8%, but
`/promotions` also shows 15%), the subset fails → the offer is **not** collapsed → the new promo
reaches moderation. A new magnitude is never silently dropped.

### `is_hub_page(incoming_canon, peer_canon)` — pure, DB-free, in `dedup.py`

True when **any** of:
- **apex** — `incoming_canon` has no path (`"/" not in incoming_canon`). *(structural; current
  3d behavior)*
- **url-parent** — `incoming_canon` is a strict path-prefix ancestor of `peer_canon`
  (`/promotions` ⊃ `/promotions/znyzhka-10-…`). *(structural; catches whiteclinic)*
- **generic-hub slug** — the terminal path segment of `incoming_canon` is in a curated set:
  `promotions, promotion, aktsiyi, aktsii, akciyi, akcia, znizhki, znyzhky, discounts, sale,
  sales, offers, propozicii, propozycii, category, categories, catalog, katalog, about,
  about-us, pro-nas, pronas, main, home, index`. *(heuristic; catches mebelmarket
  `/promotions`, tovpollar `/category/aktsii`, m2fit `/about`)*

UA-oriented + neutral-English only; no Russian-specific forms (e.g. no `skidki`).

### Wiring in `create_offer`

Replace branch 3d's entry guard `canon_article and "/" not in canon_article` with a hub check,
and its magnitude test `new_mags & c_mags` with the subset test `new_mags <= c_mags`. Everything
else in the branch (candidate query, `_rank` deep-first ordering, shadow/expired exclusion,
same-page skip) is unchanged. Branch 3c is left as-is (it already covers same-text same-magnitude
collapse on any page).

## Blast radius & safety

- Touches only crawler offers on a host that already has another offer. New hosts, distinct
  deep offer pages, and shadow change-detection are untouched.
- All 5 existing 3d tests stay green (verified by reading them): apex→deep collapse; apex-no-peer
  kept; apex-different-magnitude kept; **two deep pages `/one` & `/two` stay separate** (neither
  is a hub — the main over-collapse guard already exists); shadow never a target. Existing tests
  are single-magnitude, so intersection→subset is behaviorally identical for them and strictly
  safer for multi-magnitude hubs.
- Only new fuzzy input is the generic-hub slug list; apex and url-parent arms stay structural.

## Testing

Unit tests (pure `is_hub_page` + branch behavior), mirroring `test_offer_apex_dedup.py`:

- **The 4 real cases** collapse: `/promotions` vs `/promotion/znyzhka-viyskovm` (slug),
  `/promotions` vs `/promotions/znyzhka-10-…` (url-parent), `/about` vs `/veteran` (slug),
  `/category/aktsii` vs `/znyzhky-…` (slug) — all same magnitude → collapsed onto the deep peer.
- **New-candidate protection:** hub page with a magnitude the peer lacks
  (`{8,15} ⊄ {8}`) → **kept** (not collapsed).
- **Distinct offers protected:** two deep offer-slug pages, same % → stay separate (regression
  of `test_deep_offer_is_unaffected`).
- **Hub-vs-hub / no peer:** hub page with no same-host peer → kept.
- **Shadow exclusion:** hub page whose only same-magnitude peer is a shadow → kept.
- `is_hub_page` unit cases: apex True; url-parent True; each generic slug True; a descriptive
  offer slug (`znyzhka-10-dlja-uchasnykiv`) False.

## Rollout

Fix is create-time only; it does not retro-collapse the 4 duplicates already in the queue. Those
are cleared by the moderator (reject/publish) as usual; after the fix they will not be
re-created on the next passive cycle (a rejected/published peer with the same magnitude now
absorbs the hub re-crawl).
