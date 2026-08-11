# DDG-independent discovery survives global backoff — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `run_active()` still perform all DDG-independent discovery (drain + 4 feeds + harvest) while DDG is in global backoff, skipping only the DDG legs (due-walk search + `site:`).

**Architecture:** Add a network-independent `SearchPass.drain()` (extracted from `run()`, behaviour-preserving). Thread a `ddg_allowed` flag through `Runner.run_active`: when `True` it calls the full `SearchPass.run` + `site:` arm (unchanged); when `False` it calls only `drain()` and skips `site:`. The scheduler's global-backoff branch calls `run_active(ddg_allowed=False)` instead of skipping the pass.

**Tech Stack:** Python 3.12, pytest. No new dependencies.

## Global Constraints

- Run tests from `crawler/`: `./.venv/Scripts/python.exe -m pytest -q` (Windows venv).
- TDD: failing test first, minimal impl, green, commit.
- `ddg_allowed` defaults to `True` everywhere → the existing (non-backoff) path is byte-identical; `SearchPass.run()` keeps its exact current behaviour and signature.
- No new deps; crawler ships via canonical Docker rebuild (pypi reachable).
- Out of scope: DDG anti-throttle/backoff logic, passive cadence, feed-cursor consume-commit (separate DEFERRED plan).

---

### Task 1: `SearchPass.drain()` — network-independent cache re-surface

**Files:**
- Modify: `crawler/crawler/discovery/search_pass.py`
- Test: `crawler/tests/test_search_pass.py`

**Interfaces:**
- Produces: `SearchPass.drain() -> list[SourceCandidate]` — returns cached-but-unharvested candidates (each tagged `origin_key`), makes no provider call, does not touch `grid_cursor`; returns `[]` when `ttl_seconds <= 0`. `SearchPass.run(known)` is unchanged externally and now calls `drain()` internally.

- [ ] **Step 1: Write the failing tests**

Append to `crawler/tests/test_search_pass.py`:

```python
def test_drain_returns_unharvested_without_searching(tmp_path):
    st = SearchState(str(tmp_path / "s.json"), clock=lambda: 1000.0)
    st.cache_put("імплантація знижка убд",
                 [SourceCandidate(name="edclinic", type="website",
                                  url_or_handle="https://edclinic.com.ua")])
    ddg = _Plan(include_pins=False, ok=True)
    sp = SearchPass([ddg], st, QueryGrid([f"q{i}" for i in range(3)]),
                    block_size=2, ttl_seconds=10_000.0)
    out = sp.drain()
    assert [c.url_or_handle for c in out] == ["https://edclinic.com.ua"]
    assert out[0].origin_key == "імплантація знижка убд"
    assert ddg.discovery.calls == []            # drain must NOT call the provider


def test_drain_ttl_zero_is_empty(tmp_path):
    st = SearchState(str(tmp_path / "s.json"), clock=lambda: 1000.0)
    st.cache_put("kw", [SourceCandidate(name="x", type="website",
                                        url_or_handle="https://x.example")])
    sp = SearchPass([_Plan(False, True)], st, QueryGrid(["q0"]),
                    block_size=1, ttl_seconds=0.0)
    assert sp.drain() == []                      # ttl<=0 => no drain (matches run())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_search_pass.py -q -k drain`
Expected: FAIL — `AttributeError: 'SearchPass' object has no attribute 'drain'`

- [ ] **Step 3: Add `drain()` and make `run()` reuse it**

In `crawler/crawler/discovery/search_pass.py`, add the method (place it just above `run`):

```python
    def drain(self) -> list[SourceCandidate]:
        """Step 1 in isolation: re-surface cached-but-unharvested candidates. No network,
        does not touch grid_cursor — safe to call during global backoff when the DDG search
        leg is skipped. ttl<=0 => no drain (mirrors run())."""
        if self._ttl <= 0:
            return []
        out: list[SourceCandidate] = []
        for _kw, cands in self._state.unharvested(self._ttl):
            out.extend(cands)
        return out
```

Then in `run()`, replace the inline drain block:

