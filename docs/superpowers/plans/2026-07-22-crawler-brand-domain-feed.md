# Crawler Brand→Domain Feed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give discovery a DDG-independent source of website candidates by resolving a curated set of brands to official domains via a rare, gated OSM/Wikidata refresh, caching them, and feeding those domains as `website` candidates into the existing harvester every pass.

**Architecture:** One new curated module `discovery/brand_feed.py` (curated seeds + `BrandResolver` + `BrandDomainCache` + `refresh_brand_domains` + `BrandFeed`). The refresh runs inline at pass start in `build_runner`, best-effort and gated on cache staleness; every pass otherwise reads the cache offline. The harvester gate is decoupled so the feed runs independently of `active_discovery`, and `Runner` unions brand candidates with the DDG-derived candidates before harvest.

**Tech Stack:** Python crawler; curated Python dict/tuples + `re`/`urllib` (same pattern as `query_grid.py`/`geo.py`); `httpx` for the rare refresh (injected for tests); tests `cd crawler && ./.venv/Scripts/python.exe -m pytest -q` (no network, no DB).

## Global Constraints

- **Scope: crawler logic only.** No DB schema, backend endpoints, admin/public UI, or LLM.
- **Curated brand set = `query_grid.BRANDS`.** `BRAND_SEEDS` keys MUST equal `set(query_grid.BRANDS)` (all 48). Each seed = `(wikidata_qid | None, fallback_domain)`; fallback domain is required and non-empty.
- **Network only in the refresh path**, best-effort: every resolver failure returns `None`; the refresh substitutes the curated fallback domain; a dead network at pass start never crashes or blocks the pass.
- **`active_discovery` default stays `False`** (unchanged). `brand_feed_enabled` defaults `True`, independent of `active_discovery`. Harvester is built when `(active_discovery-derived discovery is not None) OR (brand_feed is not None)`.
- **`brand_feed_refresh_hours` default = 336** (14 days). **`brand_domains_path` default = `/data/brand_domains.json`** (beside `search_state.json`).
- **Extraction/attribution downstream is untouched** — brand domains are just another candidate source into the existing harvester.
- **Cache round-trips through `brand_domains.json`** (process = pass), atomic writes like `SearchState._save`.

---

### Task 1: Curated brand seeds (`BRAND_SEEDS`)

**Files:**
- Create: `crawler/crawler/discovery/brand_feed.py`
- Test: `crawler/tests/test_brand_feed.py`

**Interfaces:**
- Consumes: `crawler.discovery.query_grid.BRANDS` (existing 48-brand tuple).
- Produces: `BRAND_SEEDS: dict[str, tuple[str | None, str]]` — `brand -> (wikidata_qid | None, fallback_domain)`.

- [ ] **Step 1: Write the failing tests**

Create `crawler/tests/test_brand_feed.py`:

```python
from crawler.discovery.brand_feed import BRAND_SEEDS
from crawler.discovery.query_grid import BRANDS


def test_brand_seeds_cover_exactly_the_brand_set():
    assert set(BRAND_SEEDS) == set(BRANDS)


def test_brand_seeds_have_bare_nonempty_fallback_domains():
    for brand, (qid, domain) in BRAND_SEEDS.items():
        assert domain and domain.strip(), brand
        assert " " not in domain and "/" not in domain, brand   # bare host, no scheme/path
        assert qid is None or qid.startswith("Q"), brand
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_brand_feed.py -q`
Expected: FAIL — `crawler.discovery.brand_feed` does not exist yet.

- [ ] **Step 3: Create the module with the curated seeds**

Create `crawler/crawler/discovery/brand_feed.py`:

```python
"""Offline curated brand→domain feed: resolve known brands to official domains via a
rare OSM/Wikidata refresh, cache them, and emit website SourceCandidates each pass.

Curated core (same technique as query_grid.py/geo.py): the brand set IS
query_grid.BRANDS; BRAND_SEEDS adds an optional Wikidata QID (fast-path hint) and a
required fallback domain per brand. The network (Wikidata/Overpass) is touched only
during refresh; passes read the cache offline."""

from crawler.discovery.query_grid import BRANDS  # noqa: F401 — referenced by the seeds invariant

# brand -> (wikidata_qid | None, fallback_domain)
# Fallback domains are best-effort BOOTSTRAP values: they seed the feed before any
# successful refresh and are overwritten by authoritative Wikidata/Overpass data on
# refresh. QID is an optional hint; when None the resolver discovers the brand's
# wikidata id / website via Overpass at refresh time.
BRAND_SEEDS: dict[str, tuple[str | None, str]] = {
    "Rozetka": (None, "rozetka.com.ua"),
    "Comfy": (None, "comfy.ua"),
    "Фокстрот": (None, "foxtrot.com.ua"),
    "Епіцентр": (None, "epicentrk.ua"),
    "Нова Лінія": (None, "novalinia.ua"),
    "JYSK": (None, "jysk.ua"),
    "EVA": (None, "eva.ua"),
    "Prostor": (None, "prostor.ua"),
    "Аврора": (None, "aurora.ua"),
    "Копійочка": (None, "kopiyochka.ua"),
    "Сільпо": (None, "silpo.ua"),
    "АТБ": (None, "atbmarket.com"),
    "Novus": (None, "novus.online"),
    "VARUS": (None, "varus.ua"),
    "Metro": (None, "metro.ua"),
    "OKKO": (None, "okko.ua"),
    "WOG": (None, "wog.ua"),
    "UPG": (None, "upg.ua"),
    "SOCAR": (None, "socar.ua"),
    "БРСМ": (None, "brsm-nafta.com"),
    "KLO": (None, "klo.ua"),
    "Parallel": (None, "parallel.ua"),
    "Подорожник": (None, "podorozhnyk.ua"),
    "АНЦ": (None, "anc.ua"),
    "Бажаємо здоров'я": (None, "apteka-bz.com.ua"),
    "Аптека Доброго Дня": (None, "add.ua"),
    "Алло": (None, "allo.ua"),
    "Цитрус": (None, "ctrs.com.ua"),
    "MOYO": (None, "moyo.ua"),
    "Brain": (None, "brain.com.ua"),
    "Eldorado": (None, "eldorado.ua"),
    "INTERTOP": (None, "intertop.ua"),
    "Colin's": (None, "colins.ua"),
    "LC Waikiki": (None, "lcwaikiki.ua"),
    "Adidas": (None, "adidas.ua"),
    "Puma": (None, "ua.puma.com"),
    "New Balance": (None, "newbalance.ua"),
    "Megasport": (None, "megasport.ua"),
    "ПриватБанк": (None, "privatbank.ua"),
    "monobank": (None, "monobank.ua"),
    "Ощадбанк": (None, "oschadbank.ua"),
    "ПУМБ": (None, "pumb.ua"),
    "Sense Bank": (None, "sensebank.com.ua"),
    "Райффайзен Банк": (None, "raiffeisen.ua"),
    "Нова пошта": (None, "novaposhta.ua"),
    "Київстар": (None, "kyivstar.ua"),
    "Vodafone": (None, "vodafone.ua"),
    "lifecell": (None, "lifecell.ua"),
}
```

