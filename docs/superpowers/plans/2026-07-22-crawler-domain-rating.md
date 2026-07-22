# Crawler domain-rating Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persistent crawler-side domain rating that remembers productive website domains, re-feeds them as DDG-independent candidates, prioritises budget toward them, evicts dead/noisy ones — and routes approved domains to the passive deep-walk while the active path skips them.

**Architecture:** Three new crawler-side units — `DomainRegistry` (JSON state with exp-decay score), `DomainFeed` (candidate emitter), plus host-level skip and registry recording wired into `ActiveHarvester`, and passive deep-walk wired into `Runner._crawl_source`. All state is crawler-side JSON (no backend changes). Everything is best-effort and gated so `domain_rating_enabled=False` is byte-equivalent to today.

**Tech Stack:** Python 3.11, pytest, stdlib `json`/`os`/`time`. Same patterns as `discovery/brand_feed.py` (`BrandDomainCache`) and `discovery/search_state.py` (`SearchState`).

## Global Constraints

- Run tests from `crawler/`: `./.venv/Scripts/python.exe -m pytest -q` (Windows). Baseline is **299 passing**; must stay green (grows with new tests).
- **Live moderation gate untouched.** Rating only decides who/what order we actively fetch. Every offer still goes to human moderation.
- **Deterministic extraction core untouched** (regex/lexicons). Rating is a layer around fetching, never inside `extract`.
- **Best-effort everywhere:** registry/feed/walk never raise up and never crash a pass.
- **Website-only.** Registry keyed by bare host; telegram/IG/FB out of scope.
- **`domain_rating_enabled=False` ⇒ byte-equivalent** to current behaviour (no record, no feed, no host-skip).
- **Single host function:** everywhere a bare host is derived (registry keys, `known_hosts`, feed emission), use `crawler.discovery.walker._host` so keys always match.
- **Backend untouched.** No schema/endpoint/migration.
- Atomic JSON writes: `tmp` file + `os.replace` (as `BrandDomainCache._save`).
- Commit after each task with the message shown in its final step.

---

### Task 1: DomainRegistry (state + score model)

**Files:**
- Create: `crawler/crawler/discovery/domain_registry.py`
- Test: `crawler/tests/test_domain_registry.py`

**Interfaces:**
- Consumes: `crawler.discovery.walker._host` (bare host).
- Produces:
  - `DomainRegistry(path, data=None, clock=time.time, *, decay=0.9, offer_weight=1.0, error_weight=0.5, promote_min_score=0.5)`
  - `DomainRegistry.load(path, clock=time.time, **score_kw) -> DomainRegistry`
  - `.record(host: str, offers: int, errors: int) -> None` (mutates in memory; no disk write)
  - `.top(n: int, known_hosts: set[str]) -> list[str]` (score ≥ promote_min_score, sorted `(-score, host)`, skips `known_hosts`)
  - `.prune(evict_min_score: float, evict_ttl_seconds: float) -> int`
  - `.save() -> None` (atomic)
  - `.score(host) -> float` (test helper; 0.0 if absent)

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_domain_registry.py
import json

from crawler.discovery.domain_registry import DomainRegistry


class Clock:
    def __init__(self, t=1000.0): self.t = t
    def __call__(self): return self.t


def _reg(tmp_path, clock=None, **kw):
    return DomainRegistry(str(tmp_path / "registry.json"),
                          clock=clock or Clock(), **kw)


def test_record_creates_entry_and_score(tmp_path):
    r = _reg(tmp_path, offer_weight=1.0)
    r.record("silpo.ua", offers=1, errors=0)
    assert r.score("silpo.ua") == 1.0


def test_score_decays_then_rewards(tmp_path):
    r = _reg(tmp_path, decay=0.9, offer_weight=1.0, error_weight=0.5)
    r.record("x.ua", offers=1, errors=0)          # 1.0
    r.record("x.ua", offers=0, errors=0)          # 1.0*0.9 = 0.9
    r.record("x.ua", offers=1, errors=2)          # 0.9*0.9 + 1 - 1.0 = 0.81
    assert abs(r.score("x.ua") - 0.81) < 1e-9


def test_score_never_negative(tmp_path):
    r = _reg(tmp_path, error_weight=0.5)
    r.record("bad.ua", offers=0, errors=10)
    assert r.score("bad.ua") == 0.0


def test_counters_and_timestamps(tmp_path):
    clock = Clock(2000.0)
    r = _reg(tmp_path, clock=clock)
    r.record("a.ua", offers=2, errors=1)
    clock.t = 2500.0
    r.record("a.ua", offers=0, errors=0)
    e = r._data["domains"]["a.ua"]
    assert e["offers"] == 2 and e["errors"] == 1
    assert e["passes"] == 2 and e["empty_passes"] == 1
    assert e["first_seen"] == 2000.0 and e["last_seen"] == 2500.0
    assert e["last_offer"] == 2000.0


