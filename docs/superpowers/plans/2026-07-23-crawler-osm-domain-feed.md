# Crawler OSM domain enumeration feed — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-fill the domain catalog by enumerating Ukrainian branded POIs (with websites) from OpenStreetMap/Overpass and feeding their domains as website candidates into the existing walker→moderation→DomainRegistry pipeline — DDG-independently.

**Architecture:** A new `crawler/discovery/osm_feed.py` mirrors the brand-feed pattern: `OsmEnumerator` runs one best-effort Overpass query on a rare refresh and returns a filtered `brand→host` map; the result is cached in a reused `BrandDomainCache` (separate file); `OsmDomainFeed` emits a rotating window of website `SourceCandidate`s each pass. Wired into `Runner` beside `brand_feed`, gated by `osm_feed_enabled` (default ON, byte-eq off).

**Tech Stack:** Python 3.11, httpx, pytest, existing crawler package.

## Global Constraints

- Scope is `crawler/` only — no backend/admin/public, no DB.
- Baseline is **381** crawler tests green. Run from `crawler/`: `./.venv/Scripts/python.exe -m pytest -q` (no mysql needed for crawler).
- Nested package: crawler PROJECT root is `D:\ubd_probe\crawler` (`.venv`, `tests/`, `crawler/` package). Source under `crawler/crawler/…`; tests under `crawler/tests/`.
- New domains are only CANDIDATES; precision-gates (host-blocklist, attribution relevance-gate) + human moderation are downstream. Enumeration additionally pre-filters blocklisted hosts.
- `osm_feed_enabled=False` MUST be byte-equivalent (wiring builds no feed → `osm_feed=None` on Runner → branch not entered).
- Reuse existing pieces (do NOT reimplement): `BrandDomainCache` (`crawler/discovery/brand_feed.py`), `bare_host` (`crawler/util/hosts.py`), `is_blocked_host` (`crawler/discovery/blocklist.py`), `normalize_ref` (`crawler/discovery/passive.py`), `SourceCandidate` (`crawler/models.py`).
- Config defaults (exact): `osm_feed_enabled=True`, `osm_feed_refresh_hours=336`, `osm_feed_per_pass=20`, `osm_domains_path="/data/osm_domains.json"`, `osm_feed_max_domains=500`, `osm_min_pois=2`. Reuse `overpass_url`.
- Do NOT touch `BRAND_SEEDS`/`BrandFeed`; the OSM feed is additive (overlaps dedup naturally via `known`).

---

### Task 1: `OsmEnumerator`

**Files:**
- Create: `crawler/crawler/discovery/osm_feed.py`
- Test: `crawler/tests/test_osm_feed.py` (new)

**Interfaces:**
- Consumes: `bare_host` (util/hosts), `is_blocked_host` (discovery/blocklist).
- Produces: `class OsmEnumerator(overpass_url, timeout=25.0, min_pois=2, max_domains=500, client_factory=None, sleep=None, min_delay=1.0)` with `enumerate() -> dict[str, str]` (brand→host). Module constant `_OVERPASS_QUERY: str`.

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_osm_feed.py
from crawler.discovery.osm_feed import OsmEnumerator


class _FakeResp:
    def __init__(self, payload): self._payload = payload
    def raise_for_status(self): pass
    def json(self): return self._payload


class _FakeClient:
    def __init__(self, post_payload=None, boom=False):
        self._post, self._boom = post_payload, boom
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def post(self, url, data=None):
        if self._boom:
            raise RuntimeError("net down")
        return _FakeResp(self._post)


def _enum(elements, boom=False, **kw):
    return OsmEnumerator(
        overpass_url="http://ov", sleep=lambda s: None,
        client_factory=lambda: _FakeClient({"elements": elements}, boom=boom), **kw)


def test_aggregates_and_filters_by_min_pois():
    els = [{"tags": {"brand": "Foo", "website": "https://foo.ua/x"}},
           {"tags": {"brand": "Foo", "website": "http://foo.ua"}},
           {"tags": {"brand": "Bar", "website": "https://bar.ua"}}]   # single POI
    assert _enum(els, min_pois=2).enumerate() == {"Foo": "foo.ua"}


def test_contact_website_fallback():
    els = [{"tags": {"brand": "Cee", "contact:website": "https://cee.ua"}},
           {"tags": {"brand": "Cee", "contact:website": "https://cee.ua/uk"}}]
    assert _enum(els, min_pois=2).enumerate() == {"Cee": "cee.ua"}


