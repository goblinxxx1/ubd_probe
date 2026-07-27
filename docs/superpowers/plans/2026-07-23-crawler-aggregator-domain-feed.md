# Crawler aggregator-as-domain-feed — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn blocklisted aggregator directories (veteranam.info) into a feed of business DOMAINS — capture their outbound business hosts, re-feed them as website candidates, harvest the businesses' own sites for first-party offers.

**Architecture:** Mirrors the OSM-feed pattern. A new `AggregatorDomainStore` (persistent host list + rotation cursor) is written by the harvester when it processes a blocklisted-aggregator page, and read by a new `AggregatorDomainFeed` that emits rotating website candidates on subsequent passes (persist + re-feed decoupling). The aggregator page itself still emits 0 offers (the interim drop is kept).

**Tech Stack:** Python 3.11, pytest, existing crawler package.

## Global Constraints

- Scope is `crawler/` only — no backend/admin, no DB.
- Baseline is **403** crawler tests green. Run from `crawler/`: `./.venv/Scripts/python.exe -m pytest -q` (no mysql).
- Nested package: crawler project root `D:\ubd_probe\crawler` (`.venv`, `tests/`, `crawler/` package). Source under `crawler/crawler/…`; tests under `crawler/tests/`.
- Autofeed (human gate stays at OFFER moderation, `pending_review`); mine links ONLY from blocklisted hosts; persist + re-feed (not inline same-pass).
- New domains are only CANDIDATES; precision-gates + moderation are downstream. `_outbound_hosts` already excludes blocklisted hosts, so other block-hosts never enter the feed.
- `aggregator_feed_enabled=False` MUST be byte-equivalent (no store → no capture, no feed built).
- Reuse existing pieces: `normalize_ref` (`crawler.discovery.passive`), `SourceCandidate` (`crawler.models`), `is_blocked_host` (`crawler.discovery.blocklist`), `_outbound_hosts`/`build_page_ctx`/`attribute` (`crawler.discovery.attribution`), `_host` (`crawler.discovery.brand_feed`).
- Config defaults (exact): `aggregator_feed_enabled=True`, `aggregator_feed_per_pass=20`, `aggregator_domains_path="/data/aggregator_domains.json"`, `aggregator_max_domains=500`.
- The interim blocklisted-drop (`attribution.py`, no salvage) stays — capture ADDS host collection, never re-enables the salvage offer.

---

### Task 1: `AggregatorDomainStore` + `AggregatorDomainFeed`

**Files:**
- Create: `crawler/crawler/discovery/aggregator_feed.py`
- Test: `crawler/tests/test_aggregator_feed.py` (new)

**Interfaces:**
- Consumes: `normalize_ref`, `SourceCandidate`.
- Produces:
  - `AggregatorDomainStore(path, data=None)` with classmethod `load(path)`, `domains() -> list[str]`, `cursor() -> int`, `set_cursor(int)`, `add(hosts, cap: int)` (union preserving order, dedup, keep newest `cap` when over).
  - `AggregatorDomainFeed(store, per_pass=20)` with `candidates(known) -> list[SourceCandidate]`.

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_aggregator_feed.py
from crawler.discovery.aggregator_feed import AggregatorDomainStore, AggregatorDomainFeed
from crawler.discovery.passive import normalize_ref


def test_add_unions_dedups_and_persists(tmp_path):
    path = str(tmp_path / "agg.json")
    s = AggregatorDomainStore.load(path)
    assert s.domains() == []
    s.add({"b.ua", "a.ua"}, cap=10)          # sorted on insert
    s.add({"a.ua", "c.ua"}, cap=10)          # a.ua deduped, c.ua appended
    assert AggregatorDomainStore.load(path).domains() == ["a.ua", "b.ua", "c.ua"]


def test_add_keeps_newest_cap(tmp_path):
    s = AggregatorDomainStore.load(str(tmp_path / "agg.json"))
    s.add({"a.ua"}, cap=2)
    s.add({"b.ua"}, cap=2)
    s.add({"c.ua"}, cap=2)                    # over cap → oldest (a.ua) dropped
    assert s.domains() == ["b.ua", "c.ua"]


def test_add_ignores_empty(tmp_path):
    s = AggregatorDomainStore.load(str(tmp_path / "agg.json"))
    s.add({"", "a.ua"}, cap=10)
    assert s.domains() == ["a.ua"]