- [ ] **Step 4: Run the tests**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_brand_feed.py -q`
Expected: PASS (2 tests). If `test_brand_seeds_cover_exactly_the_brand_set` fails, the seed keys drifted from `query_grid.BRANDS` — reconcile the dict against that tuple (do not edit `BRANDS`).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/brand_feed.py crawler/tests/test_brand_feed.py
git commit -m "feat(crawler): curated brand→domain seeds (brand feed)"
```

---

### Task 2: Persisted `BrandDomainCache`

**Files:**
- Modify: `crawler/crawler/discovery/brand_feed.py`
- Test: `crawler/tests/test_brand_feed.py`

**Interfaces:**
- Produces: `class BrandDomainCache` with `load(path, clock=time.time) -> BrandDomainCache` (classmethod), `is_stale(ttl_seconds: float) -> bool`, `domains() -> dict[str, str]`, `replace(domains: dict[str, str]) -> None` (persists atomically, stamps `refreshed_at`).

- [ ] **Step 1: Write the failing tests**

Append to `crawler/tests/test_brand_feed.py`:

```python
from crawler.discovery.brand_feed import BrandDomainCache


def test_cache_defaults_empty_and_stale(tmp_path):
    c = BrandDomainCache.load(str(tmp_path / "b.json"))
    assert c.domains() == {}
    assert c.is_stale(3600) is True


def test_cache_replace_persists_and_reloads(tmp_path):
    path = str(tmp_path / "b.json")
    BrandDomainCache.load(path, clock=lambda: 1000.0).replace({"OKKO": "okko.ua"})
    assert BrandDomainCache.load(path).domains() == {"OKKO": "okko.ua"}


def test_cache_freshness_gate(tmp_path):
    now = {"t": 1000.0}
    c = BrandDomainCache.load(str(tmp_path / "b.json"), clock=lambda: now["t"])
    c.replace({"OKKO": "okko.ua"})
    assert c.is_stale(3600) is False        # just refreshed
    now["t"] = 1000.0 + 3600
    assert c.is_stale(3600) is True         # ttl elapsed


def test_cache_tolerates_corrupt_file(tmp_path):
    path = tmp_path / "b.json"
    path.write_text("{ not json", encoding="utf-8")
    assert BrandDomainCache.load(str(path)).domains() == {}
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_brand_feed.py -q`
Expected: FAIL — `BrandDomainCache` not defined.

- [ ] **Step 3: Add the cache**

In `crawler/crawler/discovery/brand_feed.py`, add the stdlib imports **immediately after the module docstring and before** the existing `from crawler.discovery.query_grid import BRANDS` line (imports must follow the docstring, never precede it), then add the module logger just after that first-party import. The head of the file becomes:

```python
"""<existing module docstring stays unchanged>"""

import copy
import json
import logging
import os
import time

from crawler.discovery.query_grid import BRANDS  # noqa: F401 — referenced by the seeds invariant

log = logging.getLogger(__name__)
```

Then append to the module (after `BRAND_SEEDS`):

```python
_EMPTY_CACHE = {"version": 1, "refreshed_at": 0.0, "domains": {}}


class BrandDomainCache:
    """Persistent JSON brand→domain map with a refresh-freshness gate. Atomic writes."""

    def __init__(self, path: str, data: dict | None = None, clock=time.time):
        self._path = path
        self._clock = clock
        self._data = data if data is not None else json.loads(json.dumps(_EMPTY_CACHE))

    @classmethod
    def load(cls, path: str, clock=time.time) -> "BrandDomainCache":
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("brand cache must be a JSON object")
            for k, default in _EMPTY_CACHE.items():
                data.setdefault(k, copy.deepcopy(default))
        except (OSError, ValueError) as exc:
            log.warning("brand cache load failed (%s); starting clean", exc)
            data = None
        return cls(path, data=data, clock=clock)

    def is_stale(self, ttl_seconds: float) -> bool:
        return self._clock() - float(self._data.get("refreshed_at", 0.0)) >= ttl_seconds

    def domains(self) -> dict[str, str]:
        return dict(self._data.get("domains", {}))

    def replace(self, domains: dict[str, str]) -> None:
        self._data["domains"] = dict(domains)
        self._data["refreshed_at"] = self._clock()
        self._save()

    def _save(self) -> None:
        directory = os.path.dirname(self._path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = f"{self._path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False)
        os.replace(tmp, self._path)
```