def test_dedup_by_host_stable_first_brand_wins():
    els = [{"tags": {"brand": "Aaa", "website": "https://same.ua"}},
           {"tags": {"brand": "Aaa", "website": "https://same.ua"}},
           {"tags": {"brand": "Bbb", "website": "https://same.ua"}},
           {"tags": {"brand": "Bbb", "website": "https://same.ua"}}]
    assert _enum(els, min_pois=2).enumerate() == {"Aaa": "same.ua"}


def test_cap_max_domains():
    els = [{"tags": {"brand": "Aaa", "website": "https://a.ua"}},
           {"tags": {"brand": "Aaa", "website": "https://a.ua"}},
           {"tags": {"brand": "Bbb", "website": "https://b.ua"}},
           {"tags": {"brand": "Bbb", "website": "https://b.ua"}}]
    assert _enum(els, min_pois=2, max_domains=1).enumerate() == {"Aaa": "a.ua"}


def test_blocklisted_host_filtered(monkeypatch):
    import crawler.discovery.osm_feed as m
    monkeypatch.setattr(m, "is_blocked_host", lambda h: h == "bad.ua")
    els = [{"tags": {"brand": "Good", "website": "https://good.ua"}},
           {"tags": {"brand": "Good", "website": "https://good.ua"}},
           {"tags": {"brand": "Bad", "website": "https://bad.ua"}},
           {"tags": {"brand": "Bad", "website": "https://bad.ua"}}]
    assert _enum(els, min_pois=2).enumerate() == {"Good": "good.ua"}


def test_missing_brand_or_website_skipped():
    els = [{"tags": {"website": "https://x.ua"}},        # no brand
           {"tags": {"brand": "Y"}},                     # no website
           {"tags": {}}]
    assert _enum(els, min_pois=1).enumerate() == {}


def test_http_failure_returns_empty():
    assert _enum([], boom=True).enumerate() == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_osm_feed.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'crawler.discovery.osm_feed'`

- [ ] **Step 3: Write minimal implementation**

```python
# crawler/crawler/discovery/osm_feed.py
"""DDG-independent domain auto-fill: enumerate Ukrainian branded POIs with websites from
OpenStreetMap/Overpass and emit their domains as website candidates. Mirrors brand_feed —
Overpass is touched only on a rare refresh; passes read the cache offline."""

import logging
import time
from collections import Counter, defaultdict

import httpx

from crawler.discovery.blocklist import is_blocked_host
from crawler.util.hosts import bare_host

log = logging.getLogger(__name__)

_OSM_UA = "UBDCrawler/0.1 (+https://ubd.example; osm domain enumerator)"

# UA branded POIs that carry a website — chains, not one-off shops.
_OVERPASS_QUERY = (
    "[out:json][timeout:180];"
    'area["ISO3166-1"="UA"][admin_level=2]->.ua;'
    '(nwr(area.ua)["brand"]["website"];'
    'nwr(area.ua)["brand"]["contact:website"];);'
    "out tags 20000;"
)


class OsmEnumerator:
    """Best-effort brand→host enumeration via one Overpass query. HTTP is injected for tests;
    every failure path returns an empty map so the caller keeps the previous cache."""

    def __init__(self, overpass_url, timeout=25.0, min_pois=2, max_domains=500,
                 client_factory=None, sleep=None, min_delay=1.0):
        self._overpass = overpass_url
        self._min_pois = min_pois
        self._max_domains = max_domains
        self._client_factory = client_factory or (
            lambda: httpx.Client(timeout=timeout, headers={"User-Agent": _OSM_UA}))
        self._sleep = sleep or time.sleep
        self._delay = min_delay

    def enumerate(self) -> dict[str, str]:
        by_brand: dict[str, Counter] = defaultdict(Counter)
        for el in self._query():
            tags = el.get("tags", {})
            brand = (tags.get("brand") or "").strip()
            host = bare_host(tags.get("website") or tags.get("contact:website") or "")
            if brand and host:
                by_brand[brand][host] += 1
        # best host per brand, filtered by min POI count and blocklist
        picked: dict[str, str] = {}
        for brand, hosts in by_brand.items():
            host, count = hosts.most_common(1)[0]
            if count >= self._min_pois and not is_blocked_host(host):
                picked[brand] = host
        # dedup by host (stable brand order), cap
        seen: set[str] = set()
        out: dict[str, str] = {}
        for brand in sorted(picked):
            host = picked[brand]
            if host in seen:
                continue
            seen.add(host)
            out[brand] = host
            if len(out) >= self._max_domains:
                break
        return out

    def _query(self) -> list:
        try:
            if self._delay:
                self._sleep(self._delay)
            with self._client_factory() as client:
                resp = client.post(self._overpass, data={"data": _OVERPASS_QUERY})
                resp.raise_for_status()
                data = resp.json()
            return data.get("elements", []) or []
        except Exception as exc:  # noqa: BLE001 — enumeration best-effort
            log.warning("osm enumeration query failed: %s", exc)
            return []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_osm_feed.py -q`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/osm_feed.py crawler/tests/test_osm_feed.py
git commit -m "feat(crawler): OsmEnumerator — Overpass UA branded-domain enumeration"
```

