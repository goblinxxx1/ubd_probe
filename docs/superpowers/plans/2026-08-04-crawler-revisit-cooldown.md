# Track B · Phase 1 — Domain revisit cooldown (walk down the list)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or executing-plans. Steps use `- [ ]`.

**Goal:** The active crawler re-crawls an already-visited domain at most once per cooldown (21 days); instead of re-hammering the top productive domains every pass, `DomainFeed`/`site:` walk further down the list to not-recently-visited domains.

**Architecture:** `domain_registry` already stores per-host `last_seen`. Add `seen_within()` and a cooldown filter in `top()`; `DomainFeed` and the `site:` pool pass the cooldown so they emit only not-recently-visited domains (walk down); `ActiveHarvester` gets a cooldown gate as a belt for the other feeds. Config knob `active_revisit_cooldown_days` (default 21); wiring threads it to the three consumers.

**Tech Stack:** Python, crawler pytest.

## Global Constraints
- crawler-only; no backend/admin changes.
- Cooldown source = `domain_registry` (active-visit ledger). `cooldown_seconds=0` ⇒ byte-equivalent to current behaviour (no exclusion) — for tests/OFF.
- TDD test-first; run `./.venv/Scripts/python.exe -m pytest -q` from `crawler/`.
- Deploy env: `ACTIVE_REVISIT_COOLDOWN_DAYS=21`.

---

### Task 1: DomainRegistry — `seen_within` + cooldown filter in `top`

**Files:**
- Modify: `crawler/crawler/discovery/domain_registry.py`
- Test: `crawler/tests/test_domain_registry.py`

**Interfaces:**
- Produces: `DomainRegistry.seen_within(host, seconds) -> bool`; `DomainRegistry.top(n, known_hosts, cooldown_seconds=0) -> list[str]` (excludes hosts with `now-last_seen < cooldown_seconds`).

- [ ] **Step 1: Write failing tests**

Add to `crawler/tests/test_domain_registry.py`:
```python
def test_seen_within_reflects_last_seen(tmp_path):
    from crawler.discovery.domain_registry import DomainRegistry
    t = {"v": 1000.0}
    r = DomainRegistry(str(tmp_path / "r.json"), clock=lambda: t["v"])
    r.record("a.ua", offers=1, errors=0)   # last_seen = 1000
    t["v"] = 1000.0 + 50
    assert r.seen_within("a.ua", 100) is True
    assert r.seen_within("a.ua", 40) is False
    assert r.seen_within("never.ua", 100) is False


def test_top_excludes_recently_seen_when_cooldown_set(tmp_path):
    from crawler.discovery.domain_registry import DomainRegistry
    t = {"v": 1000.0}
    r = DomainRegistry(str(tmp_path / "r.json"), clock=lambda: t["v"])
    r.record("hi.ua", offers=5, errors=0)    # highest score, seen at 1000
    t["v"] = 1000.0 + 10
    r.record("lo.ua", offers=1, errors=0)    # lower score, seen at 1010
    t["v"] = 1000.0 + 20
    # cooldown 100s -> both seen within 100 -> excluded
    assert r.top(10, set(), cooldown_seconds=100) == []
    # cooldown 0 -> normal (score order)
    assert r.top(10, set(), cooldown_seconds=0) == ["hi.ua", "lo.ua"]
    t["v"] = 1000.0 + 150
    # now hi.ua seen 150s ago (>100 -> eligible), lo.ua 140s ago (>100 -> eligible)
    assert r.top(10, set(), cooldown_seconds=100) == ["hi.ua", "lo.ua"]
```

- [ ] **Step 2: Run — fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_domain_registry.py -k "seen_within or cooldown" -v`
Expected: FAIL (`seen_within` missing; `top` has no `cooldown_seconds`).

- [ ] **Step 3: Implement**

In `crawler/crawler/discovery/domain_registry.py`, add `seen_within` and extend `top`:
```python
    def seen_within(self, host, seconds) -> bool:
        e = self._data["domains"].get(_host(host))
        return e is not None and (self._clock() - e["last_seen"]) < seconds

    def top(self, n, known_hosts, cooldown_seconds=0):
        now = self._clock()
        rows = [(h, e["score"]) for h, e in self._data["domains"].items()
                if e["score"] >= self._promote and h not in known_hosts
                and not (cooldown_seconds and now - e["last_seen"] < cooldown_seconds)]
        rows.sort(key=lambda r: (-r[1], r[0]))
        return [h for h, _ in rows[:max(0, int(n))]]
```

- [ ] **Step 4: Run — passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_domain_registry.py -q`
Expected: PASS (new + existing).

- [ ] **Step 5: Commit**
```bash
git add crawler/crawler/discovery/domain_registry.py crawler/tests/test_domain_registry.py
git commit -m "feat(crawler): DomainRegistry.seen_within + cooldown filter in top()"
```

---

### Task 2: DomainFeed + site: pool honour the cooldown (walk down the list)