- [ ] **Step 4: Run the tests**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_brand_feed.py -q`
Expected: PASS (Task 1 + Task 2 tests).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/brand_feed.py crawler/tests/test_brand_feed.py
git commit -m "feat(crawler): persisted BrandDomainCache with freshness gate"
```

---

### Task 3: `BrandResolver` (Wikidata P856 → Overpass website)

**Files:**
- Modify: `crawler/crawler/discovery/brand_feed.py`
- Test: `crawler/tests/test_brand_feed.py`

**Interfaces:**
- Produces: `_host(url: str) -> str | None` (bare host: scheme/`www.`/port/path stripped, lowercased); `class BrandResolver` with `__init__(self, client_factory=None, overpass_url=DEFAULT_OVERPASS_URL, wikidata_url=DEFAULT_WIKIDATA_URL, timeout=25.0, sleep=time.sleep, min_delay=1.0)` and `resolve(self, brand: str, qid: str | None = None) -> str | None`. Every failure path returns `None`.

- [ ] **Step 1: Write the failing tests**

Append to `crawler/tests/test_brand_feed.py`:

```python
from crawler.discovery.brand_feed import BrandResolver, _host


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, get_payload=None, post_payload=None):
        self._get, self._post = get_payload, post_payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url, params=None):
        return _FakeResp(self._get)

    def post(self, url, data=None):
        return _FakeResp(self._post)


def _resolver(get=None, post=None):
    return BrandResolver(client_factory=lambda: _FakeClient(get, post),
                         sleep=lambda s: None)


def test_host_normalizes_scheme_www_port_path():
    assert _host("https://www.Rozetka.com.ua/some/path") == "rozetka.com.ua"
    assert _host("okko.ua") == "okko.ua"
    assert _host("http://eva.ua:8080") == "eva.ua"
    assert _host("") is None


def test_resolve_uses_wikidata_p856_when_qid_present():
    payload = {"claims": {"P856": [
        {"mainsnak": {"datavalue": {"value": "https://okko.ua/"}}}]}}
    assert _resolver(get=payload).resolve("OKKO", "Q123") == "okko.ua"


def test_resolve_falls_back_to_overpass_website_aggregate():
    post = {"elements": [
        {"tags": {"website": "https://www.eva.ua/uk/"}},
        {"tags": {"contact:website": "http://eva.ua"}},
        {"tags": {"website": "https://other.example"}}]}
    assert _resolver(post=post).resolve("EVA", None) == "eva.ua"


def test_resolve_uses_overpass_brand_wikidata_then_p856():
    post = {"elements": [{"tags": {"brand:wikidata": "Q42"}}]}
    get = {"claims": {"P856": [
        {"mainsnak": {"datavalue": {"value": "https://wog.ua"}}}]}}
    assert _resolver(get=get, post=post).resolve("WOG", None) == "wog.ua"


def test_resolve_returns_none_on_failure():
    class _Boom:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            raise RuntimeError("net down")

        def post(self, *a, **k):
            raise RuntimeError("net down")

    r = BrandResolver(client_factory=lambda: _Boom(), sleep=lambda s: None)
    assert r.resolve("X", "Q1") is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_brand_feed.py -q`
Expected: FAIL — `BrandResolver` / `_host` not defined.

- [ ] **Step 3: Add `_host` and `BrandResolver`**

Add `from collections import Counter` and `from urllib.parse import urlparse` to the stdlib imports at the top of `crawler/crawler/discovery/brand_feed.py`, and `import httpx` below them. Then append to the module:

```python
DEFAULT_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
DEFAULT_WIKIDATA_URL = "https://www.wikidata.org/w/api.php"
_RESOLVER_UA = "UBDCrawler/0.1 (+https://ubd.example; brand-domain resolver)"


def _host(url: str) -> str | None:
    """Bare registrable host: strip scheme, userinfo, port, path, and a leading www."""
    if not url or not url.strip():
        return None
    raw = url.strip()
    if "//" not in raw:
        raw = "//" + raw
    netloc = urlparse(raw).netloc.lower()
    netloc = netloc.split("@")[-1].split(":")[0]
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc or None


class BrandResolver:
    """Best-effort brand→domain resolution via Wikidata P856 and Overpass website tags.
    HTTP is injected for testability; every failure path returns None."""

    def __init__(self, client_factory=None, overpass_url=DEFAULT_OVERPASS_URL,
                 wikidata_url=DEFAULT_WIKIDATA_URL, timeout=25.0,
                 sleep=time.sleep, min_delay=1.0):
        self._client_factory = client_factory or (
            lambda: httpx.Client(timeout=timeout, headers={"User-Agent": _RESOLVER_UA}))
        self._overpass = overpass_url
        self._wikidata = wikidata_url
        self._sleep = sleep
        self._delay = min_delay

    def resolve(self, brand: str, qid: str | None = None) -> str | None:
        if qid:
            host = self._wikidata_site(qid)
            if host:
                return host
        tags = self._overpass_tags(brand)
        if tags.get("wikidata"):
            host = self._wikidata_site(tags["wikidata"])
            if host:
                return host
        hosts = [h for h in (_host(w) for w in tags.get("websites", [])) if h]
        if hosts:
            return Counter(hosts).most_common(1)[0][0]
        return None

    def _wikidata_site(self, qid: str) -> str | None:
        try:
            if self._delay:
                self._sleep(self._delay)
            with self._client_factory() as client:
                resp = client.get(self._wikidata, params={
                    "action": "wbgetclaims", "entity": qid,
                    "property": "P856", "format": "json"})
                resp.raise_for_status()
                data = resp.json()
            for claim in data.get("claims", {}).get("P856", []):
                value = (claim.get("mainsnak", {}).get("datavalue", {}) or {}).get("value")
                host = _host(value) if isinstance(value, str) else None
                if host:
                    return host
        except Exception as exc:  # noqa: BLE001 — resolution is best-effort
            log.warning("wikidata P856 failed for %s: %s", qid, exc)
        return None

    def _overpass_tags(self, brand: str) -> dict:
        query = f'[out:json][timeout:25];nwr["brand"="{brand}"];out tags 50;'
        try:
            if self._delay:
                self._sleep(self._delay)
            with self._client_factory() as client:
                resp = client.post(self._overpass, data={"data": query})
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001 — resolution is best-effort
            log.warning("overpass failed for %r: %s", brand, exc)
            return {}
        wikidata = None
        websites: list[str] = []
        for el in data.get("elements", []):
            tags = el.get("tags", {})
            wikidata = wikidata or tags.get("brand:wikidata") or tags.get("wikidata")
            for key in ("website", "contact:website"):
                if tags.get(key):
                    websites.append(tags[key])
        return {"wikidata": wikidata, "websites": websites}
```