---

### Task 2: `OsmDomainFeed`

**Files:**
- Modify: `crawler/crawler/discovery/osm_feed.py`
- Test: `crawler/tests/test_osm_feed.py` (append)

**Interfaces:**
- Consumes: `BrandDomainCache` (brand_feed), `normalize_ref`, `SourceCandidate`.
- Produces: `class OsmDomainFeed(cache, per_pass=20)` with `candidates(known: set[str]) -> list[SourceCandidate]`.

- [ ] **Step 1: Write the failing test**

```python
# append to crawler/tests/test_osm_feed.py
from crawler.discovery.brand_feed import BrandDomainCache
from crawler.discovery.osm_feed import OsmDomainFeed
from crawler.discovery.passive import normalize_ref


def _cache(tmp_path, mapping):
    c = BrandDomainCache.load(str(tmp_path / "osm.json"))
    c.replace(mapping)
    return c


def test_feed_emits_website_candidates(tmp_path):
    c = _cache(tmp_path, {"OKKO": "okko.ua", "EVA": "eva.ua"})
    cands = {x.name: x for x in OsmDomainFeed(c).candidates(known=set())}
    assert cands["OKKO"].type == "website"
    assert cands["OKKO"].url_or_handle == "https://okko.ua"
    assert cands["OKKO"].discovery_note == "osm-feed:okko.ua"


def test_feed_skips_known(tmp_path):
    c = _cache(tmp_path, {"OKKO": "okko.ua"})
    known = {normalize_ref("website", "https://okko.ua")}
    assert OsmDomainFeed(c).candidates(known) == []


def test_feed_empty_cache_is_safe(tmp_path):
    c = BrandDomainCache.load(str(tmp_path / "osm.json"))   # no replace → empty
    assert OsmDomainFeed(c).candidates(known=set()) == []


def test_feed_rotates_window_and_advances_cursor(tmp_path):
    c = _cache(tmp_path, {"A": "a.ua", "B": "b.ua", "C": "c.ua", "D": "d.ua"})
    feed = OsmDomainFeed(c, per_pass=2)
    assert [x.name for x in feed.candidates(set())] == ["A", "B"]
    assert [x.name for x in feed.candidates(set())] == ["C", "D"]
    assert [x.name for x in feed.candidates(set())] == ["A", "B"]   # wrapped
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_osm_feed.py -q -k feed`
Expected: FAIL — `ImportError: cannot import name 'OsmDomainFeed'`

- [ ] **Step 3: Write minimal implementation**

Add these two imports near the top of `crawler/crawler/discovery/osm_feed.py` (with the existing imports):
```python
from crawler.discovery.passive import normalize_ref
from crawler.models import SourceCandidate
```

Then append to `crawler/crawler/discovery/osm_feed.py`:

```python
class OsmDomainFeed:
    """Offline emitter: a rotating window of website SourceCandidates from the OSM cache,
    advancing the cache's persisted cursor each pass so the whole set is covered over passes."""

    def __init__(self, cache, per_pass=20):
        self._cache = cache
        self._per_pass = per_pass

    def candidates(self, known: set[str]) -> list[SourceCandidate]:
        brands = sorted(self._cache.domains())
        size = len(brands)
        if size == 0:
            return []
        n = max(1, min(int(self._per_pass), size))
        cursor = self._cache.cursor()
        if cursor < 0 or cursor >= size:
            cursor = 0
        window = [brands[(cursor + i) % size] for i in range(n)]
        self._cache.set_cursor((cursor + n) % size)
        domains = self._cache.domains()
        out: list[SourceCandidate] = []
        for brand in window:
            host = domains.get(brand)
            if not host:
                continue
            url = f"https://{host}"
            if normalize_ref("website", url) in known:
                continue
            out.append(SourceCandidate(
                name=brand, type="website", url_or_handle=url,
                discovered_from_source_id=None, discovery_note=f"osm-feed:{host}"))
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_osm_feed.py -q`
Expected: PASS (all — 7 enumerator + 4 feed)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/osm_feed.py crawler/tests/test_osm_feed.py
git commit -m "feat(crawler): OsmDomainFeed — rotating website candidates from OSM cache"
```

---

### Task 3: config flags

**Files:**
- Modify: `crawler/crawler/config.py` (`_RawSettings`, `Config`, `load_config`)
- Test: `crawler/tests/test_config.py` (append)

**Interfaces:**
- Produces: `Config.osm_feed_enabled=True`, `osm_feed_refresh_hours=336`, `osm_feed_per_pass=20`, `osm_domains_path="/data/osm_domains.json"`, `osm_feed_max_domains=500`, `osm_min_pois=2`.

- [ ] **Step 1: Write the failing test**

```python
# append to crawler/tests/test_config.py
def test_osm_feed_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)      # no .env -> defaults apply
    cfg = load_config()
    assert cfg.osm_feed_enabled is True
    assert cfg.osm_feed_refresh_hours == 336
    assert cfg.osm_feed_per_pass == 20
    assert cfg.osm_domains_path == "/data/osm_domains.json"
    assert cfg.osm_feed_max_domains == 500
    assert cfg.osm_min_pois == 2


