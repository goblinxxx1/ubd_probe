# UBD Discounts — Search Discovery (SearXNG) Design — Track B

**Date:** 2026-07-15
**Scope:** Crawler active discovery — second search provider (self-hosted SearXNG)
**Status:** Approved design, ready for implementation planning
**Branch:** `feat/discovery-searxng` (cut from `main`)

## Context

Track A wired active discovery with a `DuckDuckGoProvider` (`ddgs`) behind the
`SEARCH_PROVIDERS` env switch, feeding `suggested_sources`. Track B adds a second
provider — **self-hosted SearXNG** — a metasearch engine that aggregates and
rotates across several upstream engines (Google/Bing/DuckDuckGo/Brave/Qwant…),
which is more resilient to bans than hitting one engine directly.

The Track A design is forward-compatible: `SEARCH_PROVIDERS` is a csv and
`build_search_provider` already dispatches by name, so Track B slots in as a new
provider branch plus a new compose service — no rework of Track A.

This is the second of three discovery tracks: A = DuckDuckGo (done),
**B = SearXNG (this)**, C = dedup layer (later).

## Goals

- Add a `searxng` Docker service (official `searxng/searxng` image) under the
  existing `crawler` compose profile — it starts with the crawler, not on a plain
  `up`.
- Implement `SearxngProvider`: `(keyword) -> list[SourceCandidate]` querying the
  service's JSON API. Best-effort: any error/unavailability logs and returns `[]`.
- Enable it via `SEARCH_PROVIDERS` (e.g. `searxng`, or `duckduckgo,searxng`).
- Reuse Track A's URL normalisation and the two-stage `suggested_sources` flow.
- Document the (unchanged) outbound source address and the added SearXNG upstream
  traffic.

## Non-Goals

- Cross-source / fuzzy dedup of candidates (Track C) — only Track A's basic URL
  normalisation here (duplicate candidates from DuckDuckGo + SearXNG are expected
  and handled later).
- Admin UI provider checkboxes — still env-driven.
- Publishing SearXNG's port to the host by default (internal only; optional debug
  publish noted).
- Tuning/curating SearXNG's engine list — keep its sensible defaults.

## Architecture

### SearXNG service (`docker-compose.yml` + `searxng/settings.yml`)

- New service `searxng`, image `searxng/searxng:latest`, `profiles: ["crawler"]`,
  internal port `8080` (not published).
- SearXNG does **not** serve JSON by default, so mount a custom
  `searxng/settings.yml` enabling it:
  ```yaml
  use_default_settings: true
  server:
    secret_key: "changeme"      # overridden by SEARXNG_SECRET env
    limiter: false              # no bot-limiter for internal single-client use
  search:
    formats: [html, json]
  ```
  The image substitutes `secret_key` from the `SEARXNG_SECRET` env var.
- Healthcheck (e.g. GET `/healthz` or `/`), and `crawler depends_on searxng`.

### SearxngProvider (`crawler/crawler/discovery/providers.py`)

`SearxngProvider(base_url, results_per_keyword=7, min_delay=4.0, client_factory=…)`,
a callable `(keyword) -> list[SourceCandidate]`:
- `GET {base_url}/search` with params `q=<keyword>`, `format=json`.
- Parse `results[:n]`, take each `result["url"]`, normalise via the existing
  `_normalize_url`, build `SourceCandidate(type="website",
  url_or_handle=<url>, name=result.get("title") or url,
  discovery_note="searxng: <keyword>")`.
- Honours `min_delay` between queries; wrapped best-effort → `[]` on any failure.
- Uses an injectable HTTP client factory (httpx) so tests can mock it.

### Config + combinator

- New env: `SEARXNG_URL` (default `http://searxng:8080`), `SEARXNG_SECRET`.
- `config.py` gains `searxng_url: str`.
- `build_search_provider` adds `elif name == "searxng": SearxngProvider(base_url=
  config.searxng_url, results_per_keyword=…, min_delay=…)`.
- `SEARCH_PROVIDERS` default stays `duckduckgo`; SearXNG is enabled by listing
  `searxng` (alone or with `duckduckgo`).

### Network

The crawler's outbound source address is unchanged — `192.168.20.69` (host LAN
IP; both the crawler and SearXNG containers NAT through the host). With SearXNG
enabled, outbound traffic additionally goes to whatever upstream engines SearXNG
queries (Google/Bing/DuckDuckGo/Brave/Qwant/etc.). `README-docker.md` notes this.

### Run model

Same as Track A: first run manually, then schedule. `searxng` comes up with
`docker compose --profile crawler up -d` / `run`.

## Data flow

```
SEARCH_KEYWORDS → SearxngProvider → GET searxng:8080/search?format=json
   → normalise URLs → SourceCandidate(website) → ActiveDiscovery (dedup vs known)
   → submit_suggestion → suggested_sources → admin moderation
```

## Error handling & edge cases

- SearXNG down / slow / non-200 / bad JSON → log + `[]`; pass survives.
- Empty results → zero candidates, no error.
- Candidate already a known source → skipped by `ActiveDiscovery`.
- `searxng` not listed in `SEARCH_PROVIDERS` → provider not built; service can
  still be up but is simply unused.
- Both providers enabled → duplicate candidates possible; deduped against `known`
  within a pass, full cross-provider dedup deferred to Track C.

## Testing & verification

- `SearxngProvider`: mock HTTP client → returns normalised website candidates with
  the `searxng:` note; a client error or non-JSON body yields `[]` (best-effort).
- `build_search_provider`: `searxng` builds a provider; `duckduckgo,searxng` builds
  a combined one.
- End-to-end (Docker): `docker compose --profile crawler up -d searxng`; a real
  pass with `SEARCH_PROVIDERS=searxng` populates `suggested_sources`; confirm in
  admin. If SearXNG's upstreams rate-limit, the pass still completes (best-effort).

## Open decisions (defaulted, override at planning time)

- Image `searxng/searxng:latest`; internal port 8080; not published.
- `SEARCH_PROVIDERS` default remains `duckduckgo`.
- Keep SearXNG's default engine set; `limiter: false` for internal use.