- [ ] **Step 4: Run the tests**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_brand_feed.py -q`
Expected: PASS (Task 1-3 tests).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/brand_feed.py crawler/tests/test_brand_feed.py
git commit -m "feat(crawler): BrandResolver (Wikidata P856 + Overpass website fallback)"
```

---

### Task 4: `refresh_brand_domains` + `BrandFeed`

**Files:**
- Modify: `crawler/crawler/discovery/brand_feed.py`
- Test: `crawler/tests/test_brand_feed.py`

**Interfaces:**
- Consumes: `BRAND_SEEDS` (Task 1), `BrandDomainCache` (Task 2), a resolver with `resolve(brand, qid)` (Task 3), `crawler.discovery.passive.normalize_ref`, `crawler.models.SourceCandidate`.
- Produces: `refresh_brand_domains(cache, resolver, seeds=BRAND_SEEDS) -> None`; `class BrandFeed` with `__init__(self, cache, seeds=BRAND_SEEDS)` and `candidates(self, known: set[str]) -> list[SourceCandidate]`.

- [ ] **Step 1: Write the failing tests**

Append to `crawler/tests/test_brand_feed.py`:

```python
from crawler.discovery.brand_feed import BrandFeed, refresh_brand_domains
from crawler.discovery.passive import normalize_ref


class _FakeResolver:
    def __init__(self, mapping):
        self._m = mapping

    def resolve(self, brand, qid):
        v = self._m.get(brand)
        if isinstance(v, Exception):
            raise v
        return v


def test_refresh_prefers_resolved_then_curated_fallback(tmp_path):
    seeds = {"OKKO": (None, "okko.ua"),
             "EVA": (None, "eva.ua"),          # resolver returns None -> fallback
             "WOG": (None, "wog.ua")}          # resolver raises -> fallback
    resolver = _FakeResolver({"OKKO": "okko.com.ua", "EVA": None,
                              "WOG": RuntimeError("boom")})
    cache = BrandDomainCache.load(str(tmp_path / "b.json"))
    refresh_brand_domains(cache, resolver, seeds)
    assert cache.domains() == {"OKKO": "okko.com.ua", "EVA": "eva.ua", "WOG": "wog.ua"}


def test_brand_feed_emits_website_candidates_using_cache_then_fallback(tmp_path):
    seeds = {"OKKO": (None, "okko.ua"), "EVA": (None, "eva.ua")}
    cache = BrandDomainCache.load(str(tmp_path / "b.json"))
    cache.replace({"OKKO": "okko.com.ua"})     # EVA absent -> falls back to seed domain
    cands = {c.name: c for c in BrandFeed(cache, seeds).candidates(known=set())}
    assert cands["OKKO"].type == "website"
    assert cands["OKKO"].url_or_handle == "https://okko.com.ua"
    assert cands["OKKO"].discovery_note == "brand-feed:OKKO"
    assert cands["EVA"].url_or_handle == "https://eva.ua"


def test_brand_feed_skips_known_refs(tmp_path):
    seeds = {"OKKO": (None, "okko.ua")}
    cache = BrandDomainCache.load(str(tmp_path / "b.json"))
    known = {normalize_ref("website", "https://okko.ua")}
    assert BrandFeed(cache, seeds).candidates(known) == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_brand_feed.py -q`
Expected: FAIL — `refresh_brand_domains` / `BrandFeed` not defined.

- [ ] **Step 3: Add the refresh function and the feed**

Add these imports near the top of `crawler/crawler/discovery/brand_feed.py` (below the existing `from crawler.discovery.query_grid import BRANDS` line):

```python
from crawler.discovery.passive import normalize_ref
from crawler.models import SourceCandidate
```

Then append to the module:

```python
def refresh_brand_domains(cache: "BrandDomainCache", resolver, seeds=BRAND_SEEDS) -> None:
    """Resolve every seed brand to a domain (best-effort), falling back to the curated
    seed domain, and persist the result to the cache."""
    resolved: dict[str, str] = {}
    for brand, (qid, fallback) in seeds.items():
        domain = None
        try:
            domain = resolver.resolve(brand, qid)
        except Exception as exc:  # noqa: BLE001 — one brand must not kill the batch
            log.warning("brand resolve failed for %s: %s", brand, exc)
            domain = None
        resolved[brand] = domain or fallback
    cache.replace(resolved)


class BrandFeed:
    """Offline emitter: one website SourceCandidate per brand from the cache/fallback."""

    def __init__(self, cache: "BrandDomainCache", seeds=BRAND_SEEDS):
        self._cache = cache
        self._seeds = seeds

    def candidates(self, known: set[str]) -> list[SourceCandidate]:
        domains = self._cache.domains()
        out: list[SourceCandidate] = []
        for brand, (qid, fallback) in self._seeds.items():
            domain = domains.get(brand) or fallback
            url = f"https://{domain}"
            if normalize_ref("website", url) in known:
                continue
            out.append(SourceCandidate(
                name=brand, type="website", url_or_handle=url,
                discovered_from_source_id=None,
                discovery_note=f"brand-feed:{brand}"))
        return out
```

