# Crawler Precision — Design

**Date:** 2026-07-21
**Track:** improve crawler extraction precision — cut false-positive "offers" and fix missed location.
**Branch:** `feat/crawler-precision` (from `main`).

## Goal

Reduce noise in the moderation queue and improve extraction quality. Four independent levers in the
crawler's extract/attribution layer:

1. **UBD-relevance gate** — don't create an offer with no target-audience signal.
2. **Location extraction** — find the offer's city even when it's in the page's address/contacts, not
   the offer block (offer 10: Dr.Oculus clinic, city "Вишневе"/"Київ" missed → `location=null`).
3. **Telegram channel gate** — general news/info/educational channels (e.g. `t.me/nau_info`, a
   university info channel) must not be treated as offer providers.
4. **Stricter discount parsing** — a bare percentage must not turn arbitrary text into an "offer"
   (a fare-increase news post `145→544 грн` became a fake "-18%" discount).

**Scope:** crawler logic only (`crawler/`). No DB schema changes, no new backend endpoints. Moderation
already blocks junk from reaching the public site — this is about queue noise and extraction quality,
not corrupted live data.

## Observed evidence (moderation queue snapshot)

- 6 of 17 pending offers were from one Telegram channel `t.me/nau_info` — all university news
  (dorm registration, stipend ratings, graduation, transport fare hike, master's admission), none a
  UBD discount. 10 of 17 had no target ("для кого") category at all.
- Offer 10 (Dr.Oculus, `optica-oculus.com.ua`) is a **genuine** UBD offer (15%/10% for УБД + war-disabled,
  target_cats correctly `[УБД, інвалід війни]`) but `location=null` — its city lives in the page's
  contact/address area, not the offer block; the site has no JSON-LD `addressLocality`.

## Design decisions (resolved with user)

- **Relevance gate is soft:** create the offer if it has a target-category match **OR** an explicit
  UBD/veteran keyword in the text — not strictly requiring a DB category. Fewer false negatives.
- **Location strategy:** structured metadata → address/contact region → offer text (in that priority),
  plus a curated gazetteer expansion. Precise: look where the address actually is, don't grab an
  incidental city.
- **Telegram gate:** name/description heuristic **and** a curated handle blocklist (both).
- All four levers are in scope, implemented as independently testable units.

## Why all four (layering)

The levers are complementary, not redundant. The soft relevance gate alone does not catch
military-themed *news*: e.g. a "виплати мобілізованим" post matches the `військов` audience keyword and
would pass the relevance gate — but the Telegram-channel gate (news/info channel) and the stricter
discount parser (no genuine discount) catch it. Each junk class needs its own net.

## Components

### 1. UBD-relevance gate — `crawler/crawler/extract/heuristic.py`, `crawler/crawler/discovery/lexicon.py`

In `HeuristicExtractor.extract()`, target audiences are already derived as
`target_slugs = classify(blob, TARGET_LEXICON)` where `blob = provider + site_name + text`. The gate:

- **If `target_slugs` is empty → return `None`** (skip the offer). Because `target_slugs` is the
  curated audience-keyword match (independent of whether a DB category exists), this is exactly the
  "target-category OR explicit UBD keyword" soft rule.
- **Extend `TARGET_LEXICON`** to cover the audiences the platform serves that are currently missing —
  **ДСНС/рятувальники** and **поліція/Національна поліція** — so their legitimate offers pass the gate
  (and get a "для кого" category). Existing entries (УБД, Ветеран, war-disability, fallen-family, IDP)
  stay.

The gate runs inside `extract()`, so it applies to **both** the passive crawl path
(`runner._crawl_source`) and the active-harvest path (`harvest.ActiveHarvester`) — both call
`extract()`.

### 2. Location extraction — `crawler/crawler/fetchers/website.py`, `crawler/crawler/discovery/geo.py`

Broaden page-level locality detection (`_extract_locality`), which today reads only JSON-LD
`addressLocality`. New priority order (first hit wins):

1. **Structured metadata:** JSON-LD `addressLocality` (existing) **and** HTML microdata
   `[itemprop=addressLocality]`; `<meta property="og:locality">` /
   `<meta property="business:contact_data:locality">`; `<meta name="geo.placename">`.
2. **Address/contact region:** run `find_city` over text scoped to `<address>` elements, the page
   footer, and blocks whose text contains address markers (`вул.`, `м.`, `адреса`, `контакти`,
   `місто`). This targets where a business address actually appears.
3. **Offer text:** the extractor already falls back to `find_city(text)` then the `Онлайн` signal
   (`heuristic.py:96`) — unchanged.

The fetcher attaches the resolved page locality to each `RawItem.locality` (as today). The extractor's
`location = item.locality or find_city(text) or (Онлайн …)` line is unchanged.

**Gazetteer expansion (`geo.py`, `_CITIES`):** add **Вишневе** and other Kyiv-agglomeration towns
(Ірпінь, Буча, Бровари, Бориспіль, Фастів, Вишгород, Обухів), plus a set of additional raion centres,
each with nominative + common oblique surface forms. Keep the precision-over-recall philosophy
(curated forms, word-boundary matching). This is a curated expansion, not full-settlement coverage.

### 3. Telegram channel gate — `crawler/crawler/discovery/attribution.py`, `crawler/crawler/discovery/blocklist.py`

Add a Telegram equivalent of the existing website `is_blocked_host`. In `blocklist.py`:

- `_TELEGRAM_HANDLES` — a curated set of blocked channel handles (seed: `nau_info`).
- `_CHANNEL_NEWS_LEXICON` — a curated lexicon of news/info/educational markers (`новини`, `інфо`,
  `news`, `info`, `університет`, `студент`, `коледж`, `абітурієнт`, `розклад`, `КАІ`, …).
- `is_blocked_telegram(handle, name)` → `True` if the handle is in the blocklist **or** the channel
  name/description matches the news/info lexicon.

In `attribution.py`, the telegram branch of `attribute()` (currently `ctx.cand_type == "telegram"` →
returns the channel as provider) calls `is_blocked_telegram(handle, channel_name)` first; if blocked,
returns `None` (no attribution → no offer/suggestion). Handle comes from the candidate URL
(`t.me/<handle>`); the channel name/title comes from the fetched page (`item.site_name` / page title).

This gate sits at the **active-harvest attribution point** — the entry where search-discovered Telegram
channels become providers. The relevance (§1) and discount (§4) gates in `extract()` remain as
backstops for any telegram content on both paths.

### 4. Stricter discount parsing — `crawler/crawler/extract/heuristic.py`

- **Remove the bare `"%"`** from `_OFFER_TRIGGERS` (`heuristic.py:31`). A percentage alone must not
  make a block an "offer". Real triggers (`знижк`, `акці`, `промокод`, `безкоштов`, `безплатн`,
  `діє до`, `спецпропоз`, `розпродаж`) stay.
- **Discount-context requirement for percent:** treat an `N%` match as a `percent` discount only when a
  discount keyword (`знижк`, `акці`, `економ`, `вигід`, or a `-N%` form) is present in the same block.
  If the percentage lacks that context, `discount_type`/`discount_value` stay `None` — the block is
  still only an offer if it independently passed the pruned `_OFFER_TRIGGERS` gate (so a lone
  context-less percentage no longer produces an offer at all, since `%` is removed from the triggers).
- **Price-increase guard:** if the block contains increase markers (`зростання`, `подорожчання`,
  `підвищення варт`, `дорожч`, `буде … грн`) and no genuine discount phrase, it is **not** an offer
  (`extract()` returns `None`). This kills fare/price-hike news.

## Component interaction

`extract()` order: offer-trigger gate (pruned) → price-increase guard → relevance gate (target_slugs) →
discount parse (context-checked) → build candidate. Any gate failing returns `None`. Telegram gate is
upstream in `attribute()` (active harvest). No change to models, payloads, or the runner/harvester
control flow beyond `extract()`/`attribute()` returning `None` more often.

## Testing

Real-case fixtures drive the tests:

- **Relevance gate:** a UBD offer (Dr.Oculus text) → passes; a university-news text with no audience
  keyword → `None`; a ДСНС/поліція offer → passes (after lexicon extension).
- **Location:** an `optica`-style page (address "м. Вишневе …" in a contact block, no JSON-LD) →
  `locality == "Вишневе"`; a page with JSON-LD `addressLocality=Київ` → `"Київ"`; a page listing
  several delivery cities in body but one address city → the address city wins; `find_city("Вишневе")`
  → `"Вишневе"` (gazetteer).
- **Telegram gate:** `is_blocked_telegram("nau_info", …)` → `True`; a news-named channel → `True`; a
  plain business channel → `False`; `attribute()` returns `None` for a blocked telegram candidate.
- **Discount parse:** the transport fare-hike text (`145→544 грн`, `18%` incidental) → `None`
  (price-increase guard / no discount context); "знижка 15%" → `percent, 15`; a bare "18%" with no
  discount word and no other trigger → `None`.

Existing extractor/attribution tests must stay green (the good cases: Dr.Oculus, fixture offers,
Rezervist). Full crawler suite green.

## Out of scope

- DB schema, backend endpoints, admin/public UI.
- LLM-based classification.
- Full Ukrainian settlement gazetteer (curated expansion only).
- Bulk-cleaning the current moderation queue (a separate operational action, not this code track).
