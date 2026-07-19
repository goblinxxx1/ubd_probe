# Crawler: attribution precision + business location + card de-dup

**Date:** 2026-07-19
**Branch:** `feat/crawler-attribution-location`
**Status:** design approved, ready for plan

## Context

Follow-up to the active-search harvest redesign (variant A, merge `95b34dc`). The
end-to-end pipeline works (offers → moderation, dedup, suggestions 136 → 17), but the
first live run surfaced three defects to polish:

1. **Attribution false positives** — news / government / stock-photo / social-aggregator
   pages leak in as fake "providers" (`zakon.rada.gov.ua`, `biz.nv.ua`, `nszu.gov.ua`,
   `ua.depositphotos.com`, `vm.tiktok.com`, «24 канал», `061.ua`) alongside real ones
   (Your Burger, BOXY, NAF FLOWERS, ALLORO, MRIIA).
2. **No business location** — the crawler never fills `Offer.location`, though the backend
   model/schemas and the admin form already support it.
3. **Card text duplication** — the public card shows `card__dtext` (`offer.title`) and
   `card__desc` (`offer.description`) with identical text for crawler offers, because the
   extractor sets `title = text[:200]` and `body = text`.

The project constraint stands: **zero-cost, offline, no cloud LLM.**

## Scope

One branch, three coordinated changes. Backend + admin need **no** change for location
(both already carry `location` / the «Локація» form field). Admin unchanged entirely.

Out of scope (documented as follow-ups): news Telegram channels still attribute as
providers; IG/FB harvesting.

---

## 1. Attribution precision (crawler)

### New module `crawler/discovery/blocklist.py`

- `is_blocked_host(host: str | None) -> bool` — True when `host` matches a curated set of
  media / government / stock-photo / social-aggregator domains, by **exact match or
  subdomain suffix** (`biz.nv.ua` → matches `nv.ua`; `ua.depositphotos.com` → matches
  `depositphotos.com`), plus a TLD-level rule for `*.gov.ua`.
- Seed set (extensible), from observed leaks + common UA media:
  - media: `nv.ua`, `24tv.ua`, `061.ua`, `pravda.com.ua`, `unian.ua`, `tsn.ua`, `rbc.ua`,
    `censor.net`, `obozrevatel.com`, `segodnya.ua`
  - gov: any `*.gov.ua` (covers `rada.gov.ua`, `zakon.rada.gov.ua`, `nszu.gov.ua`)
  - stock: `depositphotos.com`, `shutterstock.com`, `istockphoto.com`, `freepik.com`
  - social aggregators: `tiktok.com`, `youtube.com`, `youtu.be`, `pinterest.com`,
    `twitter.com`, `x.com`

### Changes in `attribution.py`

- After the Telegram branch, guard on the page host: if `is_blocked_host(ctx.host)` →
  `return None`. Kills leaks that flow through rule 1 (first-person) and rule 3
  (single-business) for media/gov/stock/social pages.
- Rule 2 (external business link): if the link target host `is_blocked_host` → skip that
  link (do not attribute a media/stock/social domain as a third-party provider); fall
  through to the next rule.
- Rule 3 (single-business page): narrow `offer_block_count <= 3` → `offer_block_count <= 1`
  (only a page that is essentially one offer block counts as first-party).

**Rationale.** The host guard is the primary discriminator for known media/gov/stock; the
narrowed rule 3 shrinks the long tail of unknown news portals leaking as first-party.
Strong signals (explicit first-person, external business link) still attribute normally.

---

## 2. Business location (crawler)

Backend (`Offer.location`, `OfferCreate/Update/Out`) and admin (`OfferForm` «Локація»
field, `buildOfferPayload`) already support location. Only the crawler needs to fill it.

### Fetch layer

- `RawItem` gains `locality: str | None = None`.
- Website fetcher gains `_extract_locality(tree) -> str | None`, page-level, priority:
  1. JSON-LD `<script type="application/ld+json">` → `PostalAddress.addressLocality`
     (walk nested `address` / `@graph`).
  2. `meta[property="business:contact_data:locality"]`.
  3. `og:locality` / `meta[name="geo.placename"]`.
  The resolved locality is attached to every `RawItem` produced from that page.
- Other fetchers (og-meta, telegram) leave `locality = None`.

### Gazetteer `crawler/discovery/geo.py`

- `find_city(text: str) -> str | None` — matches a **curated list of Ukrainian cities**
  (oblast centres + large cities) and returns the canonical nominative form.
- Precision over recall: only known cities match. Basic inflection tolerance via
  stem/prefix matching, tuned to avoid the worst collisions (e.g. `Рівне`).

### Extraction / payload

- `OfferCandidate` gains `location: str | None = None`.
- `offer_payload` includes `location`.
- Extractor sets `location = item.locality or find_city(item.text)` (structured signal
  wins; gazetteer is fallback). `None` when nothing is found — admin fills manually.
- `content_hash` is **unchanged** (stays `content_hash(title, provider, text)`): location
  is metadata, not offer identity, so no dedup churn against already-stored offers.

---

## 3. Card text de-duplication (crawler + public)

### Public (primary fix — covers all offers, any source)

`OfferCard.vue`: do **not** render `card__dtext` when `title` duplicates `description`
(equal, or description starts with the title, normalised for whitespace/case). Removes the
visible duplication for all existing data immediately. Add a component test.

### Crawler (data hygiene)

Heuristic extractor: make `title` a concise headline distinct from the full body.
`title` = first sentence / first ~80 chars trimmed at a word boundary; `description` =
full text. Eliminates the "title = whole blob" case; on the card the front-guard still
hides it (title remains a prefix of body), but the detail view and admin get a clean short
title.

---

## Testing

- `crawler/tests/test_blocklist.py` — exact + subdomain + `*.gov.ua` matches; non-matches.
- `crawler/tests/test_attribution.py` — extend: blocked page host → None; blocked external
  link ignored; rule-3 narrowed to N≤1 (N=2 no longer first-party via rule 3).
- `crawler/tests/test_geo.py` — gazetteer matches / inflection / non-matches.
- website fetcher test — `_extract_locality` from JSON-LD / og / geo-meta.
- extractor test — `location` populated from `locality` and from gazetteer fallback;
  title/description split.
- `public/tests/components/OfferCard.test.js` — dtext hidden when duplicate, shown when
  distinct.

Existing suites must stay green (crawler offline; backend needs `mysql-container`).
Public: `npm run build` in addition to Vitest (scoped-Less regressions escape Vitest).

## Follow-ups (not this branch)

- News Telegram channels still attribute as providers (blocklist is host-based / website).
- IG/FB harvesting.