- [ ] **Step 4: Run the tests**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_brand_feed.py -q`
Expected: PASS (Task 1-4 tests).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/brand_feed.py crawler/tests/test_brand_feed.py
git commit -m "feat(crawler): refresh_brand_domains + BrandFeed website candidates"
```

---

### Task 5: Config knobs

**Files:**
- Modify: `crawler/crawler/config.py`
- Test: `crawler/tests/test_config.py`

**Interfaces:**
- Produces: `Config.brand_feed_enabled: bool` (env `BRAND_FEED_ENABLED`, default `True`), `Config.brand_feed_refresh_hours: int` (env `BRAND_FEED_REFRESH_HOURS`, default `336`), `Config.brand_domains_path: str` (env `BRAND_DOMAINS_PATH`, default `/data/brand_domains.json`), `Config.overpass_url: str` (env `OVERPASS_URL`), `Config.wikidata_url: str` (env `WIKIDATA_URL`).

- [ ] **Step 1: Write the failing tests**

Append to `crawler/tests/test_config.py`:

```python
def test_brand_feed_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)      # no .env -> defaults apply
    cfg = load_config()
    assert cfg.brand_feed_enabled is True
    assert cfg.brand_feed_refresh_hours == 336
    assert cfg.brand_domains_path == "/data/brand_domains.json"
    assert cfg.overpass_url == "https://overpass-api.de/api/interpreter"
    assert cfg.wikidata_url == "https://www.wikidata.org/w/api.php"


def test_brand_feed_env_overrides(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BRAND_FEED_ENABLED", "false")
    monkeypatch.setenv("BRAND_FEED_REFRESH_HOURS", "48")
    cfg = load_config()
    assert cfg.brand_feed_enabled is False
    assert cfg.brand_feed_refresh_hours == 48
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_config.py -q`
Expected: FAIL — `Config` has no `brand_feed_enabled`.

- [ ] **Step 3: Add the settings in three places**

In `crawler/crawler/config.py`:

In `_RawSettings`, after `freshness_ttl_days: int = 30`:
```python
    brand_feed_enabled: bool = True
    brand_feed_refresh_hours: int = 336
    brand_domains_path: str = "/data/brand_domains.json"
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    wikidata_url: str = "https://www.wikidata.org/w/api.php"
```

In the `Config` dataclass, after `freshness_ttl_days: int = 30`:
```python
    brand_feed_enabled: bool = True
    brand_feed_refresh_hours: int = 336
    brand_domains_path: str = "/data/brand_domains.json"
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    wikidata_url: str = "https://www.wikidata.org/w/api.php"
```

In `load_config()`'s `Config(...)` call, after `freshness_ttl_days=s.freshness_ttl_days,`:
```python
        brand_feed_enabled=s.brand_feed_enabled,
        brand_feed_refresh_hours=s.brand_feed_refresh_hours,
        brand_domains_path=s.brand_domains_path,
        overpass_url=s.overpass_url,
        wikidata_url=s.wikidata_url,
```

- [ ] **Step 4: Run the tests**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_config.py -q`
Expected: PASS (new + existing config tests).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/config.py crawler/tests/test_config.py
git commit -m "feat(crawler): brand-feed config knobs"
```

---

### Task 6: Wire the brand feed into discovery (decoupled gate)

**Files:**
- Modify: `crawler/crawler/runner.py` (accept `brand_feed`, union candidates)
- Modify: `crawler/crawler/wiring.py` (build feed + refresh-on-stale, decouple harvester gate)
- Test: `crawler/tests/test_wiring.py`

**Interfaces:**
- Consumes: `BRAND_SEEDS`, `BrandDomainCache`, `BrandFeed`, `BrandResolver`, `refresh_brand_domains` (Tasks 1-4); `Config.brand_feed_enabled`/`brand_feed_refresh_hours`/`brand_domains_path`/`overpass_url`/`wikidata_url` (Task 5).
- Produces: `Runner.__init__(..., brand_feed=None)`; `Runner.run` unions `brand_feed.candidates(known)` with the DDG discovery candidates before harvest. `build_runner` builds a `BrandFeed` (refreshing the cache when stale) when `config.brand_feed_enabled`, and builds the harvester when `(discovery is not None or brand_feed is not None) and config.active_fetch_budget`.

- [ ] **Step 1: Write the failing tests**

First, update the TWO existing tests in `crawler/tests/test_wiring.py` so they do not trigger the (now default-on) brand feed. In `test_build_runner_wires_all_platforms`, add `brand_feed_enabled=False,` to the `Config(...)` kwargs (after `proxies={},`). In `test_build_runner_rotates_query_grid_and_unions_pins`, add `brand_feed_enabled=False,` to its `Config(...)` kwargs (after `search_queries_per_pass=3,`).

Then append the new tests to `crawler/tests/test_wiring.py`:

