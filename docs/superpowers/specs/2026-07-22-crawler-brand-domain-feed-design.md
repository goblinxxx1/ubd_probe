# Crawler Brand→Domain Feed — Design (self-growing discovery, track 2)

**Status:** design approved; implemented (Tasks 1-6). Post-review addendum: brand-emission **rotation** added (Task 7) — the harvester's `active_fetch_budget` caps fetches per pass, so the feed emits a rotating window of brands (persisted cursor in `brand_domains.json`, size = `brand_feed_per_pass`, default 20) advancing each pass, so all brands — including ones added as the curated set grows — get covered over successive passes instead of only the first N in dict order.

## Goal

Give discovery a **DDG-independent** source of website candidates: resolve a curated
set of retail brands to their official domains via a **rare, gated** OSM/Wikidata
refresh, persist the result to a brand→domain cache, and feed those domains as
`website` `SourceCandidate`s into the existing `ActiveHarvester` on every pass. This
is the "brand→domain feed" P1 item from the discovery-scaling brainstorm — the biggest
lever against the DDG throttling bottleneck, because the hot path (every crawl pass)
reads only the offline cache; the network is touched only when the cache is stale.

## Scope & non-goals

**This track is deliberately plumbing.** It does not, on its own, need to produce
offers — meaningful offer yield comes from the *combined* approved stack (sitemap
depth, polite layer, etc.) landing on top of it. Success for THIS track = brand
domains reliably enter the candidate pipeline, deterministically and offline within a
pass.

- **IN:** curated brand seeds (name + Wikidata QID + fallback domain); a best-effort
  `BrandResolver` (Wikidata P856 → Overpass `website` → curated fallback); a persisted
  `BrandDomainCache` with a freshness gate; a `BrandFeed` that emits deduped `website`
  candidates; config knobs; wiring that **decouples** the harvester from
  `active_discovery` so the feed runs independently.
- **OUT (later tracks):** fetch depth beyond the homepage (robots→sitemap→BFS≤2),
  the polite layer (per-domain robots cache / Crawl-delay), discovering *new* brands
  (snowball / OSM category harvest), domain-rating, marketing lexicon. No DB schema,
  no backend/UI/LLM changes.

## Global constraints

- Crawler logic only. Deterministic curated core (tuples/dicts + `re`), same technique
  as `lexicon.py`/`geo.py`/`query_grid.py`. Network is best-effort and only in the
  refresh path.
- Extraction/attribution downstream is **untouched** — brand domains are just another
  candidate source feeding the existing harvester; the precision gates remain the net.
- Every crawl pass is a fresh process (`python -m crawler run`), so the cache and its
  `refreshed_at` timestamp MUST round-trip through `brand_domains.json`.
- `active_discovery` default stays **`False`** (unchanged). `brand_feed_enabled`
  defaults **`True`** but is independent of `active_discovery`.

## Architecture

New module `crawler/crawler/discovery/brand_feed.py` (curated core + isolated units).
Candidates it produces union with the DDG-derived candidates before harvest:

```
[rare, gated, best-effort]   BrandResolver ── refresh ──▶ BrandDomainCache (brand_domains.json)
[every pass, offline]        BrandDomainCache ─▶ BrandFeed ─▶ SourceCandidate[] ─┐
                             ActiveDiscovery(DDG) ─▶ SourceCandidate[] ──────────┤
                                                                                 ▼
                                                    union(dedup vs known) ─▶ ActiveHarvester.harvest(...)
```

## Components & interfaces

### 1. Curated seeds — `BRAND_SEEDS`
A curated mapping keyed by brand name, aligned with `query_grid.BRANDS` (the 48 brand
names are the single source of truth for *which* brands exist). Each entry carries an
optional Wikidata QID and a **required** fallback domain:

