# Active-Search Offer Harvesting (Variant A)

**Date:** 2026-07-18
**Track:** crawler / active discovery redesign
**Branch:** `feat/crawler-active-harvest`

## Problem

The crawler's Level-2 active search was built "the wrong way" relative to the
product intent. Today it treats every search-engine result as a **suggested
source** (`POST /api/internal/suggested-sources`) that an admin must approve
before anything is crawled. See `runner.py` active-discovery loop and
`discovery/providers.py`.

The intended behaviour (variant A): when active search finds a page, the crawler
should **fetch that page, extract the offer, and put it straight into Offers
moderation** — with the source becoming a *by-product* suggestion, not the
primary output.

Critical product rule (user): an offer is created **only when a provider can be
attributed** — someone who actually offers the discount. A page that merely
states "such discounts exist for UBD veterans" with no attributable provider is
*information*, not an offer and not a source. The text must be **explicitly
traversed** to decide this.

## Decisions (locked in brainstorming)

1. **Source fate:** offer + suggest source (both), but the suggestion is
   *conditional* on a successful, attributed extraction — not emitted for every
   result.
2. **Attribution:** heuristic, combining first-party detection **and**
   named-provider extraction (approaches 1+2). No cloud LLM (zero-cost runtime
   holds).
3. **Scope of types:** website + telegram for now. Instagram/Facebook results
   are ignored for now (a deferred follow-up) — deliberately **not** re-emitted
   as bare suggestions.
4. **Dedup:** backend `content_hash` dedup extended to source-less crawler
   offers, plus the existing `target_url` merge.
5. **Fetch budget:** 20 page fetches per pass (tunable via `.env`).

## Architecture

```
search providers ──► ActiveDiscovery ──► candidate URLs (deduped vs known/seen)
                                            │
                                            ▼
                                     ActiveHarvester  (budget = 20 / pass)
                                            │  fetch (WebsiteFetcher / TelegramFetcher)
                                            ▼
                                     RawItem blocks + page context
                                            │  HeuristicExtractor (discount fields)
                                            │  attribute()          (provider + validity)
                                            ▼
                        valid offer? ──► submit_offer(source_id=None)  → moderation
                                    └──► submit_suggestion (conditional) → suggested sources
```

### Component responsibilities

- **`discovery/providers.py`** — unchanged. Search keyword → list of classified
  `SourceCandidate` (type, normalized URL, name). Best-effort.
- **`discovery/active.py` `ActiveDiscovery`** — unchanged role: run search over
  keywords, dedup candidates against `known` sources and `seen` set, return the
  list of candidate URLs. It no longer implies "suggest these".
- **`extract/attribution.py` (NEW)** — pure function
  `attribute(block, page_ctx) -> Attribution | None`. Given one offer block and
  its page context, decide provider + whether/what to suggest. No I/O.
- **`discovery/harvest.py` (NEW) `ActiveHarvester`** — orchestrates the harvest:
  for each candidate (within the fetch budget), fetch via the matching fetcher,
  run `HeuristicExtractor` for discount fields and `attribute()` for the
  provider, submit valid offers with `source_id=None`, and conditionally submit
  the source suggestion. Enforces the per-pass fetch budget and reuses the
  existing `RateLimiter` for politeness.
- **`models.py`** — `RawItem` gains an optional `site_name: str | None = None`
  (page-level brand hint), populated by `WebsiteFetcher` so attribution needs no
  second page parse.
- **`runner.py`** — the active-discovery branch calls `ActiveHarvester` instead
  of submitting a suggestion per search result.

## Provider attribution algorithm

Page context (`page_ctx`) computed once per fetched page:
- `brand` (`B`) = `og:site_name` → cleaned `<title>` → first `h1` (whichever is
  first non-empty).
- `host` (`H`) = the page's registrable host.
- `offer_block_count` (`N`) = number of blocks on the page that pass the
  discount-trigger gate.

For each block that passed the discount-trigger gate (see
`HeuristicExtractor`), with block text `T` and outbound links `L`:

1. **first-party (first-person):** if the block reads first-person
   (`\b(ми|у нас|наш\w*|для наших)\b`, case-insensitive) and `B` is present →
   `provider = B`, `suggest = origin(H)`. First-person wins over an outbound
   link, because a business site can also link out (booking, partners).
2. **third-party (named provider):** else if `L` contains a business link
   (host ≠ `H`, not a social host — reuse `extract.heuristic._pick_target`) →
   named third party. `provider` = registrable domain of that external link
   (host without `www.`); `suggest` = `origin` of that link.
3. **first-party (single-business):** else if the page looks like a
   single-business page (`N <= 3`) and `B` is present → `provider = B`,
   `suggest = origin(H)`.
4. **generic info → reject:** otherwise return `None` (no offer, no source).

**Telegram:** the channel is inherently the provider (first-party). `provider` =
channel title; `suggest` = the channel URL/handle. (No `_pick_target`/`N`
gymnastics; a telegram post that passes the discount gate yields an offer
attributed to its channel.)

`Attribution` dataclass: `provider: str`, `is_first_party: bool`,
`suggest_type: str | None`, `suggest_url_or_handle: str | None`,
`suggest_name: str | None`.