```python
import json

from crawler.discovery.brand_feed import BrandFeed
from crawler.runner import Runner
from crawler.models import SourceCandidate


def test_build_runner_brand_feed_runs_without_ddg(tmp_path):
    # Pre-write a FRESH cache (far-future refreshed_at) so build_runner does NOT refresh
    # (no network), and points brand_domains_path at tmp (not /data).
    bpath = tmp_path / "brand_domains.json"
    bpath.write_text(json.dumps({"version": 1, "refreshed_at": 9_999_999_999.0,
                                 "domains": {"OKKO": "okko.ua"}}), encoding="utf-8")
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=False, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={},
        brand_feed_enabled=True,
        brand_domains_path=str(bpath),
        brand_feed_refresh_hours=336,
        active_fetch_budget=20,
    )
    runner = build_runner(cfg)
    assert runner._discovery is None
    assert isinstance(runner._brand_feed, BrandFeed)
    assert runner._harvester is not None


def test_runner_unions_brand_feed_and_ddg_candidates():
    class _Api:
        def list_target_categories(self):
            return []

        def list_offer_categories(self):
            return []

        def list_sources(self, is_active=True):
            return []

        def expire_stale(self, days):
            return {"expired": 0}

    class _Discovery:
        def run(self, keywords, known):
            return [SourceCandidate(name="ddg", type="website",
                                    url_or_handle="https://ddg.example")]

    class _Feed:
        def candidates(self, known):
            return [SourceCandidate(name="OKKO", type="website",
                                    url_or_handle="https://okko.ua")]

    class _Harvester:
        def __init__(self):
            self.seen = None

        def harvest(self, candidates, cats, known, summary):
            self.seen = list(candidates)

    harv = _Harvester()
    runner = Runner(_Api(), {}, extractor=None, rate_limiter=None,
                    discovery=_Discovery(), keywords=["kw"], harvester=harv,
                    brand_feed=_Feed())
    runner.run()
    assert {c.name for c in harv.seen} == {"ddg", "OKKO"}
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_wiring.py -q`
Expected: FAIL — `Runner.__init__` has no `brand_feed`; `build_runner` does not build a `BrandFeed`.

- [ ] **Step 3: Extend `Runner`**

In `crawler/crawler/runner.py`, add the `brand_feed` parameter to `Runner.__init__` (after `harvester=None`) and store it:

```python
    def __init__(self, api_client, fetchers: dict, extractor, rate_limiter,
                 discovery=None, keywords=None, harvester=None, brand_feed=None,
                 freshness_ttl_days=30):
        self._api = api_client
        self._fetchers = fetchers
        self._extractor = extractor
        self._rl = rate_limiter
        self._discovery = discovery
        self._keywords = keywords or []
        self._harvester = harvester
        self._brand_feed = brand_feed
        self._freshness_ttl_days = freshness_ttl_days
```

Then replace the discovery block in `Runner.run` (currently):

```python
        if self._discovery is not None and self._keywords and self._harvester is not None:
            try:
                candidates = self._discovery.run(self._keywords, known)
                self._harvester.harvest(candidates, cats, known, summary)
            except Exception as exc:  # noqa: BLE001 — discovery must not crash the pass
                summary["errors"] += 1
                log.warning("active discovery failed: %s", exc)
```

with:

```python
        if self._harvester is not None:
            try:
                candidates = []
                if self._discovery is not None and self._keywords:
                    candidates += self._discovery.run(self._keywords, known)
                if self._brand_feed is not None:
                    candidates += self._brand_feed.candidates(known)
                if candidates:
                    self._harvester.harvest(candidates, cats, known, summary)
            except Exception as exc:  # noqa: BLE001 — discovery must not crash the pass
                summary["errors"] += 1
                log.warning("active discovery failed: %s", exc)
```

- [ ] **Step 4: Wire the feed in `build_runner`**

In `crawler/crawler/wiring.py`, add a module logger and the brand-feed imports at the top (next to the other `from crawler.discovery...` imports):

```python
import logging

from crawler.discovery.brand_feed import (
    BRAND_SEEDS, BrandDomainCache, BrandFeed, BrandResolver, refresh_brand_domains)

log = logging.getLogger(__name__)
```

Add this helper above `build_runner`:

```python
def _build_brand_feed(config):
    cache = BrandDomainCache.load(config.brand_domains_path)
    if cache.is_stale(config.brand_feed_refresh_hours * 3600):
        try:
            resolver = BrandResolver(overpass_url=config.overpass_url,
                                     wikidata_url=config.wikidata_url,
                                     timeout=config.request_timeout)
            refresh_brand_domains(cache, resolver, BRAND_SEEDS)
        except Exception as exc:  # noqa: BLE001 — refresh is best-effort; feed uses cache/fallbacks
            log.warning("brand-domain refresh failed: %s", exc)
    return BrandFeed(cache, BRAND_SEEDS)
```

Then replace the discovery/harvester block in `build_runner` (currently):

```python
    discovery = None
    harvester = None
    keywords = config.search_keywords
    if config.active_discovery:
        state = SearchState.load(config.search_state_path)
        batch, new_cursor = QueryGrid().next_batch(
            config.search_queries_per_pass, state.grid_cursor)
        state.set_grid_cursor(new_cursor)
        keywords = merge_queries(batch, config.search_keywords)
        provider = build_search_provider(config, state=state)
        if provider is not None:
            budget = config.search_budget or len(keywords)
            discovery = ActiveDiscovery(budget=budget, search_provider=provider)
            if config.active_fetch_budget:
                harvester = ActiveHarvester(api, fetchers, extractor, rate_limiter,
                                            fetch_budget=config.active_fetch_budget)
    return Runner(api, fetchers, extractor, rate_limiter,
                  discovery=discovery, keywords=keywords, harvester=harvester,
                  freshness_ttl_days=config.freshness_ttl_days)
```