**Files:**
- Modify: `crawler/crawler/discovery/domain_feed.py`
- Modify: `crawler/crawler/runner.py`
- Test: `crawler/tests/test_domain_feed.py`, `crawler/tests/test_runner.py`

**Interfaces:**
- Consumes: `DomainRegistry.top(n, known_hosts, cooldown_seconds)` (Task 1).
- Produces: `DomainFeed(registry, per_pass=8, cooldown_seconds=0)`; `Runner(..., revisit_cooldown_seconds=0)` used in the site: `top()` call.

- [ ] **Step 1: Write failing test (DomainFeed)**

Add to `crawler/tests/test_domain_feed.py`:
```python
def test_domain_feed_passes_cooldown_to_top(tmp_path):
    from crawler.discovery.domain_feed import DomainFeed
    t = {"v": 1000.0}
    r = _reg(tmp_path)
    r._clock = lambda: t["v"]           # override clock for the test
    r.record("recent.ua", offers=5, errors=0)   # seen at 1000
    t["v"] = 1000.0 + 10
    hosts = [c.url_or_handle for c in DomainFeed(r, per_pass=8, cooldown_seconds=100).candidates(set())]
    assert hosts == []                  # within cooldown -> excluded
```

- [ ] **Step 2: Run — fails** (`pytest tests/test_domain_feed.py::test_domain_feed_passes_cooldown_to_top`) — `DomainFeed` has no `cooldown_seconds`.

- [ ] **Step 3: Implement DomainFeed**

In `crawler/crawler/discovery/domain_feed.py`:
```python
class DomainFeed:
    def __init__(self, registry, per_pass=8, cooldown_seconds=0):
        self._registry = registry
        self._per_pass = per_pass
        self._cooldown = cooldown_seconds

    def candidates(self, known_hosts):
        out = []
        for host in self._registry.top(self._per_pass, known_hosts, self._cooldown):
            if is_blocked_host(host):
                continue
            out.append(SourceCandidate(
                name=host, type="website", url_or_handle=f"https://{host}",
                discovered_from_source_id=None,
                discovery_note=f"domain-rating:{host}"))
        return out
```

- [ ] **Step 4: Write failing test (runner site: cooldown)**

Add to `crawler/tests/test_runner.py`:
```python
def test_site_query_pool_respects_revisit_cooldown(tmp_path):
    api = FakeApi([{"id": 1, "type": "website", "name": "S", "url_or_handle": "http://x"}])
    t = {"v": 1000.0}
    reg = DomainRegistry(str(tmp_path / "r.json"), clock=lambda: t["v"])
    reg.record("proven.ua", offers=3, errors=0)   # seen at 1000
    t["v"] = 1000.0 + 10
    state = SearchState(str(tmp_path / "s.json"), clock=lambda: 1.0)
    disc = _MutatingDiscovery()
    runner = Runner(api, {"website": FakeFetcher([])}, get_extractor("heuristic"), _rl(),
                    harvester=_RecordingHarvester(), discovery=disc, domain_registry=reg,
                    site_planner=SiteQueryPlanner(terms=("знижка",)),
                    site_state=state, site_query_budget=5, revisit_cooldown_seconds=100)
    runner.run_active()
    qs = " ".join(q for call in disc.calls for q in call)
    assert "proven.ua" not in qs        # within cooldown -> not site-queried
```

- [ ] **Step 5: Run — fails** (`Runner` has no `revisit_cooldown_seconds`; proven.ua still queried).

- [ ] **Step 6: Implement Runner**

In `crawler/crawler/runner.py` `__init__`, add param + store:
```python
                 passive_schedule=None, now=time.time, revisit_cooldown_seconds=0):
```
```python
        self._revisit_cooldown = revisit_cooldown_seconds
```
In `run_active`, the site: branch, pass cooldown to `top` (combine with the existing blocklist filter from Track A):
```python
                reg = [h for h in self._domain_registry.top(
                           self._site_query_budget, known_hosts, self._revisit_cooldown)
                       if not is_blocked_host(h)]
```

- [ ] **Step 7: Run — passes + full suite**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_domain_feed.py tests/test_runner.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**
```bash
git add crawler/crawler/discovery/domain_feed.py crawler/crawler/runner.py crawler/tests/test_domain_feed.py crawler/tests/test_runner.py
git commit -m "feat(crawler): DomainFeed + site: pool honour revisit cooldown (walk down the list)"
```

---

### Task 3: ActiveHarvester cooldown gate (belt for other feeds) + config + wiring

**Files:**
- Modify: `crawler/crawler/discovery/harvest.py`
- Modify: `crawler/crawler/config.py`, `crawler/crawler/wiring.py`
- Test: `crawler/tests/test_active_harvest.py`, `crawler/tests/test_config.py`