## ActiveHarvester flow

```
def harvest(candidates, cats, known, summary):
    used = 0
    for cand in candidates:                       # already deduped by ActiveDiscovery
        if used >= fetch_budget: break
        if cand.type not in ("website", "telegram"): continue   # IG/FB deferred
        ref = normalize_ref(cand.type, cand.url_or_handle)
        if ref in known: continue                 # already an active source
        used += 1
        items, _ = fetcher_for(cand).fetch(as_source(cand), None)
        passing = [it for it in items if extractor.extract(it, "", cats) is not None]
        page_ctx = build_page_ctx(cand, passing)  # brand B, host H, block count N=len(passing)
        for item in passing:                      # already passed the discount-trigger gate
            attr = attribute(item, page_ctx, cand.type)
            if attr is None: continue             # generic info → skip
            offer = extractor.extract(item, attr.provider, cats)  # content_hash uses real provider
            api.submit_offer(offer_payload(offer))   # source_id=None (offer.source_id unset)
            summary["offers"] += 1
            if attr.suggest_url_or_handle:
                s_ref = normalize_ref(attr.suggest_type, attr.suggest_url_or_handle)
                if s_ref not in known:
                    api.submit_suggestion(suggestion_payload_from(attr))
                    known.add(s_ref)
                    summary["suggestions"] += 1
```

Notes:
- `fetcher_for(cand)` reuses the runner's existing `WebsiteFetcher` /
  `TelegramFetcher`. `as_source(cand)` builds a throwaway
  `{"id": None, "type", "url_or_handle", "name"}` dict — no `crawl-state` call
  (those need a real source id).
- `HeuristicExtractor.extract` is called with the attributed `provider` so its
  `content_hash = hash(title, provider, text)` is correct for dedup. It already
  sets discount fields, `target_url` (via `_pick_target`), categories,
  `image_url`, `article_url`, `site_url`. `source_id` stays unset, so
  `offer_payload` sends `source_id=None`. (The first, gate-only `extract(it, "")`
  pass just filters blocks and counts `N`; its output is discarded.)
- Errors per candidate are isolated (log + continue); harvest never crashes the
  pass — same posture as the existing discovery loop.

## Backend changes

`crud/offer.py` `create_offer` — extend the `content_hash` dedup so it also
fires for source-less crawler offers:

```
if content_hash is not None and created_by == CreatedBy.crawler:
    q = db.query(Offer).filter(Offer.content_hash == content_hash)
    q = q.filter(Offer.source_id == source_id) if source_id is not None \
        else q.filter(Offer.source_id.is_(None))
    existing = q.first()
    if existing is not None:
        return existing
```

This keeps the current source-scoped behaviour identical, and adds
`source_id IS NULL` dedup for active-search offers. A rejected offer is **not**
resurrected: `create_offer` returns the existing row regardless of its status,
so it never re-enters the moderation queue. The existing `target_url` merge for
crawler offers stays as-is and runs after this guard.

Router `/api/internal/offers` already accepts `source_id: int | None = None`
(`InternalOfferCreate`) — no change.

## Configuration

New `.env` key (with `_RawSettings` + `Config` + `load_config` plumbing):

- `ACTIVE_FETCH_BUDGET=20` — max page fetches per pass for active harvesting.
  `0` disables harvesting (falls back to search-only, emitting nothing).

Existing `ACTIVE_DISCOVERY`, `SEARCH_PROVIDERS`, `SEARCH_KEYWORDS`,
`SEARCH_RESULTS_PER_KEYWORD`, `SEARCH_MIN_DELAY`, `SEARCH_BUDGET`, `SEARXNG_URL`
are unchanged.

## Testing

New / changed tests:

- **`test_attribution.py` (new)** — first-party (first-person marker), first-party
  (single-business `N<=3` + brand), third-party (external business link →
  provider + suggest that site), generic-info reject (no provider, aggregator-ish
  `N>3` no first-person), telegram (channel = provider).
- **`test_active_harvest.py` (new)** — fetch budget cap honoured; candidate already
  in `known` skipped; valid block → `submit_offer(source_id=None)` + conditional
  `submit_suggestion`; reject → nothing submitted; per-candidate error isolated.
- **`test_runner_discovery.py`** — rewritten: active branch now harvests offers
  instead of blindly suggesting every result.
- **`test_active_discovery.py`** — trimmed to `ActiveDiscovery`'s remaining role
  (candidate dedup), suggestion assertions removed.
- **backend `test_internal.py`** — source-less offer with a repeated
  `content_hash` is deduped (second POST returns the same offer id); a rejected
  source-less offer is not resurrected by a re-POST.

Zero-cost / offline: all tests use fakes for search providers, fetchers, and the
API client — no network.

## Out of scope (deferred follow-ups)

- Instagram / Facebook active harvesting (needs account pool + ban-risk handling
  on arbitrary URLs).
- LLM-based provider attribution (`local_llm` extractor hook stays a stub).
- Aggregator listings where each entry names a distinct business without its own
  link — v1 rejects these; smarter multi-provider splitting is future work.