with:

```python
    discovery = None
    harvester = None
    brand_feed = None
    keywords = config.search_keywords
    if config.active_discovery:
        state = SearchState.load(config.search_state_path)
        batch, new_cursor = QueryGrid().next_batch(
            config.search_queries_per_pass, state.grid_cursor)
        state.set_grid_cursor(new_cursor)
        keywords = merge_queries(batch, config.search_keywords)
        provider = build_search_provider(config, state=state)
        if provider is not None:
            budget = config.search_budget or len(keywords)
            discovery = ActiveDiscovery(budget=budget, search_provider=provider)
    if config.brand_feed_enabled:
        brand_feed = _build_brand_feed(config)
    if (discovery is not None or brand_feed is not None) and config.active_fetch_budget:
        harvester = ActiveHarvester(api, fetchers, extractor, rate_limiter,
                                    fetch_budget=config.active_fetch_budget)
    return Runner(api, fetchers, extractor, rate_limiter,
                  discovery=discovery, keywords=keywords, harvester=harvester,
                  brand_feed=brand_feed, freshness_ttl_days=config.freshness_ttl_days)
```

- [ ] **Step 5: Run the tests**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_wiring.py tests/test_runner.py tests/test_runner_discovery.py -q`
Expected: PASS — new wiring/runner tests pass; existing runner tests still pass (the `brand_feed` param defaults to `None`, so prior `Runner(...)` calls are unaffected).

- [ ] **Step 6: Full suite + commit**

Run the whole crawler suite — everything green:
`cd crawler && ./.venv/Scripts/python.exe -m pytest -q`

```bash
git add crawler/crawler/runner.py crawler/crawler/wiring.py crawler/tests/test_wiring.py
git commit -m "feat(crawler): wire brand-domain feed into discovery (decoupled harvester gate)"
```

---

### Task 7: Brand-emission rotation (+ post-review cleanups)

**Context:** the harvester caps fetches at `active_fetch_budget` (default 20) per pass, but `BRAND_SEEDS` has 48 brands (and the curated set will grow). Without rotation the feed re-emits the same first-20 brands every pass (the harvester submits offers but never adds a brand homepage to `known`), so the tail is starved forever. This task makes `BrandFeed` emit a **rotating window** of brands, persisting a cursor in `brand_domains.json`, so all brands are covered over successive passes. Also folds in the trivial post-review cleanups.

**Files:**
- Modify: `crawler/crawler/discovery/brand_feed.py` (`BrandDomainCache` cursor; `BrandFeed` rotation)
- Modify: `crawler/crawler/config.py` (`brand_feed_per_pass`)
- Modify: `crawler/crawler/wiring.py` (pass `per_pass`)
- Modify: `crawler/crawler/runner.py` (log-string cleanup)
- Test: `crawler/tests/test_brand_feed.py`, `crawler/tests/test_config.py`, `crawler/tests/test_wiring.py`

**Interfaces:**
- Consumes: `BrandDomainCache`, `BrandFeed`, `BRAND_SEEDS`, `Config.brand_feed_per_pass`.
- Produces: `BrandDomainCache.cursor() -> int` + `set_cursor(value: int) -> None`; `BrandFeed(cache, seeds=BRAND_SEEDS, per_pass=20)` whose `candidates(known)` emits only the rotating window `[cursor : cursor+per_pass)` (wrapping) and advances+persists the cursor by the window size; `Config.brand_feed_per_pass: int` (env `BRAND_FEED_PER_PASS`, default 20).

- [ ] **Step 1: Write the failing tests**

Append to `crawler/tests/test_brand_feed.py`:

```python
def test_cache_cursor_defaults_zero_and_persists(tmp_path):
    path = str(tmp_path / "b.json")
    c = BrandDomainCache.load(path)
    assert c.cursor() == 0
    c.set_cursor(7)
    assert BrandDomainCache.load(path).cursor() == 7


def test_brand_feed_rotates_window_and_advances_cursor(tmp_path):
    seeds = {"A": (None, "a.ua"), "B": (None, "b.ua"),
             "C": (None, "c.ua"), "D": (None, "d.ua")}
    cache = BrandDomainCache.load(str(tmp_path / "b.json"))
    feed = BrandFeed(cache, seeds, per_pass=2)
    first = [c.name for c in feed.candidates(known=set())]
    second = [c.name for c in feed.candidates(known=set())]
    assert first == ["A", "B"]
    assert second == ["C", "D"]
    third = [c.name for c in feed.candidates(known=set())]
    assert third == ["A", "B"]                    # wrapped back to start


def test_brand_feed_full_sweep_covers_every_brand(tmp_path):
    seeds = {"A": (None, "a.ua"), "B": (None, "b.ua"),
             "C": (None, "c.ua"), "D": (None, "d.ua")}
    cache = BrandDomainCache.load(str(tmp_path / "b.json"))
    feed = BrandFeed(cache, seeds, per_pass=1)
    seen = []
    for _ in range(len(seeds)):
        seen += [c.name for c in feed.candidates(known=set())]
    assert sorted(seen) == ["A", "B", "C", "D"]   # each brand visited once per sweep