def test_osm_feed_env_overrides(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OSM_FEED_ENABLED", "false")
    monkeypatch.setenv("OSM_FEED_MAX_DOMAINS", "50")
    monkeypatch.setenv("OSM_MIN_POIS", "3")
    cfg = load_config()
    assert cfg.osm_feed_enabled is False
    assert cfg.osm_feed_max_domains == 50
    assert cfg.osm_min_pois == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_config.py -q -k osm`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'osm_feed_enabled'`

- [ ] **Step 3: Write minimal implementation**

In `crawler/crawler/config.py`:

1. In `_RawSettings`, add after `brand_feed_per_pass: int = 20`:
```python
    osm_feed_enabled: bool = True
    osm_feed_refresh_hours: int = 336
    osm_feed_per_pass: int = 20
    osm_domains_path: str = "/data/osm_domains.json"
    osm_feed_max_domains: int = 500
    osm_min_pois: int = 2
```

2. In the `Config` dataclass, add after `brand_feed_per_pass: int = 20`:
```python
    osm_feed_enabled: bool = True
    osm_feed_refresh_hours: int = 336
    osm_feed_per_pass: int = 20
    osm_domains_path: str = "/data/osm_domains.json"
    osm_feed_max_domains: int = 500
    osm_min_pois: int = 2
```

3. In `load_config()`'s `Config(...)` call, add:
```python
        osm_feed_enabled=s.osm_feed_enabled,
        osm_feed_refresh_hours=s.osm_feed_refresh_hours,
        osm_feed_per_pass=s.osm_feed_per_pass,
        osm_domains_path=s.osm_domains_path,
        osm_feed_max_domains=s.osm_feed_max_domains,
        osm_min_pois=s.osm_min_pois,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_config.py -q`
Expected: PASS (all, including the 2 new)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/config.py crawler/tests/test_config.py
git commit -m "feat(crawler): osm_feed_* config flags"
```

---

### Task 4: wiring + runner integration

**Files:**
- Modify: `crawler/crawler/wiring.py`
- Modify: `crawler/crawler/runner.py`
- Test: `crawler/tests/test_wiring.py` (append), `crawler/tests/test_runner.py` (append)

**Interfaces:**
- Consumes: `OsmEnumerator`, `OsmDomainFeed` (Tasks 1-2), `BrandDomainCache`, `Config.osm_*` (Task 3).
- Produces: `Runner.__init__` gains `osm_feed=None`; `build_runner` builds and passes it.

- [ ] **Step 1: Write the failing tests**

```python
# append to crawler/tests/test_runner.py
class _StubOsm:
    def __init__(self, cands): self._cands = cands
    def candidates(self, known): return list(self._cands)


def test_runner_unions_osm_feed_candidates():
    src = {"id": 1, "type": "website", "name": "Silpo", "url_or_handle": "https://silpo.ua"}
    api = FakeApi([src])
    hv = _RecordingHarvester()
    osm_cand = SourceCandidate(name="Foo", type="website", url_or_handle="https://foo.ua")
    runner = Runner(api, {"website": FakeFetcher([])}, get_extractor("heuristic"), _rl(),
                    harvester=hv, osm_feed=_StubOsm([osm_cand]))
    runner.run()
    assert any(c.url_or_handle == "https://foo.ua" for c in hv.candidates)
```

```python
# append to crawler/tests/test_wiring.py
import json as _json_osm

from crawler.discovery.osm_feed import OsmDomainFeed


def test_build_runner_osm_feed_runs_without_network(tmp_path):
    # FRESH cache (far-future refreshed_at) so build_runner does NOT hit Overpass.
    opath = tmp_path / "osm_domains.json"
    opath.write_text(_json_osm.dumps({"version": 1, "refreshed_at": 9_999_999_999.0,
                                      "domains": {"Foo": "foo.ua"}, "cursor": 0}),
                     encoding="utf-8")
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=False, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={}, brand_feed_enabled=False,
        osm_feed_enabled=True, osm_domains_path=str(opath), osm_feed_refresh_hours=336)
    runner = build_runner(cfg)
    assert isinstance(runner._osm_feed, OsmDomainFeed)


