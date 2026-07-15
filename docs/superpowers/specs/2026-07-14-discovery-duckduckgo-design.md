# UBD Discounts — Search Discovery (DuckDuckGo) Design — Track A

**Date:** 2026-07-14
**Scope:** Crawler active discovery — first search provider
**Status:** Approved design, ready for implementation planning
**Branch:** `feat/discovery-duckduckgo` (cut from `main`)

## Context

The crawler currently only visits **already-registered** sources and does passive
discovery (extracting social handles from content it already fetched). The
active, search-based discovery layer (`ActiveDiscovery` in
`crawler/crawler/discovery/active.py`) exists as a skeleton but is **completely
disconnected**: `wiring.py` never instantiates it, `runner.py` never calls it, no
keywords are supplied, and its `search_provider` hook is `None`.

Track A wires up active discovery end-to-end with a first provider —
**DuckDuckGo** — so the crawler can find *new* candidate sources by searching the
web, removing the "where do sources come from" bottleneck. Results feed
`suggested_sources` for human moderation (they do NOT become offers directly).

This is the first of three planned discovery tracks: **A = DuckDuckGo (this)**,
B = SearXNG (self-hosted service, later), C = dedup layer (later).

## Goals

- Implement `DuckDuckGoProvider`: `(keyword) -> list[SourceCandidate]` using the
  free, keyless `ddgs` library. Best-effort: any error/ban logs and returns empty,
  never crashing the crawl pass.
- Connect `ActiveDiscovery` into `wiring.py` + `runner.py`, gated by
  `ACTIVE_DISCOVERY=true` and the enabled provider list.
- Feed discovered candidates into `suggested_sources` (two-stage: moderation, not
  offers).
- Keyword-driven search from an env list (17 seed phrases across UBD/veteran,
  their families, ДСНС, police, war-disabled, families of the fallen).
- Basic URL normalisation before submitting candidates (full cross-source dedup is
  Track C).
- Document the crawler's **outbound source address** for a router firewall
  exception.

## Non-Goals

- **SearXNG provider / service** — Track B. The config is forward-compatible
  (`SEARCH_PROVIDERS` csv) so B slots in without rework.
- **Cross-source / fuzzy dedup** of candidates and offers — Track C. Only minimal
  URL normalisation here.
- **Admin UI checkboxes** for providers — later; providers are enabled via env in
  Track A.
- **Keyword generation from categories** — env list only for now.
- Turning search results into offers directly — they stay candidate *sources*.

## Architecture

### Provider (`crawler/crawler/discovery/providers.py`)

`DuckDuckGoProvider` is a callable `(keyword: str) -> list[SourceCandidate]`:
- Uses `ddgs` to fetch the top `results_per_keyword` (default 7) web results.
- Each result URL → `SourceCandidate(type="website", url_or_handle=<normalised
  url>, discovery_note="ddg: <keyword>")`.
- Wrapped so any exception (network, rate-limit/ban, library breakage) is logged
  and yields `[]` — the crawl pass survives.
- Honours a configurable inter-query delay (`SEARCH_MIN_DELAY`, default 4s) to
  reduce ban risk.

A small combinator builds one `search_provider` callable from the enabled
providers listed in `SEARCH_PROVIDERS` (Track A: just `duckduckgo`).

### Wiring + runner integration

- `wiring.py`: when `config.active_discovery` is true, construct the enabled
  providers, combine them, and create `ActiveDiscovery(budget, provider)`; pass it
  into `Runner`. When false (default), pass `None` — no behaviour change.
- `runner.run()`: after visiting sources, if active discovery is present, run
  `ActiveDiscovery.run(keywords, known)` and `submit_suggestion(...)` each returned
  candidate (reusing the existing suggestion payload path). `known` already
  contains normalised refs of current sources, so candidates matching existing
  sources are skipped by `ActiveDiscovery`.

### Config (`crawler/crawler/config.py`, all env)

- `ACTIVE_DISCOVERY=true` — master switch (already exists as a field).
- `SEARCH_PROVIDERS=duckduckgo` — csv of enabled providers.
- `SEARCH_KEYWORDS="phrase1, phrase2, …"` — the 17 seed phrases (csv).
- `SEARCH_RESULTS_PER_KEYWORD=7`.
- `SEARCH_MIN_DELAY=4` — seconds between search queries.
- `SEARCH_BUDGET` — max keywords processed per pass (default = number of keywords).

### URL normalisation

Before building a `SourceCandidate`, normalise the result URL: strip `utm_*` query
params and `#fragment`, drop a trailing slash, lowercase the host. Reuse/extend
`normalize_ref` from `passive.py` where practical so `known`-matching stays
consistent. Reserved-path junk (e.g. social `/p/…`, `/share/…`) is filtered.

### Outbound network address (operations)

The crawler runs in a Docker container; its egress is NAT'd through the host, so
the router sees the **host LAN IP** as the source. On the current machine that is
**`192.168.20.69`** (Wi-Fi, gateway `192.168.20.1`). The network admin adds this
address to the router's outbound exception. Caveat: DHCP may change it — reserve a
static/DHCP-reserved IP so the exception stays valid. Destination domains, for
reference: `duckduckgo.com`, `links.duckduckgo.com`, `html.duckduckgo.com`, plus
any discovered site. This goes in `README-docker.md`.

### Run model

First run manually to verify firewall + candidates appear:
`docker compose --profile crawler run --rm crawler` (with `ACTIVE_DISCOVERY=true`).
Then schedule via `CRAWL_INTERVAL_SECONDS>0` + `docker compose --profile crawler up -d crawler`.

## Data flow

```
SEARCH_KEYWORDS → DuckDuckGoProvider(ddgs) → normalise URL → SourceCandidate(website)
   → ActiveDiscovery (dedup vs known) → submit_suggestion → suggested_sources
   → admin moderation → approved → sources → (existing) website fetch → offers
```

## Error handling & edge cases

- Provider error/ban → log + `[]`; other keywords and the rest of the pass proceed.
- `ddgs` returns nothing → zero candidates, no error.
- Candidate URL already a known source → skipped by `ActiveDiscovery`.
- `ACTIVE_DISCOVERY=false` or empty `SEARCH_PROVIDERS`/`SEARCH_KEYWORDS` → discovery
  no-op; ordinary crawl unaffected.
- Malformed result URL → normalisation drops it rather than submitting junk.

## Testing & verification

- `DuckDuckGoProvider`: mock `ddgs` → returns `SourceCandidate`s with normalised
  URLs + note; an exception from `ddgs` yields `[]` (best-effort).
- URL normalisation: utm/fragment/trailing-slash/host-case handled; junk filtered.
- Combinator: builds provider from `SEARCH_PROVIDERS`; unknown name ignored/logged.
- `runner`: discovery on → `submit_suggestion` called for new candidates, skipped
  for known; discovery off → never called.
- End-to-end (offline): a stubbed provider returning a candidate → one row in
  `suggested_sources` visible in admin.

## Open decisions (defaulted, override at planning time)

- 17 seed keywords (editable via env); 7 results/keyword; 4s inter-query delay.
- `SEARCH_PROVIDERS` default `duckduckgo`.
- URL normalisation reuses/extends `passive.normalize_ref`.