```python
        # 1) DRAIN: re-surface cached-but-unharvested candidates (no DDG re-search).
        if self._ttl > 0:
            for _kw, cands in self._state.unharvested(self._ttl):
                out.extend(cands)
```

with a call to the new method:

```python
        # 1) DRAIN: re-surface cached-but-unharvested candidates (no DDG re-search).
        out.extend(self.drain())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_search_pass.py -q`
Expected: PASS — all SearchPass tests green (drain + existing run/due-walk tests, since `run()` behaviour is preserved).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/search_pass.py crawler/tests/test_search_pass.py
git commit -m "feat(crawler): SearchPass.drain() — network-independent cache re-surface"
```

---

### Task 2: `Runner.run_active(ddg_allowed)` — gate DDG legs behind the flag

**Files:**
- Modify: `crawler/crawler/runner.py:93` (`run_active`)
- Test: `crawler/tests/test_runner_discovery.py`

**Interfaces:**
- Consumes: `SearchPass.drain()` and `SearchPass.run(known)` (Task 1).
- Produces: `Runner.run_active(ddg_allowed: bool = True) -> dict`. `ddg_allowed=True` = current behaviour (`search_pass.run` + `site:` arm). `ddg_allowed=False` = `search_pass.drain()` only, `site:` arm skipped; feeds + harvest + mark-consumed run in both.

- [ ] **Step 1: Write the failing tests**

In `crawler/tests/test_runner_discovery.py`, replace `FakeSearchPass` with a version that also exposes `drain()` and records whether `run()` was called, and add site-query fakes + the new tests:

```python
class FakeSearchPass:
    def __init__(self, cands, drain_cands=None):
        self._cands = cands
        self._drain = drain_cands or []
        self.called_with = None
        self.ran = False
    def run(self, known):
        self.ran = True
        self.called_with = set(known)
        return self._cands
    def drain(self):
        return list(self._drain)
    def provider_for_site_query(self): return None


class FakeDiscovery:
    def __init__(self): self.ran = False
    def run(self, queries, known): self.ran = True; return []


class FakeSitePlanner:
    def next_batch(self, reg, budget, cursor): return (["site:x знижка"], cursor + 1)


class FakeSiteState:
    def __init__(self): self.site_cursor = 0
    def set_site_cursor(self, v): self.site_cursor = v


class FakeRegistry:
    def top(self, n, known_hosts, cooldown): return ["x.example"]
    def prune(self, a, b): pass
    def save(self): pass


def _runner_with_site(api, search_pass, harvester, discovery):
    return Runner(api, {}, extractor=None, rate_limiter=None, search_pass=search_pass,
                  harvester=harvester, discovery=discovery,
                  site_planner=FakeSitePlanner(), site_state=FakeSiteState(),
                  domain_registry=FakeRegistry())


def test_run_active_backoff_drains_without_searching():
    api = FakeApi()
    searched = SourceCandidate(name="s", type="website", url_or_handle="https://s.example")
    drained = SourceCandidate(name="d", type="website", url_or_handle="https://d.example")
    sp = FakeSearchPass([searched], drain_cands=[drained])
    h = FakeHarvester()
    _runner(api, sp, h).run_active(ddg_allowed=False)
    assert sp.ran is False                       # DDG due-walk search NOT called
    assert h.calls == [[drained]]                # only the drained candidate harvested


def test_run_active_ddg_allowed_runs_full_search():
    api = FakeApi()
    searched = SourceCandidate(name="s", type="website", url_or_handle="https://s.example")
    sp = FakeSearchPass([searched])
    h = FakeHarvester()
    _runner(api, sp, h).run_active(ddg_allowed=True)
    assert sp.ran is True
    assert h.calls == [[searched]]


def test_run_active_backoff_skips_site_queries():
    disc = FakeDiscovery()
    _runner_with_site(FakeApi(), FakeSearchPass([], drain_cands=[]),
                      FakeHarvester(), disc).run_active(ddg_allowed=False)
    assert disc.ran is False                      # site: DDG queries skipped under backoff