def test_build_runner_osm_feed_disabled(tmp_path):
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=False, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={}, brand_feed_enabled=False, osm_feed_enabled=False)
    runner = build_runner(cfg)
    assert runner._osm_feed is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_runner.py tests/test_wiring.py -q -k "osm"`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'osm_feed'` (runner) / `AttributeError: ... '_osm_feed'` (wiring)

- [ ] **Step 3: Write minimal implementation**

In `crawler/crawler/runner.py`:

1. Extend `Runner.__init__` — append after `site_query_budget=5`:
```python
                 site_planner=None, site_state=None, site_query_budget=5,
                 osm_feed=None):
```
and store it:
```python
        self._osm_feed = osm_feed
```

2. In `run()`, inside `if self._harvester is not None:`, after the `brand_feed` candidates line (before the site-query block):
```python
                if self._osm_feed is not None:
                    candidates += self._osm_feed.candidates(known)
```

In `crawler/crawler/wiring.py`:

3. Add imports (with the other discovery imports):
```python
from crawler.discovery.osm_feed import OsmDomainFeed, OsmEnumerator
```

4. Add the builder near `_build_brand_feed`:
```python
def _build_osm_feed(config):
    cache = BrandDomainCache.load(config.osm_domains_path)
    if cache.is_stale(config.osm_feed_refresh_hours * 3600):
        try:
            domains = OsmEnumerator(
                overpass_url=config.overpass_url, timeout=config.request_timeout,
                min_pois=config.osm_min_pois,
                max_domains=config.osm_feed_max_domains).enumerate()
            if domains:
                cache.replace(domains)
        except Exception as exc:  # noqa: BLE001 — refresh best-effort; feed uses cache
            log.warning("osm-domain enumeration failed: %s", exc)
    return OsmDomainFeed(cache, per_pass=config.osm_feed_per_pass)
```

5. In `build_runner`, where `brand_feed` is built (`if config.brand_feed_enabled: brand_feed = _build_brand_feed(config)`), add right after it:
```python
    osm_feed = None
    if config.osm_feed_enabled:
        osm_feed = _build_osm_feed(config)
```

6. Pass it to the `Runner(...)` call (add kwarg):
```python
                  site_planner=site_planner, site_state=site_state,
                  site_query_budget=config.site_query_budget,
                  osm_feed=osm_feed)
```

- [ ] **Step 4: Run tests to verify they pass, then the full suite**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_runner.py tests/test_wiring.py -q`
Expected: PASS (all, including the 3 new)

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — 381 baseline + new tests, all green.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/runner.py crawler/crawler/wiring.py crawler/tests/test_runner.py crawler/tests/test_wiring.py
git commit -m "feat(crawler): wire OSM domain feed into Runner (gated osm_feed_enabled)"
```

---

## Final verification (after all tasks)

- [ ] Full suite green from `crawler/`: `./.venv/Scripts/python.exe -m pytest -q`
- [ ] Request opus whole-branch review (superpowers:requesting-code-review) before merge.
- [ ] Merge to `main` (--no-ff), delete branch, push, update `docs/RESUME.md` + memory.

## Self-review notes (traceability to spec)

- Spec §1 `OsmEnumerator` → Task 1; `OsmDomainFeed` → Task 2. §2 cache reuse → Task 2 (BrandDomainCache). §3 wiring `_build_osm_feed` → Task 4. §4 runner union → Task 4. §5 config → Task 3.
- Byte-eq off (`osm_feed_enabled=False`) → `test_build_runner_osm_feed_disabled`.
- Noise filters (min_pois, dedup, cap, blocklist, website/contact fallback) → Task 1 tests.
- Recall-safety (candidates only, moderation downstream) → structural: OSM candidates flow through the same harvester/attribution/moderation as brand_feed; no new offer path.