```python
# brand -> (wikidata_qid | None, fallback_domain)   # values below are illustrative;
# actual QIDs/domains are curated during implementation Task 1.
BRAND_SEEDS = {
    "Rozetka": ("Q4048662", "rozetka.com.ua"),
    "OKKO":    ("Q12165655", "okko.ua"),
    "АТБ":     (None,        "atbmarket.com"),   # QID unknown → Overpass/fallback only
    # ... all 48 brands from query_grid.BRANDS
}
```

- Invariant (unit-tested): `set(BRAND_SEEDS) == set(query_grid.BRANDS)` — every brand
  has a seed, so the feed is never empty even with zero successful refreshes.
- QID may be `None` (brand lacks a clean Wikidata entity) → resolver skips straight to
  the Overpass/website fallback for that brand.

### 2. `BrandResolver`
Best-effort brand→domain resolution, HTTP injected for testability:

```python
class BrandResolver:
    def __init__(self, client_factory=None, overpass_url=..., wikidata_url=...,
                 user_agent=..., sleep=time.sleep, min_delay=1.0): ...
    def resolve(self, brand: str, qid: str | None) -> str | None:
        """Return a bare domain (host) or None. Order:
           1. qid present → Wikidata P856 'official website' → host
           2. else/on failure → Overpass `website`/`contact:website` tag for the
              brand, aggregated to the most common host
           Any exception → None (caller falls back to the curated seed domain)."""
```

- Wikidata P856 via the public API (`action=wbgetclaims&property=P856`), Overpass via a
  `nwr["brand"=…]["website"]` query. Both require a descriptive `User-Agent`.
- Returns a normalized bare host (scheme/path/`www.` stripped). No exceptions escape.

### 3. `BrandDomainCache`
Persisted JSON, atomic writes (mirrors `SearchState._save`):

```python
# brand_domains.json: {"version": 1, "refreshed_at": 0.0, "domains": {brand: domain}}
class BrandDomainCache:
    @classmethod
    def load(cls, path, clock=time.time) -> "BrandDomainCache": ...
    def is_stale(self, ttl_seconds: float) -> bool          # now - refreshed_at >= ttl
    def domains(self) -> dict[str, str]
    def replace(self, domains: dict[str, str]) -> None       # set domains, stamp refreshed_at, save
```

- Corrupt/missing file → clean empty cache (same tolerance as `SearchState.load`).

### 4. `refresh_brand_domains(cache, resolver, seeds, clock)`
Rare batch, best-effort per brand:

```python
def refresh_brand_domains(cache, resolver, seeds=BRAND_SEEDS) -> None:
    resolved = {}
    for brand, (qid, fallback) in seeds.items():
        domain = None
        try:
            domain = resolver.resolve(brand, qid)
        except Exception:            # noqa: BLE001 — one brand must not kill the refresh
            domain = None
        resolved[brand] = domain or fallback      # curated fallback guarantees a value
    cache.replace(resolved)
```

### 5. `BrandFeed`
Offline candidate emitter (no network — pure cache read):

```python
class BrandFeed:
    def __init__(self, cache: BrandDomainCache, seeds=BRAND_SEEDS): ...
    def candidates(self, known: set[str]) -> list[SourceCandidate]:
        """For each brand: domain = cache.domains().get(brand) or seed fallback.
           Emit SourceCandidate(name=brand, type='website',
           url_or_handle=f'https://{domain}', discovery_note=f'brand-feed:{brand}').
           Skip any whose normalize_ref('website', url) is already in `known`."""
```

## Wiring (`wiring.py` / `runner.py`)

Decouple the harvester gate and fold in a second candidate source.

`build_runner`:
- `brand_feed = None`. If `config.brand_feed_enabled`:
  - `cache = BrandDomainCache.load(config.brand_domains_path)`
  - if `cache.is_stale(config.brand_feed_refresh_hours * 3600)`: run
    `refresh_brand_domains(cache, BrandResolver(...from config...))` wrapped in
    try/except (best-effort; a failed refresh leaves the last-known / empty cache, and
    the feed still falls back to curated seed domains).
  - `brand_feed = BrandFeed(cache)`