def test_run_active_ddg_allowed_runs_site_queries():
    disc = FakeDiscovery()
    _runner_with_site(FakeApi(), FakeSearchPass([], drain_cands=[]),
                      FakeHarvester(), disc).run_active(ddg_allowed=True)
    assert disc.ran is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_runner_discovery.py -q -k "backoff or ddg_allowed"`
Expected: FAIL — `run_active()` takes no `ddg_allowed` argument (TypeError).

- [ ] **Step 3: Add the `ddg_allowed` parameter and gate the DDG legs**

In `crawler/crawler/runner.py`, change the `run_active` signature and docstring:

```python
    def run_active(self, ddg_allowed: bool = True) -> dict:
        """Discovery of NEW domains: feeds + site: + harvester. Never crawls a host that
        is already an active source (published/approved) — passive owns those.

        ddg_allowed=False (global backoff): run everything DDG-INDEPENDENT — the cache
        drain, all four feeds, harvest — and skip only the DDG legs (due-walk search +
        site:). Default True = full pass (byte-identical to before)."""
```

Replace the search-pass feed line:

```python
            if self._search_pass is not None:
                feeds.append(self._search_pass.run(known))
```

with:

```python
            if self._search_pass is not None:
                # DDG-independent drain always runs; the DDG due-walk search only when allowed.
                feeds.append(self._search_pass.run(known) if ddg_allowed
                             else self._search_pass.drain())
```

Gate the `site:` arm on the flag — change its condition:

```python
            if (self._site_planner is not None and self._site_state is not None
                    and self._discovery is not None and self._domain_registry is not None):
```

to:

```python
            if (ddg_allowed and self._site_planner is not None and self._site_state is not None
                    and self._discovery is not None and self._domain_registry is not None):
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_runner_discovery.py tests/test_runner.py -q`
Expected: PASS — new backoff/ddg tests green; existing `run()`-path tests unaffected (default `ddg_allowed=True` still calls `search_pass.run`).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/runner.py crawler/tests/test_runner_discovery.py
git commit -m "feat(crawler): run_active(ddg_allowed) — drain+feeds always, DDG legs gated"
```

---

### Task 3: Scheduler runs DDG-independent active pass during backoff

**Files:**
- Modify: `crawler/crawler/scheduler.py:17-28` (`step`)
- Test: `crawler/tests/test_scheduler.py`

**Interfaces:**
- Consumes: `Runner.run_active(ddg_allowed)` (Task 2).
- Produces: no new symbols; `step` now calls `run_active(ddg_allowed=False)` in the global-backoff branch and `run_active(ddg_allowed=True)` in the normal branch.

- [ ] **Step 1: Update the fake + affected tests, add the new one**

In `crawler/tests/test_scheduler.py`, replace the `_Runner` fake:

```python
class _Runner:
    def __init__(self):
        self.calls = []
        self.ddg_flags = []

    def run_active(self, ddg_allowed=True):
        self.calls.append("active")
        self.ddg_flags.append(ddg_allowed)

    def run_passive(self):
        self.calls.append("passive")
```

Update `test_not_backed_off_runs_active` to assert the flag, and replace the two backed-off tests:

```python
def test_not_backed_off_runs_active():
    r = _Runner()
    assert step(r, _State(False), _Passive(), **_kw()) == 60
    assert r.calls == ["active"] and r.ddg_flags == [True]


def test_backed_off_passive_due_runs_active_then_passive():
    r, p = _Runner(), _Passive(due=True)
    assert step(r, _State(True, secs=500), p, **_kw()) == 500
    assert r.calls == ["active", "passive"] and p.marked == 1
    assert r.ddg_flags == [False]              # active pass ran DDG-independent


def test_backed_off_passive_not_due_runs_ddg_independent_active():
    r = _Runner()
    assert step(r, _State(True, secs=9999), _Passive(due=False), **_kw()) == 1800
    assert r.calls == ["active"] and r.ddg_flags == [False]
```

Update `test_run_loop_bounded_iterations` expectation (active now also runs in the backed-off iteration):