def test_cursor_defaults_zero_and_persists(tmp_path):
    path = str(tmp_path / "agg.json")
    s = AggregatorDomainStore.load(path)
    assert s.cursor() == 0
    s.set_cursor(4)
    assert AggregatorDomainStore.load(path).cursor() == 4


def test_load_tolerates_corrupt(tmp_path):
    p = tmp_path / "agg.json"
    p.write_text("{ not json", encoding="utf-8")
    assert AggregatorDomainStore.load(str(p)).domains() == []


def _store(tmp_path, hosts):
    s = AggregatorDomainStore.load(str(tmp_path / "agg.json"))
    s.add(set(hosts), cap=100)
    return s


def test_feed_emits_website_candidates(tmp_path):
    feed = AggregatorDomainFeed(_store(tmp_path, ["okko.ua"]))
    c = feed.candidates(known=set())[0]
    assert c.type == "website"
    assert c.url_or_handle == "https://okko.ua"
    assert c.discovery_note == "aggregator-feed:okko.ua"


def test_feed_skips_known_and_empty(tmp_path):
    feed = AggregatorDomainFeed(_store(tmp_path, ["okko.ua"]))
    known = {normalize_ref("website", "https://okko.ua")}
    assert feed.candidates(known) == []
    empty = AggregatorDomainFeed(AggregatorDomainStore.load(str(tmp_path / "e.json")))
    assert empty.candidates(known=set()) == []