```

Append to `crawler/tests/test_config.py`:

```python
def test_brand_feed_per_pass_default(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert load_config().brand_feed_per_pass == 20


def test_brand_feed_per_pass_override(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BRAND_FEED_PER_PASS", "5")
    assert load_config().brand_feed_per_pass == 5
```

Also append the two cheap-win tests — to `crawler/tests/test_brand_feed.py`:

```python
def test_host_returns_none_for_none():
    assert _host(None) is None
```

and to `crawler/tests/test_wiring.py`:

```python
def test_runner_skips_harvest_when_no_candidates():
    class _Api:
        def list_target_categories(self):
            return []

        def list_offer_categories(self):
            return []

        def list_sources(self, is_active=True):
            return []

        def expire_stale(self, days):
            return {"expired": 0}

    class _EmptyDiscovery:
        def run(self, keywords, known):
            return []

    class _Harvester:
        def __init__(self):
            self.called = False

        def harvest(self, candidates, cats, known, summary):
            self.called = True

    harv = _Harvester()
    runner = Runner(_Api(), {}, extractor=None, rate_limiter=None,
                    discovery=_EmptyDiscovery(), keywords=["kw"], harvester=harv,
                    brand_feed=None)
    runner.run()
    assert harv.called is False
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_brand_feed.py tests/test_config.py tests/test_wiring.py -q`
Expected: FAIL — `BrandDomainCache.cursor`/`set_cursor` and `Config.brand_feed_per_pass` missing; `BrandFeed` emits all brands (no rotation).

- [ ] **Step 3: Add the cursor to `BrandDomainCache`**

In `crawler/crawler/discovery/brand_feed.py`, add `"cursor": 0` to `_EMPTY_CACHE`:

```python
_EMPTY_CACHE = {"version": 1, "refreshed_at": 0.0, "domains": {}, "cursor": 0}
```

Then, inside `BrandDomainCache` (e.g. right after the `domains` method), add:

```python
    def cursor(self) -> int:
        return int(self._data.get("cursor", 0))

    def set_cursor(self, value: int) -> None:
        self._data["cursor"] = int(value)
        self._save()
```

- [ ] **Step 4: Make `BrandFeed` rotate**

In `crawler/crawler/discovery/brand_feed.py`, replace the whole `BrandFeed` class with:

```python
class BrandFeed:
    """Offline emitter: a rotating window of website SourceCandidates from the
    cache/fallback. The window advances a persisted cursor each pass so every brand
    (including ones added as the curated set grows) is covered over successive passes."""

    def __init__(self, cache: "BrandDomainCache", seeds=BRAND_SEEDS, per_pass=20):
        self._cache = cache
        self._seeds = seeds
        self._per_pass = per_pass

    def candidates(self, known: set[str]) -> list[SourceCandidate]:
        brands = list(self._seeds)
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
            domain = domains.get(brand) or self._seeds[brand][1]
            url = f"https://{domain}"
            if normalize_ref("website", url) in known:
                continue
            out.append(SourceCandidate(
                name=brand, type="website", url_or_handle=url,
                discovered_from_source_id=None,
                discovery_note=f"brand-feed:{brand}"))
        return out
```

(The existing Task 4 `BrandFeed` tests use seed dicts of size ≤ 2 with the default `per_pass=20`, so `n == size` → the full set is still emitted and those tests keep passing.)

- [ ] **Step 5: Add the `brand_feed_per_pass` config knob (three spots)**

In `crawler/crawler/config.py`:

In `_RawSettings`, after `wikidata_url: str = "https://www.wikidata.org/w/api.php"`:
```python
    brand_feed_per_pass: int = 20
```

In the `Config` dataclass, after `wikidata_url: str = "https://www.wikidata.org/w/api.php"`:
```python
    brand_feed_per_pass: int = 20
```

In `load_config()`'s `Config(...)` call, after `wikidata_url=s.wikidata_url,`:
```python
        brand_feed_per_pass=s.brand_feed_per_pass,
```

- [ ] **Step 6: Pass `per_pass` from wiring, and clean up the runner log string**

In `crawler/crawler/wiring.py`, in `_build_brand_feed`, change the return line from `return BrandFeed(cache, BRAND_SEEDS)` to:

```python
    return BrandFeed(cache, BRAND_SEEDS, per_pass=config.brand_feed_per_pass)
```

In `crawler/crawler/runner.py`, in the discovery block's `except`, change the log message so it no longer misattributes brand-feed failures to DDG:

```python
                log.warning("active discovery / brand-feed harvest failed: %s", exc)
```

- [ ] **Step 7: Run the tests**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_brand_feed.py tests/test_config.py tests/test_wiring.py tests/test_runner.py tests/test_runner_discovery.py -q`
Expected: PASS — new rotation/config/cleanup tests pass; existing brand-feed/wiring/runner tests still pass.

- [ ] **Step 8: Full suite + commit**

Run the whole crawler suite — everything green:
`cd crawler && ./.venv/Scripts/python.exe -m pytest -q`

```bash
git add crawler/crawler/discovery/brand_feed.py crawler/crawler/config.py crawler/crawler/wiring.py crawler/crawler/runner.py crawler/tests/test_brand_feed.py crawler/tests/test_config.py crawler/tests/test_wiring.py
git commit -m "feat(crawler): rotate brand-feed emission window across passes (+review cleanups)"
```

---

## Notes for the implementer

- Each `python -m crawler run` is a **fresh process = one pass**, so the brand cache and its `refreshed_at` MUST round-trip through `brand_domains.json` — the refresh is gated on `is_stale` at pass start (`_build_brand_feed`).
- The refresh (`refresh_brand_domains` via `BrandResolver`) is the ONLY place that touches the network, and it is best-effort: a dead network leaves the last-known cache in place and the feed still emits the curated fallback domains. Never let a refresh failure crash or block the pass.
- Do NOT touch `active_discovery`'s default (`False`) or the DDG query-grid rotation — the brand feed is an independent, additive candidate source. The harvester is now gated on `(discovery or brand_feed)`, not on `active_discovery` alone.
- `BRAND_SEEDS` fallback domains are bootstrap-only and are overwritten by refresh; do not spend effort hand-verifying them beyond the shape asserted in Task 1.
```