- Build the harvester when `(config.active_discovery or config.brand_feed_enabled)` and
  `config.active_fetch_budget` (today it is gated on `active_discovery` alone).
- The DDG block (query-grid rotation + `ActiveDiscovery`) stays exactly as is, still
  under `if config.active_discovery:`.
- Pass `brand_feed=brand_feed` to `Runner`.

`Runner.run` (replace the current discovery block):
```python
if self._harvester is not None:
    candidates = []
    if self._discovery is not None and self._keywords:
        candidates += self._discovery.run(self._keywords, known)
    if self._brand_feed is not None:
        candidates += self._brand_feed.candidates(known)
    if candidates:
        self._harvester.harvest(candidates, cats, known, summary)
```
Wrapped in the existing best-effort try/except. `known` dedup already prevents a brand
domain that is also a tracked source from being re-harvested.

## Config (`config.py`, three mirrored spots each)

| field | env | default | note |
|---|---|---|---|
| `brand_feed_enabled: bool` | `BRAND_FEED_ENABLED` | `True` | independent of `active_discovery` |
| `brand_feed_refresh_hours: int` | `BRAND_FEED_REFRESH_HOURS` | `336` | domains are stable (14 days); refresh is rare |
| `brand_domains_path: str` | `BRAND_DOMAINS_PATH` | `/data/brand_domains.json` | beside `search_state.json` |
| `overpass_url: str` | `OVERPASS_URL` | `https://overpass-api.de/api/interpreter` | override for mirror/self-host/tests |
| `wikidata_url: str` | `WIKIDATA_URL` | `https://www.wikidata.org/w/api.php` | override for mirror/self-host/tests |

## Error handling

- Resolver: every failure path returns `None`; refresh substitutes the curated
  fallback domain. No network error ever escapes `refresh_brand_domains`.
- Refresh call in `build_runner` is wrapped best-effort — a dead network at pass start
  never crashes or blocks the pass; the feed proceeds on the existing cache + fallbacks.
- Cache load tolerates corrupt/missing files (clean empty cache).
- `Runner` discovery block stays inside its existing try/except.

## Testing (no network, deterministic)

- **`BrandResolver`**: injected `client_factory` returning canned Wikidata / Overpass
  JSON — verify P856 host extraction, Overpass `website` fallback + host aggregation,
  QID-`None` path, and that any HTTP exception yields `None`.
- **`BrandDomainCache`**: `tmp_path` round-trip; `is_stale` boundary against a fake
  clock; corrupt-file tolerance.
- **`refresh_brand_domains`**: fake resolver — resolved value wins; `None`/exception
  per brand falls back to the curated seed domain; cache stamped.
- **`BrandFeed`**: emits one `website` candidate per brand with the cached (or fallback)
  domain; dedups against `known`.
- **Seeds invariant**: `set(BRAND_SEEDS) == set(query_grid.BRANDS)`.
- **Wiring**: with `brand_feed_enabled=True, active_discovery=False` and a stubbed
  cache, `build_runner` builds a harvester and a `BrandFeed`, and `Runner.run` harvests
  brand candidates with **no** DDG provider; with both disabled, no harvester is built.
- **Config**: defaults + env overrides for the five new knobs.

## Implementation task sketch (for writing-plans)

1. `BRAND_SEEDS` + seeds-invariant test.
2. `BrandDomainCache` (load/save/is_stale/domains/replace) + tests.
3. `BrandResolver` (Wikidata P856 → Overpass website fallback) + mocked-HTTP tests.
4. `refresh_brand_domains` + `BrandFeed` + tests.
5. Config: five new knobs (three mirrored spots each) + tests.
6. Wiring: decouple harvester gate, refresh-on-stale in `build_runner`, `Runner`
   brand-feed candidate union + tests.
```