def test_feed_rotates_window(tmp_path):
    # note: store keeps insertion order; add sorts each batch, so a,b,c,d
    feed = AggregatorDomainFeed(_store(tmp_path, ["a.ua", "b.ua", "c.ua", "d.ua"]), per_pass=2)
    assert [c.name for c in feed.candidates(set())] == ["a.ua", "b.ua"]
    assert [c.name for c in feed.candidates(set())] == ["c.ua", "d.ua"]
    assert [c.name for c in feed.candidates(set())] == ["a.ua", "b.ua"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_aggregator_feed.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'crawler.discovery.aggregator_feed'`

- [ ] **Step 3: Write minimal implementation**

```python
# crawler/crawler/discovery/aggregator_feed.py
"""Aggregator-as-domain-feed: a persistent store of business hosts harvested from
blocklisted aggregator directories, plus a rotating feed that re-surfaces them as
website candidates. Same persist+re-feed pattern as osm_feed / brand_feed."""

import copy
import json
import logging
import os

from crawler.discovery.passive import normalize_ref
from crawler.models import SourceCandidate

log = logging.getLogger(__name__)

_EMPTY = {"version": 1, "hosts": [], "cursor": 0}


class AggregatorDomainStore:
    """Persistent ordered host list + rotation cursor. Accumulates continuously (no
    freshness gate). Atomic writes; a corrupt/missing file starts clean."""

    def __init__(self, path, data=None):
        self._path = path
        self._data = data if data is not None else json.loads(json.dumps(_EMPTY))

    @classmethod
    def load(cls, path) -> "AggregatorDomainStore":
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("aggregator store must be a JSON object")
            for k, default in _EMPTY.items():
                data.setdefault(k, copy.deepcopy(default))
        except (OSError, ValueError) as exc:
            log.warning("aggregator store load failed (%s); starting clean", exc)
            data = None
        return cls(path, data=data)

    def domains(self) -> list[str]:
        return list(self._data.get("hosts", []))

    def cursor(self) -> int:
        return int(self._data.get("cursor", 0))

    def set_cursor(self, value: int) -> None:
        self._data["cursor"] = int(value)
        self._save()

    def add(self, hosts, cap: int) -> None:
        cur = list(self._data.get("hosts", []))
        seen = set(cur)
        for h in sorted(hosts):
            if h and h not in seen:
                cur.append(h)
                seen.add(h)
        if len(cur) > cap:
            cur = cur[len(cur) - cap:]      # keep newest cap, drop oldest from the front
        self._data["hosts"] = cur
        self._save()

    def _save(self) -> None:
        directory = os.path.dirname(self._path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = f"{self._path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False)
        os.replace(tmp, self._path)


class AggregatorDomainFeed:
    """Rotating window of website SourceCandidates from the store."""

    def __init__(self, store, per_pass=20):
        self._store = store
        self._per_pass = per_pass

    def candidates(self, known) -> list[SourceCandidate]:
        hosts = self._store.domains()
        size = len(hosts)
        if size == 0:
            return []
        n = max(1, min(int(self._per_pass), size))
        cursor = self._store.cursor()
        if cursor < 0 or cursor >= size:
            cursor = 0
        window = [hosts[(cursor + i) % size] for i in range(n)]
        self._store.set_cursor((cursor + n) % size)
        out: list[SourceCandidate] = []
        for host in window:
            url = f"https://{host}"
            if normalize_ref("website", url) in known:
                continue
            out.append(SourceCandidate(
                name=host, type="website", url_or_handle=url,
                discovered_from_source_id=None, discovery_note=f"aggregator-feed:{host}"))
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_aggregator_feed.py -q`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/aggregator_feed.py crawler/tests/test_aggregator_feed.py
git commit -m "feat(crawler): AggregatorDomainStore + AggregatorDomainFeed"
```

---

### Task 2: harvester captures outbound hosts from blocklisted pages

**Files:**
- Modify: `crawler/crawler/discovery/harvest.py`
- Test: `crawler/tests/test_active_harvest.py` (append)

**Interfaces:**
- Consumes: `AggregatorDomainStore.add(hosts, cap)` (Task 1), `is_blocked_host`, `_outbound_hosts`.
- Produces: `ActiveHarvester.__init__` gains `aggregator_store=None, aggregator_max_domains=500`; `_process_page` records outbound hosts of a blocklisted page into the store.

- [ ] **Step 1: Write the failing test**

```python
# append to crawler/tests/test_active_harvest.py
class _RecStore:
    def __init__(self): self.added = []
    def add(self, hosts, cap): self.added.append((set(hosts), cap))


def _blocklisted_item():
    # url host veteranam.info is on the SEED blocklist; one outbound business link
    return RawItem(source_id=None, platform="website", key="k",
                   text="Знижка 20% для УБД", url="https://veteranam.info/list",
                   links=["https://realbiz.com.ua/sale"], site_name="V")


def test_blocklisted_page_captures_outbound_hosts():
    api = FakeApi()
    store = _RecStore()
    h = ActiveHarvester(api, {"website": FakeFetcher([_blocklisted_item()])},
                        GateExtractor(), rate_limiter=None, fetch_budget=5,
                        aggregator_store=store, aggregator_max_domains=500)
    h.harvest([_cand(url="https://veteranam.info")], cats=None, known=set(), summary=_summary())
    assert store.added and store.added[0] == ({"realbiz.com.ua"}, 500)
    assert api.offers == []     # aggregator page still emits no offer (interim drop kept)


def test_non_blocklisted_page_does_not_capture():
    api = FakeApi()
    store = _RecStore()
    h = ActiveHarvester(api, {"website": FakeFetcher([_item("Знижка 20% для УБД у нас",
                                                            site_name="Cafe")])},
                        GateExtractor(), rate_limiter=None, fetch_budget=5,
                        aggregator_store=store, aggregator_max_domains=500)
    h.harvest([_cand()], cats=None, known=set(), summary=_summary())
    assert store.added == []     # normal first-party page: nothing captured


def test_no_store_is_byte_equivalent():
    api = FakeApi()
    h = ActiveHarvester(api, {"website": FakeFetcher([_blocklisted_item()])},
                        GateExtractor(), rate_limiter=None, fetch_budget=5)
    h.harvest([_cand(url="https://veteranam.info")], cats=None, known=set(), summary=_summary())
    assert api.offers == []      # no crash, no capture path
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_active_harvest.py -q -k "capture or byte_equivalent"`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'aggregator_store'`

- [ ] **Step 3: Write minimal implementation**

In `crawler/crawler/discovery/harvest.py`:

1. Extend the imports:
```python
from crawler.discovery.attribution import attribute, build_page_ctx, _outbound_hosts
from crawler.discovery.blocklist import is_blocked_host
```

2. Extend `ActiveHarvester.__init__` — append two params after `aggregator_min_outbound=3`:
```python
    def __init__(self, api, fetchers, extractor, rate_limiter, fetch_budget=20,
                 walker=None, domain_rate_limiter=None, corpus_recorder=None,
                 domain_registry=None, hardening_enabled=True,
                 aggregator_min_outbound=3, aggregator_store=None,
                 aggregator_max_domains=500):
```
and store them in the body:
```python
        self._aggregator_store = aggregator_store
        self._aggregator_max_domains = aggregator_max_domains
```

3. In `_process_page`, after `ctx = build_page_ctx(cand, passing)` and before the `for item in passing:` loop, add the capture:
```python
        if self._aggregator_store is not None and is_blocked_host(ctx.host):
            hosts = _outbound_hosts(passing)
            if hosts:
                self._aggregator_store.add(hosts, self._aggregator_max_domains)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_active_harvest.py -q`
Expected: PASS (all, including the 3 new)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/harvest.py crawler/tests/test_active_harvest.py
git commit -m "feat(crawler): harvester captures outbound business hosts from blocklisted pages"
```

---

### Task 3: config flags

**Files:**
- Modify: `crawler/crawler/config.py` (`_RawSettings`, `Config`, `load_config`)
- Test: `crawler/tests/test_config.py` (append)

**Interfaces:**
- Produces: `Config.aggregator_feed_enabled=True`, `aggregator_feed_per_pass=20`, `aggregator_domains_path="/data/aggregator_domains.json"`, `aggregator_max_domains=500`.

- [ ] **Step 1: Write the failing test**

```python
# append to crawler/tests/test_config.py
def test_aggregator_feed_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)      # no .env -> defaults apply
    cfg = load_config()
    assert cfg.aggregator_feed_enabled is True
    assert cfg.aggregator_feed_per_pass == 20
    assert cfg.aggregator_domains_path == "/data/aggregator_domains.json"
    assert cfg.aggregator_max_domains == 500


def test_aggregator_feed_env_overrides(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGGREGATOR_FEED_ENABLED", "false")
    monkeypatch.setenv("AGGREGATOR_MAX_DOMAINS", "50")
    cfg = load_config()
    assert cfg.aggregator_feed_enabled is False
    assert cfg.aggregator_max_domains == 50
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_config.py -q -k aggregator`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'aggregator_feed_enabled'`

- [ ] **Step 3: Write minimal implementation**

In `crawler/crawler/config.py`:

1. In `_RawSettings`, add after the `osm_*` flags (e.g. after `osm_feed_query_timeout`):
```python
    aggregator_feed_enabled: bool = True
    aggregator_feed_per_pass: int = 20
    aggregator_domains_path: str = "/data/aggregator_domains.json"
    aggregator_max_domains: int = 500
```

2. In the `Config` dataclass, add after the `osm_*` fields:
```python
    aggregator_feed_enabled: bool = True
    aggregator_feed_per_pass: int = 20
    aggregator_domains_path: str = "/data/aggregator_domains.json"
    aggregator_max_domains: int = 500
```

3. In `load_config()`'s `Config(...)` call, add:
```python
        aggregator_feed_enabled=s.aggregator_feed_enabled,
        aggregator_feed_per_pass=s.aggregator_feed_per_pass,
        aggregator_domains_path=s.aggregator_domains_path,
        aggregator_max_domains=s.aggregator_max_domains,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_config.py -q`
Expected: PASS (all, including the 2 new)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/config.py crawler/tests/test_config.py
git commit -m "feat(crawler): aggregator_feed_* config flags"
```

---

### Task 4: wiring + runner integration

**Files:**
- Modify: `crawler/crawler/wiring.py`
- Modify: `crawler/crawler/runner.py`
- Test: `crawler/tests/test_wiring.py` (append), `crawler/tests/test_runner.py` (append)

**Interfaces:**
- Consumes: `AggregatorDomainStore`/`AggregatorDomainFeed` (Task 1), harvester `aggregator_store`/`aggregator_max_domains` (Task 2), `Config.aggregator_*` (Task 3).
- Produces: `Runner.__init__` gains `aggregator_feed=None`; `build_runner` builds the store+feed, injects the store into the harvester, passes the feed to `Runner`, which unions its candidates in the interleave.

- [ ] **Step 1: Write the failing tests**

```python
# append to crawler/tests/test_runner.py
class _StubAgg:
    def __init__(self, cands): self._cands = cands
    def candidates(self, known): return list(self._cands)


def test_runner_unions_aggregator_feed_candidates():
    src = {"id": 1, "type": "website", "name": "S", "url_or_handle": "https://s.ua"}
    api = FakeApi([src])
    hv = _RecordingHarvester()
    cand = SourceCandidate(name="biz.ua", type="website", url_or_handle="https://biz.ua")
    runner = Runner(api, {"website": FakeFetcher([])}, get_extractor("heuristic"), _rl(),
                    harvester=hv, aggregator_feed=_StubAgg([cand]))
    runner.run()
    assert any(c.url_or_handle == "https://biz.ua" for c in hv.candidates)
```

```python
# append to crawler/tests/test_wiring.py
from crawler.discovery.aggregator_feed import AggregatorDomainFeed


def test_build_runner_wires_aggregator_feed(tmp_path):
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=False, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={}, brand_feed_enabled=False, osm_feed_enabled=False,
        aggregator_feed_enabled=True, aggregator_domains_path=str(tmp_path / "agg.json"))
    runner = build_runner(cfg)
    assert isinstance(runner._aggregator_feed, AggregatorDomainFeed)
    assert runner._harvester is not None and runner._harvester._aggregator_store is not None


def test_build_runner_aggregator_feed_disabled(tmp_path):
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=False, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={}, brand_feed_enabled=False, osm_feed_enabled=False,
        aggregator_feed_enabled=False)
    runner = build_runner(cfg)
    assert runner._aggregator_feed is None
```

Note: the enabled wiring test relies on the harvester being built. With `brand_feed_enabled=False`, `osm_feed_enabled=False`, `active_discovery=False`, the harvester is still built because `domain_rating_enabled` defaults True (so `domain_feed` is not None → the existing harvester build-gate fires). The aggregator store is injected there.

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_runner.py tests/test_wiring.py -q -k aggregator`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'aggregator_feed'` (runner) / `AttributeError: ... '_aggregator_feed'` (wiring)

- [ ] **Step 3: Write minimal implementation**

In `crawler/crawler/runner.py`:

1. Extend `Runner.__init__` — append after `osm_feed=None`:
```python
                 osm_feed=None, aggregator_feed=None):
```
and store it:
```python
        self._aggregator_feed = aggregator_feed
```

2. In `run()`, in the `feeds` list build (inside `if self._harvester is not None:`), after the `osm_feed` append:
```python
                if self._aggregator_feed is not None:
                    feeds.append(self._aggregator_feed.candidates(known))
```

In `crawler/crawler/wiring.py`:

3. Add the import (with the other discovery imports):
```python
from crawler.discovery.aggregator_feed import AggregatorDomainFeed, AggregatorDomainStore
```

4. Build the store + feed. After the `osm_feed` build block (`if config.osm_feed_enabled: osm_feed = _build_osm_feed(config)`) and BEFORE the harvester build-gate, add:
```python
    aggregator_store = None
    aggregator_feed = None
    if config.aggregator_feed_enabled:
        aggregator_store = AggregatorDomainStore.load(config.aggregator_domains_path)
        aggregator_feed = AggregatorDomainFeed(
            aggregator_store, per_pass=config.aggregator_feed_per_pass)
```

5. Inject the store into the harvester — in the `ActiveHarvester(...)` construction inside the build-gate, add the two kwargs:
```python
                                    aggregator_min_outbound=config.aggregator_min_outbound,
                                    aggregator_store=aggregator_store,
                                    aggregator_max_domains=config.aggregator_max_domains)
```

6. Pass the feed to the `Runner(...)` call — add the kwarg:
```python
                  osm_feed=osm_feed, aggregator_feed=aggregator_feed)
```

- [ ] **Step 4: Run tests to verify they pass, then the full suite**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_runner.py tests/test_wiring.py -q`
Expected: PASS (all, including the 3 new)

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — 403 baseline + new tests, all green.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/runner.py crawler/crawler/wiring.py crawler/tests/test_runner.py crawler/tests/test_wiring.py
git commit -m "feat(crawler): wire aggregator domain feed into harvester (capture) + Runner (feed)"
```

---

## Final verification (after all tasks)

- [ ] Full suite green from `crawler/`: `./.venv/Scripts/python.exe -m pytest -q`
- [ ] Request opus whole-branch review (superpowers:requesting-code-review) before merge.
- [ ] Merge to `main` (--no-ff), delete branch, push, rebuild crawler container (`--no-deps`), update RESUME/memory.

## Self-review notes (traceability to spec)

- Spec §A capture → Task 2. §B store → Task 1. §C feed → Task 1. §D wiring → Task 4. §E config → Task 3.
- Byte-eq off (`aggregator_feed_enabled=False`) → `test_build_runner_aggregator_feed_disabled` + `test_no_store_is_byte_equivalent`.
- Decoupling (capture writes end-of-pass, feed reads next pass) → structural: store injected into both harvester and feed on the same path; feed reads at candidate-build time, harvester writes during harvest.
- Blocklisted-only source + no salvage regression → `test_blocklisted_page_captures_outbound_hosts` (api.offers == []) + `test_non_blocklisted_page_does_not_capture`.