def test_top_filters_threshold_and_known_and_sorts(tmp_path):
    r = _reg(tmp_path, promote_min_score=0.5)
    r.record("hi.ua", offers=3, errors=0)     # 3.0
    r.record("mid.ua", offers=1, errors=0)    # 1.0
    r.record("lo.ua", offers=0, errors=1)     # 0.0 (below 0.5)
    assert r.top(10, known_hosts=set()) == ["hi.ua", "mid.ua"]
    assert r.top(10, known_hosts={"hi.ua"}) == ["mid.ua"]
    assert r.top(1, known_hosts=set()) == ["hi.ua"]


def test_prune_needs_both_cold_and_old(tmp_path):
    clock = Clock(10_000.0)
    r = _reg(tmp_path, clock=clock)
    r.record("cold_old.ua", offers=0, errors=1)     # score 0.0, last_seen 10000
    r.record("cold_new.ua", offers=0, errors=1)
    r.record("warm_old.ua", offers=5, errors=0)     # score 5.0
    clock.t = 20_000.0
    r.record("cold_new.ua", offers=0, errors=1)     # last_seen bumped to 20000
    removed = r.prune(evict_min_score=0.1, evict_ttl_seconds=5000.0)
    assert removed == 1
    assert "cold_old.ua" not in r._data["domains"]
    assert "cold_new.ua" in r._data["domains"]   # too new
    assert "warm_old.ua" in r._data["domains"]   # too warm


def test_save_load_roundtrip(tmp_path):
    p = str(tmp_path / "registry.json")
    r = DomainRegistry(p, clock=Clock())
    r.record("s.ua", offers=1, errors=0)
    r.save()
    r2 = DomainRegistry.load(p, clock=Clock())
    assert r2.score("s.ua") == 1.0


def test_load_corrupt_starts_clean(tmp_path):
    p = str(tmp_path / "registry.json")
    with open(p, "w", encoding="utf-8") as f:
        f.write("{ not json")
    r = DomainRegistry.load(p)
    assert r.top(10, set()) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_domain_registry.py -q`
Expected: FAIL with `ModuleNotFoundError: crawler.discovery.domain_registry`.

- [ ] **Step 3: Write minimal implementation**

```python
# crawler/crawler/discovery/domain_registry.py
"""Persistent crawler-side domain rating: exp-decay score per bare host, fed by every
actively fetched website domain. Governs the DomainFeed and active budget ordering.
Live moderation gate is untouched — this only decides who/what order we actively fetch."""

import copy
import json
import logging
import os
import time

from crawler.discovery.walker import _host  # single source of truth for bare host

log = logging.getLogger(__name__)

_EMPTY = {"version": 1, "domains": {}}