```python
def test_run_loop_bounded_iterations():
    r, slept = _Runner(), []
    states = iter([_State(True, 100), _State(False)])
    run_loop(r, lambda: next(states), _Passive(due=True),
             sleep=slept.append, iterations=2, **_kw())
    assert r.calls == ["active", "passive", "active"] and slept == [100, 60]
```

Update the `Boom` fake in `test_run_loop_survives_pass_error` to accept the kwarg:

```python
    class Boom:
        def run_active(self, ddg_allowed=True):
            raise RuntimeError("boom")

        def run_passive(self):
            pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_scheduler.py -q`
Expected: FAIL — backed-off tests expect an `"active"` call the current `step` does not make.

- [ ] **Step 3: Add the DDG-independent active pass to the backoff branch**

In `crawler/crawler/scheduler.py`, change `step` so the global-backoff branch runs the active pass DDG-independently, and make the normal branch's flag explicit:

```python
    if state is not None and state.in_global_backoff():
        runner.run_active(ddg_allowed=False)      # DDG-independent discovery survives backoff
        if passive_schedule is None or passive_schedule.due():
            runner.run_passive()
            if passive_schedule is not None:
                passive_schedule.mark()
        return min(state.seconds_until_allowed(), backoff_max_sleep)
    if passive_schedule is not None and passive_schedule.overdue(hard_factor):
        runner.run_passive()
        passive_schedule.mark()
        return max(active_delay, MIN_ACTIVE_DELAY)
    runner.run_active(ddg_allowed=True)
    return max(active_delay, MIN_ACTIVE_DELAY)
```

Update the docstring's first bullet to reflect the new behaviour:

```python
    - Global backoff active: DDG is unusable, so run the DDG-INDEPENDENT part of the active
      pass (drain + feeds + harvest; no DDG search/site:) plus the passive pass (when its
      cadence is due), then sleep until the backoff lifts (capped).
```

- [ ] **Step 4: Run the full crawler suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — entire crawler suite green (baseline 620 + the new tests).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/scheduler.py crawler/tests/test_scheduler.py
git commit -m "feat(crawler): scheduler runs DDG-independent active pass during backoff"
```

---

### Task 4: Deploy + live verification (no code; closes the morning drain)

**Files:** none (Docker rebuild + live checks).

**Interfaces:**
- Consumes: merged branch on `main`.

- [ ] **Step 1: Merge the branch (after review)**

```bash
git checkout main && git merge --ff-only feat/ddg-independent-during-backoff
```

- [ ] **Step 2: Canonical rebuild + restart the crawler**

```bash
docker compose build crawler && docker compose up -d crawler
```
Expected: clean build (pypi reachable), container `Up`.

- [ ] **Step 3: Confirm DDG is still in global backoff (the test window)**

```bash
docker exec ubd_probe-crawler-1 python -c "import json,time; d=json.load(open('/data/search_state.json',encoding='utf-8')); print('in_backoff', time.time() < d.get('next_allowed_at',0))"
```
Expected: `in_backoff True` (if `False`, the fix is exercised on the next normal pass instead — still valid).

- [ ] **Step 4: Verify the DDG-independent active pass runs under backoff**

```bash
docker logs --since 10m ubd_probe-crawler-1 2>&1 | grep -aiE "crawl summary|blocked-hosts|approved-offers|sleeping"
```
Expected: a `crawl summary: {...}` line appears while the scheduler is still sleeping toward `next_allowed_at` — i.e. `run_active` fired during backoff (before the fix, only `sleeping` lines appeared).

- [ ] **Step 5: Confirm the 13 dentistry orphans finally drained**

```bash
docker exec ubd_probe-crawler-1 python -c "import json; d=json.load(open('/data/search_state.json',encoding='utf-8')); print('harvested=False left:', len([k for k,e in d['cache'].items() if e.get('harvested') is False]))"
```
Expected: fewer than 13 (drain consumed them; fully consumed → 0). Cross-check the admin moderation queue for new dentistry pending offers.