**Interfaces:**
- Consumes: `DomainRegistry.seen_within` (Task 1).
- Produces: `ActiveHarvester(..., revisit_cooldown_seconds=0)`; config `active_revisit_cooldown_days` (default 21); wiring threads `days*86400` into harvester, `DomainFeed`, and `Runner`.

- [ ] **Step 1: Write failing test (harvester gate)**

Add to `crawler/tests/test_active_harvest.py`:
```python
def test_recently_seen_website_candidate_skipped(tmp_path):
    from crawler.discovery.domain_registry import DomainRegistry
    api = FakeApi()
    fetched = []
    class CountingFetcher:
        def fetch(self, source, k): fetched.append(source["url_or_handle"]); return [], None
    t = {"v": 1000.0}
    reg = DomainRegistry(str(tmp_path / "r.json"), clock=lambda: t["v"])
    reg.record("seen.example", offers=1, errors=0)   # last_seen = 1000
    t["v"] = 1000.0 + 10
    h = ActiveHarvester(api, {"website": CountingFetcher()}, GateExtractor(),
                        rate_limiter=None, fetch_budget=5,
                        domain_registry=reg, revisit_cooldown_seconds=100)
    h.harvest([_cand(url="https://seen.example"), _cand(url="https://fresh.example")],
              cats=None, known=set(), summary=_summary())
    assert fetched == ["https://fresh.example"]   # recently-seen skipped, new fetched
```

- [ ] **Step 2: Run — fails** (`ActiveHarvester` has no `revisit_cooldown_seconds`; seen.example fetched).

- [ ] **Step 3: Implement harvester gate**

In `crawler/crawler/discovery/harvest.py` `__init__`, add param + store (near the other kwargs):
```python
                 aggregator_max_domains=500, revisit_cooldown_seconds=0):
```
```python
        self._revisit_cooldown = revisit_cooldown_seconds
```
In `harvest`, after the blocklist gate and before the `known`/`known_hosts` checks, add:
```python
            # Revisit cooldown: never re-crawl a domain seen within the cooldown window
            # (belt for feeds other than DomainFeed/site:, which already filter via top()).
            if (cand.type == "website" and self._revisit_cooldown and self._registry is not None
                    and self._registry.seen_within(_host(cand.url_or_handle), self._revisit_cooldown)):
                continue
```

- [ ] **Step 4: Write failing test (config default)**

Add to `crawler/tests/test_config.py`:
```python
def test_active_revisit_cooldown_default_and_override(monkeypatch, tmp_path):
    from crawler.config import load_config
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ACTIVE_REVISIT_COOLDOWN_DAYS", raising=False)
    assert load_config().active_revisit_cooldown_days == 21
    monkeypatch.setenv("ACTIVE_REVISIT_COOLDOWN_DAYS", "7")
    assert load_config().active_revisit_cooldown_days == 7
```

- [ ] **Step 5: Run — fails** (config field missing).

- [ ] **Step 6: Implement config + wiring**

In `crawler/crawler/config.py`, add to BOTH the `_RawSettings` class and the `Config` dataclass (near `freshness_ttl_days`):
```python
    active_revisit_cooldown_days: int = 21
```
and in `load_config(...)` passthrough:
```python
        active_revisit_cooldown_days=s.active_revisit_cooldown_days,
```
In `crawler/crawler/wiring.py`, compute once and thread into the three consumers:
```python
    revisit_cooldown = config.active_revisit_cooldown_days * 86400
```
- pass `cooldown_seconds=revisit_cooldown` to `DomainFeed(...)` construction;
- pass `revisit_cooldown_seconds=revisit_cooldown` to `ActiveHarvester(...)`;
- pass `revisit_cooldown_seconds=revisit_cooldown` to `Runner(...)`.

- [ ] **Step 7: Run — passes + full suite**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_active_harvest.py tests/test_config.py tests/test_wiring.py -q` then `./.venv/Scripts/python.exe -m pytest -q`
Expected: all green.

- [ ] **Step 8: Commit**
```bash
git add crawler/crawler/discovery/harvest.py crawler/crawler/config.py crawler/crawler/wiring.py crawler/tests/test_active_harvest.py crawler/tests/test_config.py
git commit -m "feat(crawler): active revisit-cooldown gate + config/wiring (default 21d)"
```

---

## Deploy
Canonical crawler rebuild; set `ACTIVE_REVISIT_COOLDOWN_DAYS=21` in `crawler/.env`; restart. Live-verify: DomainFeed/site: no longer re-emit the top domains every pass (they walk down); a domain seen <21d ago is skipped.

## Self-Review notes
- Spec §5 "Domain revisit cooldown" → Tasks 1-3 (seen_within + top cooldown; DomainFeed/site: walk-down; harvester belt; config/wiring).
- No placeholders; complete code per step.
- Names consistent: `seen_within`, `top(..., cooldown_seconds)`, `revisit_cooldown_seconds`, `active_revisit_cooldown_days`.
- `cooldown_seconds=0` byte-equivalent (existing tests keep passing).