class DomainRegistry:
    def __init__(self, path, data=None, clock=time.time, *,
                 decay=0.9, offer_weight=1.0, error_weight=0.5, promote_min_score=0.5):
        self._path = path
        self._clock = clock
        self._data = data if data is not None else json.loads(json.dumps(_EMPTY))
        self._decay = decay
        self._offer_w = offer_weight
        self._error_w = error_weight
        self._promote = promote_min_score

    @classmethod
    def load(cls, path, clock=time.time, **score_kw):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("domain registry must be a JSON object")
            for k, default in _EMPTY.items():
                data.setdefault(k, copy.deepcopy(default))
        except (OSError, ValueError) as exc:
            log.warning("domain registry load failed (%s); starting clean", exc)
            data = None
        return cls(path, data=data, clock=clock, **score_kw)

    def record(self, host, offers, errors):
        host = _host(host)
        if not host:
            return
        now = self._clock()
        e = self._data["domains"].get(host)
        if e is None:
            e = {"score": 0.0, "offers": 0, "errors": 0, "passes": 0,
                 "empty_passes": 0, "first_seen": now, "last_seen": now, "last_offer": 0.0}
            self._data["domains"][host] = e
        e["score"] = max(0.0, e["score"] * self._decay
                         + offers * self._offer_w - errors * self._error_w)
        e["offers"] += int(offers)
        e["errors"] += int(errors)
        e["passes"] += 1
        if offers == 0:
            e["empty_passes"] += 1
        else:
            e["last_offer"] = now
        e["last_seen"] = now

    def score(self, host):
        e = self._data["domains"].get(_host(host))
        return float(e["score"]) if e else 0.0

    def top(self, n, known_hosts):
        rows = [(h, e["score"]) for h, e in self._data["domains"].items()
                if e["score"] >= self._promote and h not in known_hosts]
        rows.sort(key=lambda r: (-r[1], r[0]))
        return [h for h, _ in rows[:max(0, int(n))]]

    def prune(self, evict_min_score, evict_ttl_seconds):
        now = self._clock()
        dead = [h for h, e in self._data["domains"].items()
                if e["score"] < evict_min_score
                and now - e["last_seen"] >= evict_ttl_seconds]
        for h in dead:
            del self._data["domains"][h]
        return len(dead)

    def save(self):
        directory = os.path.dirname(self._path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = f"{self._path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False)
        os.replace(tmp, self._path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_domain_registry.py -q`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/domain_registry.py crawler/tests/test_domain_registry.py
git commit -m "feat(crawler): DomainRegistry — exp-decay domain rating state"
```

---

### Task 2: DomainFeed (candidate emitter)

**Files:**
- Create: `crawler/crawler/discovery/domain_feed.py`
- Test: `crawler/tests/test_domain_feed.py`

**Interfaces:**
- Consumes: `DomainRegistry.top(n, known_hosts)` (Task 1); `crawler.models.SourceCandidate`.
- Produces: `DomainFeed(registry, per_pass=8)` with `.candidates(known_hosts: set[str]) -> list[SourceCandidate]`.

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_domain_feed.py
from crawler.discovery.domain_feed import DomainFeed
from crawler.discovery.domain_registry import DomainRegistry


def _reg(tmp_path):
    return DomainRegistry(str(tmp_path / "r.json"), clock=lambda: 1.0, promote_min_score=0.5)


def test_emits_top_domains_as_website_candidates(tmp_path):
    r = _reg(tmp_path)
    r.record("hi.ua", offers=3, errors=0)
    r.record("mid.ua", offers=1, errors=0)
    cands = DomainFeed(r, per_pass=8).candidates(known_hosts=set())
    assert [c.url_or_handle for c in cands] == ["https://hi.ua", "https://mid.ua"]
    assert all(c.type == "website" for c in cands)
    assert cands[0].name == "hi.ua"
    assert cands[0].discovery_note == "domain-rating:hi.ua"


def test_skips_known_hosts(tmp_path):
    r = _reg(tmp_path)
    r.record("hi.ua", offers=3, errors=0)
    r.record("mid.ua", offers=1, errors=0)
    cands = DomainFeed(r, per_pass=8).candidates(known_hosts={"hi.ua"})
    assert [c.url_or_handle for c in cands] == ["https://mid.ua"]


def test_respects_per_pass_cap(tmp_path):
    r = _reg(tmp_path)
    for i in range(5):
        r.record(f"d{i}.ua", offers=i + 1, errors=0)
    cands = DomainFeed(r, per_pass=2).candidates(known_hosts=set())
    assert len(cands) == 2


def test_empty_registry_returns_empty(tmp_path):
    assert DomainFeed(_reg(tmp_path), per_pass=8).candidates(set()) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_domain_feed.py -q`
Expected: FAIL with `ModuleNotFoundError: crawler.discovery.domain_feed`.

- [ ] **Step 3: Write minimal implementation**

```python
# crawler/crawler/discovery/domain_feed.py
"""DDG-independent candidate emitter: re-surfaces top-rated productive domains as website
SourceCandidates each pass, exactly like BrandFeed but sourced from the DomainRegistry."""

from crawler.models import SourceCandidate


class DomainFeed:
    def __init__(self, registry, per_pass=8):
        self._registry = registry
        self._per_pass = per_pass

    def candidates(self, known_hosts):
        out = []
        for host in self._registry.top(self._per_pass, known_hosts):
            out.append(SourceCandidate(
                name=host, type="website", url_or_handle=f"https://{host}",
                discovered_from_source_id=None,
                discovery_note=f"domain-rating:{host}"))
        return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_domain_feed.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/domain_feed.py crawler/tests/test_domain_feed.py
git commit -m "feat(crawler): DomainFeed — re-feed top-rated domains as candidates"
```

---

### Task 3: Host-skip + registry recording in ActiveHarvester

**Files:**
- Modify: `crawler/crawler/discovery/harvest.py`
- Test: `crawler/tests/test_active_harvest.py` (append)

**Interfaces:**
- Consumes: `DomainRegistry.record(host, offers, errors)` (Task 1); `crawler.discovery.walker._host`.
- Produces: `ActiveHarvester(..., domain_registry=None)`; new signature
  `harvest(self, candidates, cats, known, summary, known_hosts=None)`.
- Behaviour: website candidate whose `_host(url) in known_hosts` is skipped **before** walking;
  after each website candidate, `domain_registry.record(host, offers_delta, errors_delta)`.
  Backward compatible: `known_hosts=None`⇒empty; `domain_registry=None`⇒no recording.

- [ ] **Step 1: Write the failing test (append to test_active_harvest.py)**

```python
# append to crawler/tests/test_active_harvest.py
from crawler.discovery.domain_registry import DomainRegistry


class _RecFetcher:
    """One block; offer iff text has '%'."""
    def __init__(self, text): self._text = text
    def fetch(self, source, last_seen_key):
        return [RawItem(source_id=None, platform="website", key="k", text=self._text,
                        url=source["url_or_handle"], links=[], site_name="Cafe")], None


def test_website_candidate_in_known_hosts_is_skipped(tmp_path):
    api = FakeApi()
    reg = DomainRegistry(str(tmp_path / "r.json"), clock=lambda: 1.0)
    h = ActiveHarvester(api, {"website": _RecFetcher("Знижка 20% УБД")},
                        GateExtractor(), rate_limiter=None, fetch_budget=5,
                        domain_registry=reg)
    summary = _summary()
    h.harvest([_cand(url="https://cafe.example")], cats=None, known=set(),
              summary=summary, known_hosts={"cafe.example"})
    assert api.offers == []                       # never fetched
    assert reg.score("cafe.example") == 0.0       # never recorded


def test_registry_records_offers_per_domain(tmp_path):
    api = FakeApi()
    reg = DomainRegistry(str(tmp_path / "r.json"), clock=lambda: 1.0, offer_weight=1.0)
    h = ActiveHarvester(api, {"website": _RecFetcher("Знижка 20% УБД")},
                        GateExtractor(), rate_limiter=None, fetch_budget=5,
                        domain_registry=reg)
    summary = _summary()
    h.harvest([_cand(url="https://cafe.example")], cats=None, known=set(), summary=summary)
    assert summary["offers"] == 1
    assert reg.score("cafe.example") == 1.0       # 1 offer recorded


def test_registry_not_recorded_without_registry():
    # regression: existing 4-arg call still works (no known_hosts, no registry)
    api = FakeApi()
    h = ActiveHarvester(api, {"website": _RecFetcher("Знижка 20% УБД")},
                        GateExtractor(), rate_limiter=None, fetch_budget=5)
    summary = _summary()
    h.harvest([_cand(url="https://cafe.example")], cats=None, known=set(), summary=summary)
    assert summary["offers"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_active_harvest.py -q`
Expected: FAIL — `ActiveHarvester.__init__() got an unexpected keyword argument 'domain_registry'`.

- [ ] **Step 3: Edit `harvest.py`**

Add the import near the top (after existing imports):

```python
from crawler.discovery.walker import _host
```

Change `__init__` signature to accept the registry (add the trailing param):

```python
    def __init__(self, api, fetchers, extractor, rate_limiter, fetch_budget=20,
                 walker=None, domain_rate_limiter=None, corpus_recorder=None,
                 domain_registry=None):
        self._api = api
        self._fetchers = fetchers
        self._extractor = extractor
        self._rl = rate_limiter
        self._budget = fetch_budget
        self._walker = walker
        self._domain_rl = domain_rate_limiter
        self._corpus = corpus_recorder
        self._registry = domain_registry
```

Replace the whole `harvest` method with:

```python
    def harvest(self, candidates, cats, known, summary, known_hosts=None) -> None:
        known_hosts = known_hosts or set()
        used = 0
        for cand in candidates:
            if used >= self._budget:
                break
            if cand.type not in _FETCHABLE:
                continue
            if normalize_ref(cand.type, cand.url_or_handle) in known:
                continue
            if cand.type == "website" and _host(cand.url_or_handle) in known_hosts:
                continue
            fetcher = self._fetchers.get(cand.type)
            if fetcher is None:
                continue
            used += 1
            before_o, before_e = summary["offers"], summary["errors"]
            try:
                self._harvest_one(cand, fetcher, cats, known, summary)
            except Exception as exc:  # noqa: BLE001 — isolate per candidate
                summary["errors"] += 1
                log.warning("active harvest failed for %s: %s", cand.url_or_handle, exc)
            if self._registry is not None and cand.type == "website":
                self._registry.record(_host(cand.url_or_handle),
                                      summary["offers"] - before_o,
                                      summary["errors"] - before_e)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_active_harvest.py -q`
Expected: PASS (all existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/harvest.py crawler/tests/test_active_harvest.py
git commit -m "feat(crawler): host-skip approved domains + record domain rating in harvester"
```

---

### Task 4: Passive deep-walk in Runner._crawl_source

**Files:**
- Modify: `crawler/crawler/runner.py`
- Test: `crawler/tests/test_runner.py` (append)

**Interfaces:**
- Consumes: `DomainWalker.walk(cand) -> WalkPlan(domain, urls, crawl_delay)`;
  `DomainRateLimiter.wait(domain, delay)`; `crawler.models.SourceCandidate`.
- Produces: `Runner(..., walker=None, domain_rate_limiter=None)`. When a website source is
  crawled and `walker` is present, expand it and fetch **every** planned page through the
  website fetcher under the per-domain limiter, running the existing passive extraction
  (offer + suggestions + corpus) per page. Non-website sources and the no-walker path are
  unchanged.

- [ ] **Step 1: Write the failing test (append to test_runner.py)**

```python
# append to crawler/tests/test_runner.py
from crawler.discovery.walker import WalkPlan
from crawler.models import SourceCandidate


class _MultiPageFetcher:
    """Returns a distinct offer block per URL so we can prove every page is fetched."""
    platform = "website"
    def __init__(self): self.seen = []
    def fetch(self, source, last_seen_key):
        url = source["url_or_handle"]
        self.seen.append(url)
        item = RawItem(source_id=source["id"], platform="website", key=f"k:{url}",
                       text="Знижка 30% для ветеранів", url=url, links=[])
        return [item], f"key:{url}"


class _FakeWalker:
    def __init__(self, urls, domain): self._urls = urls; self._domain = domain
    def walk(self, cand):
        return WalkPlan(domain=self._domain, urls=self._urls, crawl_delay=0.0)


class _FakeDomainRL:
    def __init__(self): self.calls = []
    def wait(self, domain, delay): self.calls.append((domain, delay))


def test_passive_walk_fetches_every_planned_page():
    src = {"id": 7, "type": "website", "name": "Shop", "url_or_handle": "https://shop.ua"}
    api = FakeApi([src])
    fetcher = _MultiPageFetcher()
    walker = _FakeWalker(["https://shop.ua", "https://shop.ua/sale", "https://shop.ua/promo"],
                         "shop.ua")
    drl = _FakeDomainRL()
    runner = Runner(api, {"website": fetcher}, get_extractor("heuristic"), _rl(),
                    walker=walker, domain_rate_limiter=drl)
    summary = runner.run()
    assert fetcher.seen == ["https://shop.ua", "https://shop.ua/sale", "https://shop.ua/promo"]
    assert summary["offers"] == 3                      # one offer per page
    assert drl.calls == [("shop.ua", 0.0)] * 3         # per-domain limiter used
    assert api.state[7] == "key:https://shop.ua/promo" # crawl_state = last page key


def test_passive_walk_skipped_for_telegram_source():
    src = {"id": 8, "type": "telegram", "name": "Chan", "url_or_handle": "https://t.me/chan"}
    api = FakeApi([src])
    item = RawItem(source_id=8, platform="telegram", key="k",
                   text="Знижка 20% для ветеранів", links=[])
    walker = _FakeWalker(["ignored"], "t.me")
    runner = Runner(api, {"telegram": FakeFetcher([item])}, get_extractor("heuristic"), _rl(),
                    walker=walker, domain_rate_limiter=_FakeDomainRL())
    summary = runner.run()
    assert summary["offers"] == 1                       # normal single-fetch path
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_runner.py -q`
Expected: FAIL — `Runner.__init__() got an unexpected keyword argument 'walker'`.

- [ ] **Step 3: Edit `runner.py`**

Add import at top:

```python
from crawler.models import SourceCandidate
```

Extend `__init__` (add the two params + attrs):

```python
    def __init__(self, api_client, fetchers: dict, extractor, rate_limiter,
                 discovery=None, keywords=None, harvester=None, brand_feed=None,
                 freshness_ttl_days=30, corpus_recorder=None,
                 walker=None, domain_rate_limiter=None):
        self._api = api_client
        self._fetchers = fetchers
        self._extractor = extractor
        self._rl = rate_limiter
        self._discovery = discovery
        self._keywords = keywords or []
        self._harvester = harvester
        self._brand_feed = brand_feed
        self._freshness_ttl_days = freshness_ttl_days
        self._corpus = corpus_recorder
        self._walker = walker
        self._domain_rl = domain_rate_limiter
```

Replace `_crawl_source` and factor the per-item work into `_process_item`:

```python
    def _crawl_source(self, source, cats, known, summary):
        if self._walker is not None and source["type"] == "website":
            self._crawl_website_deep(source, cats, known, summary)
            return
        state = self._api.get_crawl_state(source["id"])
        items, new_key = self._fetch_for(source, state.get("last_seen_key"))
        for item in items:
            self._process_item(item, source, cats, known, summary)
        self._api.set_crawl_state(source["id"], new_key)

    def _crawl_website_deep(self, source, cats, known, summary):
        cand = SourceCandidate(name=source["name"], type="website",
                               url_or_handle=source["url_or_handle"])
        plan = self._walker.walk(cand)
        fetcher = self._fetchers.get("website")
        if fetcher is None:
            return
        state = self._api.get_crawl_state(source["id"])
        last_key = state.get("last_seen_key")
        for url in plan.urls:
            self._domain_rl.wait(plan.domain, plan.crawl_delay)
            page_src = {"id": source["id"], "type": "website",
                        "name": source["name"], "url_or_handle": url}
            items, last_key = fetcher.fetch(page_src, last_key)
            for item in items:
                self._process_item(item, source, cats, known, summary)
        self._api.set_crawl_state(source["id"], last_key)

    def _process_item(self, item, source, cats, known, summary):
        cand = self._extractor.extract(item, source["name"], cats)
        if self._corpus is not None:
            self._corpus.record(item, cand is not None)
        if cand is not None:
            cand.offer_category_ids = resolve_offer_categories(
                self._api, cats, cand.offer_category_matches)
            self._api.submit_offer(offer_payload(cand))
            summary["offers"] += 1
        for sc in extract_source_candidates(item, known):
            self._api.submit_suggestion(suggestion_payload(sc))
            known.add(normalize_ref(sc.type, sc.url_or_handle))
            summary["suggestions"] += 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_runner.py -q`
Expected: PASS (existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/runner.py crawler/tests/test_runner.py
git commit -m "feat(crawler): passive deep-walk website sources via DomainWalker"
```

---

### Task 5: Runner active-block integration (feed ordering + registry persistence)

**Files:**
- Modify: `crawler/crawler/runner.py`
- Test: `crawler/tests/test_runner.py` (append)

**Interfaces:**
- Consumes: `DomainFeed.candidates(known_hosts)` (Task 2); `DomainRegistry.save()/prune()` (Task 1);
  `ActiveHarvester.harvest(..., known_hosts=...)` (Task 3); `walker._host`.
- Produces: `Runner(..., domain_feed=None, domain_registry=None, domain_evict_min_score=0.1,
  domain_evict_ttl_seconds=2_592_000.0)`. Active block prepends domain_feed candidates
  (exploit) before discovery+brand_feed (explore), builds `known_hosts` from active website
  sources, passes it to `harvest`, and after harvest calls `registry.prune(...)` + `registry.save()`.

- [ ] **Step 1: Write the failing test (append to test_runner.py)**

```python
# append to crawler/tests/test_runner.py
from crawler.discovery.domain_registry import DomainRegistry


class _RecordingHarvester:
    def __init__(self): self.candidates = None; self.known_hosts = None
    def harvest(self, candidates, cats, known, summary, known_hosts=None):
        self.candidates = list(candidates); self.known_hosts = set(known_hosts or set())


class _StubFeed:
    def __init__(self, cands): self._cands = cands
    def candidates(self, known_hosts):
        return [c for c in self._cands if c.name not in known_hosts]


def test_active_block_prepends_domain_feed_and_builds_known_hosts(tmp_path):
    src = {"id": 1, "type": "website", "name": "Silpo", "url_or_handle": "https://silpo.ua"}
    api = FakeApi([src])
    feed_cand = SourceCandidate(name="proven.ua", type="website",
                                url_or_handle="https://proven.ua")
    hv = _RecordingHarvester()
    reg = DomainRegistry(str(tmp_path / "r.json"), clock=lambda: 1.0)
    runner = Runner(api, {"website": FakeFetcher([])}, get_extractor("heuristic"), _rl(),
                    harvester=hv, domain_feed=_StubFeed([feed_cand]), domain_registry=reg)
    runner.run()
    assert hv.candidates[0].url_or_handle == "https://proven.ua"   # feed first (exploit)
    assert hv.known_hosts == {"silpo.ua"}                          # active source host


def test_active_block_prunes_and_saves_registry(tmp_path):
    import os
    p = str(tmp_path / "r.json")
    api = FakeApi([])
    reg = DomainRegistry(p, clock=lambda: 1e9)
    reg.record("dead.ua", offers=0, errors=1)          # score 0, old (last_seen 1e9, ttl small)
    runner = Runner(api, {"website": FakeFetcher([])}, get_extractor("heuristic"), _rl(),
                    harvester=_RecordingHarvester(), domain_feed=_StubFeed([]),
                    domain_registry=reg, domain_evict_min_score=0.1,
                    domain_evict_ttl_seconds=0.0)
    runner.run()
    assert os.path.exists(p)                            # saved
    assert DomainRegistry.load(p).top(10, set()) == [] # dead pruned
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_runner.py -q`
Expected: FAIL — `Runner.__init__() got an unexpected keyword argument 'domain_feed'`.

- [ ] **Step 3: Edit `runner.py`**

Add import at top:

```python
from crawler.discovery.walker import _host
```

Extend `__init__` (add params + attrs after `self._domain_rl`):

```python
                 walker=None, domain_rate_limiter=None,
                 domain_feed=None, domain_registry=None,
                 domain_evict_min_score=0.1, domain_evict_ttl_seconds=2_592_000.0):
```

```python
        self._domain_feed = domain_feed
        self._domain_registry = domain_registry
        self._evict_min = domain_evict_min_score
        self._evict_ttl = domain_evict_ttl_seconds
```

Replace the active harvester block in `run()` (the `if self._harvester is not None:` block) with:

```python
        if self._harvester is not None:
            try:
                known_hosts = {_host(s["url_or_handle"]) for s in sources
                               if s["type"] == "website"}
                candidates = []
                if self._domain_feed is not None:
                    candidates += self._domain_feed.candidates(known_hosts)
                if self._discovery is not None and self._keywords:
                    candidates += self._discovery.run(self._keywords, known)
                if self._brand_feed is not None:
                    candidates += self._brand_feed.candidates(known)
                if candidates:
                    self._harvester.harvest(candidates, cats, known, summary,
                                            known_hosts=known_hosts)
            except Exception as exc:  # noqa: BLE001 — discovery must not crash the pass
                summary["errors"] += 1
                log.warning("active discovery / brand-feed harvest failed: %s", exc)
            finally:
                if self._domain_registry is not None:
                    try:
                        self._domain_registry.prune(self._evict_min, self._evict_ttl)
                        self._domain_registry.save()
                    except Exception as exc:  # noqa: BLE001 — persistence best-effort
                        log.warning("domain registry persist failed: %s", exc)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_runner.py -q`
Expected: PASS (existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/runner.py crawler/tests/test_runner.py
git commit -m "feat(crawler): wire DomainFeed ordering + registry persistence into Runner"
```

---

### Task 6: Config knobs + wiring + docs

**Files:**
- Modify: `crawler/crawler/config.py`
- Modify: `crawler/crawler/wiring.py`
- Modify: `crawler/tests/test_wiring.py` (append)
- Modify: `crawler/tests/test_config.py` (append)
- Modify: `.env.example`
- Modify: `RUN.md`

**Interfaces:**
- Consumes: everything from Tasks 1–5.
- Produces: 9 config knobs (spec §7); `build_runner` builds `DomainRegistry`+`DomainFeed` and
  passes `walker`/`domain_rl`/`domain_feed`/`domain_registry` to `Runner` and
  `domain_registry` to `ActiveHarvester`, all gated by `domain_rating_enabled`.

- [ ] **Step 1: Write the failing tests**

```python
# append to crawler/tests/test_config.py
def test_domain_rating_defaults():
    from crawler.config import _RawSettings
    s = _RawSettings()
    assert s.domain_rating_enabled is True
    assert s.domain_registry_path == "/data/domain_registry.json"
    assert s.domain_feed_per_pass == 8
    assert s.domain_score_decay == 0.9
    assert s.domain_offer_weight == 1.0
    assert s.domain_error_weight == 0.5
    assert s.domain_promote_min_score == 0.5
    assert s.domain_evict_min_score == 0.1
    assert s.domain_evict_ttl_hours == 720
```

```python
# append to crawler/tests/test_wiring.py
def test_domain_rating_off_is_byte_equivalent(tmp_path):
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=False, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={},
        brand_feed_enabled=False, sitemap_depth_enabled=False,
        domain_rating_enabled=False,
    )
    runner = build_runner(cfg)
    assert runner._domain_feed is None
    assert runner._domain_registry is None
    assert runner._walker is None


def test_domain_rating_on_builds_feed_registry_and_walker(tmp_path):
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=False, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={},
        brand_feed_enabled=False, sitemap_depth_enabled=True,   # brand_feed off → no network
        domain_rating_enabled=True,
        domain_registry_path=str(tmp_path / "reg.json"),
        robots_cache_path=str(tmp_path / "robots.json"),
    )
    runner = build_runner(cfg)
    assert runner._domain_feed is not None
    assert runner._domain_registry is not None
    assert runner._walker is not None                 # passive deep-walk enabled
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_config.py tests/test_wiring.py -q`
Expected: FAIL — `_RawSettings` has no `domain_rating_enabled` / `Config()` unexpected kwarg.

- [ ] **Step 3: Edit `config.py`**

Add to `_RawSettings` (after `stoplist_path`):

```python
    domain_rating_enabled: bool = True
    domain_registry_path: str = "/data/domain_registry.json"
    domain_feed_per_pass: int = 8
    domain_score_decay: float = 0.9
    domain_offer_weight: float = 1.0
    domain_error_weight: float = 0.5
    domain_promote_min_score: float = 0.5
    domain_evict_min_score: float = 0.1
    domain_evict_ttl_hours: int = 720
```

Add the identical fields to the `Config` dataclass (after `stoplist_path: str = "/data/stoplist.json"`):

```python
    domain_rating_enabled: bool = True
    domain_registry_path: str = "/data/domain_registry.json"
    domain_feed_per_pass: int = 8
    domain_score_decay: float = 0.9
    domain_offer_weight: float = 1.0
    domain_error_weight: float = 0.5
    domain_promote_min_score: float = 0.5
    domain_evict_min_score: float = 0.1
    domain_evict_ttl_hours: int = 720
```

Add to the `Config(...)` construction in `load_config()` (after `stoplist_path=s.stoplist_path,`):

```python
        domain_rating_enabled=s.domain_rating_enabled,
        domain_registry_path=s.domain_registry_path,
        domain_feed_per_pass=s.domain_feed_per_pass,
        domain_score_decay=s.domain_score_decay,
        domain_offer_weight=s.domain_offer_weight,
        domain_error_weight=s.domain_error_weight,
        domain_promote_min_score=s.domain_promote_min_score,
        domain_evict_min_score=s.domain_evict_min_score,
        domain_evict_ttl_hours=s.domain_evict_ttl_hours,
```

- [ ] **Step 4: Edit `wiring.py`**

Add imports (with the other discovery imports):

```python
from crawler.discovery.domain_feed import DomainFeed
from crawler.discovery.domain_registry import DomainRegistry
```

In `build_runner`, after the `sitemap_depth_enabled` walker block (`if config.sitemap_depth_enabled: walker, domain_rl = _build_walker(...)`), add registry/feed construction:

```python
    domain_registry = None
    domain_feed = None
    if config.domain_rating_enabled:
        domain_registry = DomainRegistry.load(
            config.domain_registry_path,
            decay=config.domain_score_decay,
            offer_weight=config.domain_offer_weight,
            error_weight=config.domain_error_weight,
            promote_min_score=config.domain_promote_min_score)
        domain_feed = DomainFeed(domain_registry, per_pass=config.domain_feed_per_pass)
        if walker is None:
            walker, domain_rl = _build_walker(config, web_client)   # passive deep-walk needs it
```

Extend the `ActiveHarvester(...)` construction to pass the registry:

```python
    if (discovery is not None or brand_feed is not None) and config.active_fetch_budget:
        harvester = ActiveHarvester(api, fetchers, extractor, rate_limiter,
                                    fetch_budget=config.active_fetch_budget,
                                    walker=walker, domain_rate_limiter=domain_rl,
                                    corpus_recorder=corpus_recorder,
                                    domain_registry=domain_registry)
```

Extend the final `Runner(...)` construction to pass walker/domain_rl/feed/registry + evict knobs:

```python
    return Runner(api, fetchers, extractor, rate_limiter,
                  discovery=discovery, keywords=keywords, harvester=harvester,
                  brand_feed=brand_feed, freshness_ttl_days=config.freshness_ttl_days,
                  corpus_recorder=corpus_recorder,
                  walker=walker, domain_rate_limiter=domain_rl,
                  domain_feed=domain_feed, domain_registry=domain_registry,
                  domain_evict_min_score=config.domain_evict_min_score,
                  domain_evict_ttl_seconds=config.domain_evict_ttl_hours * 3600)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_config.py tests/test_wiring.py -q`
Expected: PASS (existing + new).

- [ ] **Step 6: Update `.env.example` and `RUN.md`**

Append to `.env.example` (after the autofill block):

```dotenv
# --- Domain rating (self-growing discovery lever 3) ---
DOMAIN_RATING_ENABLED=true
DOMAIN_REGISTRY_PATH=/data/domain_registry.json
DOMAIN_FEED_PER_PASS=8
DOMAIN_SCORE_DECAY=0.9
DOMAIN_OFFER_WEIGHT=1.0
DOMAIN_ERROR_WEIGHT=0.5
DOMAIN_PROMOTE_MIN_SCORE=0.5
DOMAIN_EVICT_MIN_SCORE=0.1
DOMAIN_EVICT_TTL_HOURS=720
```

Add a "Блок 5 — Domain rating" section to `RUN.md` describing: the registry re-feeds proven
domains DDG-independently; approved domains (active website sources) are skipped by the active
path and deep-walked by the passive source-loop; `DOMAIN_RATING_ENABLED=false` restores prior
behaviour. Keep the wording consistent with the existing autofill "Блок 4" section.

- [ ] **Step 7: Run the full crawler suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — all tests green (299 baseline + new).

- [ ] **Step 8: Commit**

```bash
git add crawler/crawler/config.py crawler/crawler/wiring.py \
        crawler/tests/test_config.py crawler/tests/test_wiring.py .env.example RUN.md
git commit -m "feat(crawler): config knobs + wiring + docs for domain-rating"
```

---

## Self-Review

**Spec coverage:**
- §3.1 DomainRegistry → Task 1. §3.2 score model → Task 1 (tests). §3.3 DomainFeed → Task 2.
- §4 host-skip → Task 3 (harvest) + Task 5 (known_hosts build). §5 passive deep-walk → Task 4.
- §6 explore/exploit ordering + record + save/prune → Task 3 (record) + Task 5 (ordering/persist).
- §7 config → Task 6. §8 testing → each task's tests + Task 6 full-suite gate.
- §2 invariants: `domain_rating_enabled=False` byte-equivalence → Task 6 wiring test;
  best-effort → try/except in Tasks 3/5; website-only → type guards in Tasks 3/4/5.

**Placeholder scan:** none — every step has concrete code/commands. RUN.md prose (Task 6 Step 6)
is documentation, deliberately descriptive.

**Type consistency:** `_host` used identically for registry keys (Task 1 `record`), harvest
skip/record (Task 3), known_hosts build (Task 5), feed emission (Task 2 via `top`/registry).
`record(host, offers, errors)`, `top(n, known_hosts)`, `candidates(known_hosts)`,
`harvest(..., known_hosts=None)`, `WalkPlan(domain, urls, crawl_delay)` consistent across tasks.

## Deferred / out of scope (spec §9)
Telegram/IG/FB rating; rating of passive sources; LLM tail; brand-anchored queries; backend
`domain_rating` table (chose crawler-side JSON).
