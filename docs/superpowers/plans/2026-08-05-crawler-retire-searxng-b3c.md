# Retire SearXNG + B3c due-query walking — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove SearXNG entirely (code, tests, config, infra), collapse the B2 dual-provider block-partition/swap to a single-provider grid walk, then add B3c due-query walking (each pass searches only cache-stale phrases).

**Architecture:** Crawler-only, two sequential phases with a checkpoint. Phase 1 is a pure refactor + deletion that provably leaves DDG behaviour byte-identical (with one provider the current swap already degenerates to a plain walk). Phase 2 adds a freshness predicate and rewrites the walk to skip cache-fresh phrases.

**Tech Stack:** Python 3.12, pytest. Run tests from `crawler/` with `./.venv/Scripts/python.exe -m pytest -q` (Windows).

## Global Constraints

- **Crawler-only.** Do not touch backend/admin/public.
- **DDG invariant (Phase 1):** the DuckDuckGo search path (`RotatingDdgProvider`, `SearchCache`, anti-throttle, backoff, cache, backends) must remain byte-identical. No crashes, no interruptions to active search.
- **TDD:** write the failing test first, watch it fail, implement minimally, watch it pass, commit.
- **No dead code.** Remove `search_queries_per_pass` (unused since B2) along with its tests.
- **Historical docs untouched:** do NOT edit dated spec/plan files under `docs/superpowers/` for B2/B3. Only `RUN.md` / `README-docker.md` get searxng removed.
- Test command (always from `crawler/`): `./.venv/Scripts/python.exe -m pytest -q`
- Single run cursor is `grid_cursor` (already exists in `SearchState`). `block_cursor`, `cycle`, `searxng_cursor` are removed.
- Per-pass batch size stays `config.search_block_size` (=15). `search_cache_ttl_hours` supplies the freshness TTL in Phase 2.

---

## PHASE 1 — Retire SearXNG + collapse to single-provider walk

### Task 1: Strip block-partition state (`block_cursor`, `cycle`, `searxng_cursor`)

**Files:**
- Modify: `crawler/crawler/discovery/search_state.py`
- Test: `crawler/tests/test_search_state.py`

**Interfaces:**
- Produces: `SearchState` keeps `grid_cursor` (int property) + `set_grid_cursor(int)`; NO `block_cursor`, `cycle`, `searxng_cursor` anymore.

- [ ] **Step 1: Update tests — remove obsolete-field tests, add legacy-load regression**

In `crawler/tests/test_search_state.py`, DELETE these two tests entirely:
`test_searxng_cursor_sentinel_default_and_persist` (lines ~192-198) and
`test_block_cursor_and_cycle_persist` (lines ~201-209).

Then ADD this regression test (proves a live state file carrying the old keys still loads and `grid_cursor` works — the DDG-safety guarantee for deploy):

```python
def test_legacy_state_with_removed_cursors_loads(tmp_path):
    import json as _json
    path = tmp_path / "legacy.json"
    path.write_text(_json.dumps({"version": 1, "cursor": 0, "grid_cursor": 80,
                                 "block_cursor": 240, "cycle": 0, "searxng_cursor": 153,
                                 "next_allowed_at": 0.0, "backends": {}, "cache": {}}),
                    encoding="utf-8")
    st = SearchState.load(str(path), clock=Clock())
    assert st.grid_cursor == 80          # live rotation position preserved
    assert not hasattr(st, "block_cursor")   # removed property
```

- [ ] **Step 2: Run tests to verify the new one fails**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_search_state.py`
Expected: FAIL — `test_legacy_state_with_removed_cursors_loads` fails on `assert not hasattr(st, "block_cursor")` (property still exists).

- [ ] **Step 3: Remove the fields from `search_state.py`**

In `_EMPTY` (top of file) change:
```python
_EMPTY = {"version": 1, "cursor": 0, "grid_cursor": 0, "site_cursor": 0,
          "approved_cursor": 0, "searxng_cursor": -1,
          "block_cursor": 0, "cycle": 0,
          "next_allowed_at": 0.0, "backends": {}, "cache": {}}
```
to:
```python
_EMPTY = {"version": 1, "cursor": 0, "grid_cursor": 0, "site_cursor": 0,
          "approved_cursor": 0,
          "next_allowed_at": 0.0, "backends": {}, "cache": {}}
```

DELETE the entire `block-partition cursor + cycle` block (the `block_cursor` property + `set_block_cursor`, `cycle` property + `set_cycle`) and the `searxng rotation cursor` block (`searxng_cursor` property + `set_searxng_cursor`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_search_state.py`
Expected: PASS (all remaining state tests green).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/search_state.py crawler/tests/test_search_state.py
git commit -m "refactor(crawler): drop block_cursor/cycle/searxng_cursor from SearchState"
```

---

### Task 2: Collapse `SearchPass` to a single-provider grid walk

**Files:**
- Modify: `crawler/crawler/discovery/search_pass.py`
- Test: `crawler/tests/test_search_pass.py`

**Interfaces:**
- Consumes: `SearchState.grid_cursor` / `set_grid_cursor` (Task 1); `QueryGrid.next_batch(n, cursor)`; `merge_queries`.
- Consumes from a plan object: `.discovery.run(keywords, known)`, `.include_pins` (bool), `.succeeded()` (bool). NO `.cursor_key`, NO `.reset()`.
- Produces: `SearchPass.run(known) -> list[SourceCandidate]`; `SearchPass.provider_for_site_query()` returns the single plan's `.discovery` (or None if no plans). `SearchPass.__init__(plans, state, grid, block_size, static_keywords=None)` signature UNCHANGED.

- [ ] **Step 1: Rewrite the tests for single-provider walk**

Replace the whole body of `crawler/tests/test_search_pass.py` with:

```python
from crawler.discovery.search_pass import SearchPass
from crawler.discovery.search_state import SearchState
from crawler.discovery.query_grid import QueryGrid
from crawler.models import SourceCandidate


class _Disc:
    """Fake ActiveDiscovery: records keyword lists, returns one candidate."""
    def __init__(self): self.calls = []
    def run(self, keywords, known):
        self.calls.append(list(keywords))
        return [SourceCandidate(name="c", type="website", url_or_handle="https://c.example")]


class _Plan:
    def __init__(self, include_pins, ok):
        self.discovery = _Disc(); self.include_pins = include_pins; self._ok = ok
    def succeeded(self): return self._ok


def _grid(): return QueryGrid([f"q{i}" for i in range(10)])


def test_single_provider_walks_block_from_grid_cursor_with_pins(tmp_path):
    st = SearchState(str(tmp_path / "s.json"))
    ddg = _Plan(include_pins=True, ok=True)
    sp = SearchPass([ddg], st, _grid(), block_size=3, static_keywords=["пін"])
    sp.run(set())
    assert ddg.discovery.calls == [["q0", "q1", "q2", "пін"]]
    assert st.grid_cursor == 3            # advanced by block_size on success


def test_cursor_advances_across_passes_and_wraps(tmp_path):
    st = SearchState(str(tmp_path / "s.json"))
    ddg = _Plan(include_pins=False, ok=True)
    grid = QueryGrid([f"q{i}" for i in range(6)])
    sp = SearchPass([ddg], st, grid, block_size=3)
    sp.run(set()); assert st.grid_cursor == 3
    sp.run(set()); assert st.grid_cursor == 0     # (3+3) % 6 wrap
    assert ddg.discovery.calls == [["q0", "q1", "q2"], ["q3", "q4", "q5"]]


def test_no_advance_when_provider_fails(tmp_path):
    st = SearchState(str(tmp_path / "s.json"))
    ddg = _Plan(include_pins=True, ok=False)
    sp = SearchPass([ddg], st, _grid(), block_size=3)
    sp.run(set())
    assert st.grid_cursor == 0            # cursor frozen when the pass did not succeed


def test_provider_for_site_query_returns_single_discovery(tmp_path):
    st = SearchState(str(tmp_path / "s.json"))
    ddg = _Plan(include_pins=True, ok=True)
    sp = SearchPass([ddg], st, _grid(), block_size=2)
    assert sp.provider_for_site_query() is ddg.discovery


def test_empty_grid_or_no_plans_is_noop(tmp_path):
    st = SearchState(str(tmp_path / "s.json"))
    assert SearchPass([], st, _grid(), block_size=3).run(set()) == []
    ddg = _Plan(include_pins=True, ok=True)
    assert SearchPass([ddg], st, QueryGrid([]), block_size=3).run(set()) == []
    assert sp_provider_none(st) is None


def sp_provider_none(st):
    return SearchPass([], st, _grid(), block_size=2).provider_for_site_query()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_search_pass.py`
Expected: FAIL (old `SearchPass` still uses `block_cursor`/swap; new asserts on `grid_cursor` fail).

- [ ] **Step 3: Rewrite `search_pass.py`**

Replace the whole file with:

```python
from crawler.discovery.query_grid import merge_queries
from crawler.models import SourceCandidate


class SearchPass:
    """One crawl-pass of active search over a single provider. Walks a block of
    `block_size` grid phrases from `grid_cursor`, advancing the cursor by block_size
    on success (advance-on-success keeps a throttled/backed-off pass from skipping
    phrases). Sequential; the inter-pass sleep dominates wall-clock."""

    def __init__(self, plans, state, grid, block_size, static_keywords=None):
        self._plans = list(plans)
        self._state = state
        self._grid = grid
        self._bs = block_size
        self._pins = list(static_keywords or [])

    def run(self, known) -> list[SourceCandidate]:
        out: list[SourceCandidate] = []
        size = len(self._grid)
        if size == 0 or not self._plans:
            return out
        plan = self._plans[0]
        cursor = self._state.grid_cursor
        batch, new_cursor = self._grid.next_batch(self._bs, cursor)
        pins = self._pins if plan.include_pins else []
        keywords = merge_queries(batch, pins)
        out.extend(plan.discovery.run(keywords, known))
        if plan.succeeded():
            self._state.set_grid_cursor(new_cursor)
        return out

    def provider_for_site_query(self):
        """The single provider's ActiveDiscovery for `site:` queries."""
        return self._plans[0].discovery if self._plans else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_search_pass.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/search_pass.py crawler/tests/test_search_pass.py
git commit -m "refactor(crawler): collapse SearchPass to single-provider grid walk"
```

---

### Task 3: Delete `SearxngProvider` + searxng plan branch; trim `SearchProviderPlan`

**Files:**
- Modify: `crawler/crawler/discovery/providers.py`
- Delete: `crawler/tests/test_searxng_provider.py`
- Modify: `crawler/tests/test_build_plans.py`, `crawler/tests/test_build_provider.py`, `crawler/tests/test_provider_typeclass.py`

**Interfaces:**
- Produces: `SearchProviderPlan(name, discovery, include_pins, succeeded)` — dataclass WITHOUT `cursor_key` / `reset`. `build_search_plans(config, state=None)` returns `[]` for empty/unknown, one plan for `"duckduckgo"`, and logs+ignores any other name (including a stray `"searxng"`).

- [ ] **Step 1: Update the tests first**

DELETE the file `crawler/tests/test_searxng_provider.py`.

In `crawler/tests/test_build_plans.py`: remove `searxng_url="http://searxng:8080", ` from the `_cfg` base dict, and DELETE `test_ddg_and_searxng_plans_distinct_cursors`. Then update `test_ddg_only_plan` to not reference `cursor_key`:

```python
def test_ddg_only_plan(tmp_path):
    plans = build_search_plans(_cfg(tmp_path))
    assert [p.name for p in plans] == ["duckduckgo"]
    assert plans[0].include_pins is True
```

In `crawler/tests/test_build_provider.py`: remove `searxng_url="http://searxng:8080", ` from the `_cfg` base dict (leave the rest).

In `crawler/tests/test_provider_typeclass.py`: change the import line to
`from crawler.discovery.providers import RotatingDdgProvider` (drop `SearxngProvider`),
DELETE `_searx_factory` and `test_searxng_provider_classifies_and_skips_junk`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_build_plans.py tests/test_build_provider.py tests/test_provider_typeclass.py`
Expected: FAIL — imports of `SearxngProvider` / `cursor_key` references still resolve against old code, OR collection error on the just-edited files. (This step confirms the tests now describe the new contract.)

- [ ] **Step 3: Edit `providers.py`**

DELETE the entire `class SearxngProvider:` (lines ~156-196).

In the `SearchProviderPlan` dataclass, remove the `cursor_key: str` and `reset: Callable[[], None]` fields, leaving:
```python
@dataclass
class SearchProviderPlan:
    """One search provider bound to its own ActiveDiscovery and per-pass success
    check. Consumed by SearchPass."""
    name: str
    discovery: ActiveDiscovery
    include_pins: bool
    succeeded: Callable[[], bool]
```

In `build_search_plans`, the `duckduckgo` branch drops `cursor_key`/`reset`:
```python
            provider = SearchCache(rotating, state, config.search_cache_ttl_hours * 3600)
            plans.append(SearchProviderPlan(
                name="duckduckgo",
                discovery=ActiveDiscovery(budget=budget, search_provider=provider),
                include_pins=True,
                succeeded=(lambda st=state: not st.in_global_backoff())))
```
DELETE the entire `elif name == "searxng":` branch (the unknown-name `else: log.warning(...)` stays and now also catches a stray `"searxng"`).

- [ ] **Step 4: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS (searxng gone; DDG plan intact). If any other test imported `SearxngProvider`, fix that reference now.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/providers.py crawler/tests/test_build_plans.py crawler/tests/test_build_provider.py crawler/tests/test_provider_typeclass.py
git rm crawler/tests/test_searxng_provider.py
git commit -m "refactor(crawler): remove SearxngProvider + trim SearchProviderPlan"
```

---

### Task 4: Remove `searxng_url` + dead `search_queries_per_pass` from config

**Files:**
- Modify: `crawler/crawler/config.py`
- Test: `crawler/tests/test_config.py`, `crawler/tests/test_wiring.py`

**Interfaces:**
- Produces: `Config` no longer has `searxng_url` or `search_queries_per_pass` attributes.

- [ ] **Step 1: Update tests first**

In `crawler/tests/test_config.py`: DELETE `test_search_queries_per_pass_default` and `test_search_queries_per_pass_override` (lines ~67-75).

In `crawler/tests/test_wiring.py`: in `test_build_runner_no_build_time_cursor_advance`, DELETE the line `search_queries_per_pass=3,` (line ~45).

- [ ] **Step 2: Run tests to verify current state**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_config.py tests/test_wiring.py`
Expected: PASS still (removing tests/args doesn't break yet — config still has the fields). This is a removal task; the safety net is the full suite in Step 4.

- [ ] **Step 3: Edit `config.py`**

Remove all three occurrences of `search_queries_per_pass` (in `_RawSettings` line ~33, in `Config` line ~131, and the `search_queries_per_pass=s.search_queries_per_pass,` line in `load_config` ~252).

Remove all three occurrences of `searxng_url` (in `_RawSettings` line ~38, in `Config` line ~136, and the `searxng_url=s.searxng_url,` line in `load_config` ~257).

- [ ] **Step 4: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/config.py crawler/tests/test_config.py crawler/tests/test_wiring.py
git commit -m "refactor(crawler): drop searxng_url + dead search_queries_per_pass from config"
```

---

### Task 5: Remove SearXNG infra (compose, env example, settings dir, run docs)

**Files:**
- Modify: `docker-compose.yml`
- Modify: `crawler/.env.example`
- Delete: `searxng/settings.yml` (and the `searxng/` directory)
- Modify: `RUN.md`, `README-docker.md`

**Interfaces:** none (infra/docs only).

- [ ] **Step 1: Edit `docker-compose.yml`**

Delete the whole `searxng:` service block (the `searxng:` key and its `image`/`profiles`/`environment`/`volumes`/`healthcheck` lines). In the `crawler` service: delete the `searxng:` entry under `depends_on:` (and the `condition: service_healthy` under it), and delete the `SEARXNG_URL: http://searxng:8080` line from its `environment:`.

- [ ] **Step 2: Edit `crawler/.env.example`**

Delete the `SEARXNG_URL=...` and `SEARXNG_SECRET=...` lines.

- [ ] **Step 3: Delete the searxng config directory**

```bash
git rm -r searxng
```

- [ ] **Step 4: Edit `RUN.md` and `README-docker.md`**

Remove searxng-specific sections/lines (service description, `SEARXNG_URL`, the searxng healthcheck note, "second provider" mentions). Leave DDG active-search docs intact.

- [ ] **Step 5: Verify no code/infra references remain**

Run (from repo root): `git grep -n -i searxng -- ':!docs/superpowers'`
Expected: NO matches (only dated historical specs/plans under `docs/superpowers/` may still mention it — those are intentionally preserved).

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml crawler/.env.example RUN.md README-docker.md
git commit -m "chore(infra): remove SearXNG service, env, settings and run docs"
```

---

### Task 6: Phase 1 checkpoint — full suite + live DDG verification + tear down container

**Files:** none (verification/deploy).

- [ ] **Step 1: Full crawler suite green**

Run (from `crawler/`): `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS, 0 failures.

- [ ] **Step 2: Canonical rebuild of the crawler image**

```bash
docker compose --profile crawler build crawler
```
Expected: build succeeds (no searxng dependency).

- [ ] **Step 3: Stop and remove the searxng container**

```bash
docker compose --profile crawler stop searxng
docker compose --profile crawler rm -f searxng
```
Expected: `ubd_probe-searxng-1` gone from `docker ps -a`.

- [ ] **Step 4: Bring the crawler up and verify DDG active search runs without crashes**

```bash
docker compose --profile crawler up -d crawler
docker logs --tail 80 ubd_probe-crawler-1
```
Expected: crawler starts, an active pass executes, NO tracebacks, errors=0. Confirm `grid_cursor` advances across passes (inspect `/data/search_state.json`) and no reference to searxng remains.

- [ ] **Step 5: CHECKPOINT — ask the user "продовжуємо B3c (Фаза 2)?"** before proceeding.

---

## PHASE 2 — B3c due-query walking

### Task 7: Add `SearchState.is_fresh` + `QueryGrid.at`

**Files:**
- Modify: `crawler/crawler/discovery/search_state.py`
- Modify: `crawler/crawler/discovery/query_grid.py`
- Test: `crawler/tests/test_search_state.py`, `crawler/tests/test_query_grid.py`

**Interfaces:**
- Produces: `SearchState.is_fresh(keyword: str, ttl_seconds: float) -> bool` — True iff a cache entry exists whose age `< ttl_seconds` (mirrors `cache_get` freshness exactly, same `_key` normalization).
- Produces: `QueryGrid.at(index: int) -> str` — grid phrase at `index % len` (raises/returns for empty grid: returns `""`).

- [ ] **Step 1: Write the failing tests**

Add to `crawler/tests/test_search_state.py`:
```python
def test_is_fresh_true_within_ttl_false_after(tmp_path):
    clk = Clock(1000.0)
    st = _state(tmp_path, clk)
    st.cache_put("Знижки УБД", [])
    assert st.is_fresh("  знижки убд  ", ttl_seconds=100.0) is True   # normalized, within ttl
    clk.t = 1101.0
    assert st.is_fresh("знижки убд", ttl_seconds=100.0) is False       # aged past ttl

def test_is_fresh_false_for_unseen_keyword(tmp_path):
    st = _state(tmp_path, Clock())
    assert st.is_fresh("never searched", ttl_seconds=1e9) is False
```

Add to `crawler/tests/test_query_grid.py` (create the file if absent — check first with an import of `QueryGrid`):
```python
from crawler.discovery.query_grid import QueryGrid

def test_at_wraps_modulo_length():
    g = QueryGrid([f"q{i}" for i in range(3)])
    assert g.at(0) == "q0"
    assert g.at(3) == "q0"      # wraps
    assert g.at(4) == "q1"

def test_at_empty_grid_returns_empty_string():
    assert QueryGrid([]).at(0) == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_search_state.py tests/test_query_grid.py`
Expected: FAIL — `is_fresh` / `at` not defined.

- [ ] **Step 3: Implement**

In `search_state.py`, add near `cache_get`:
```python
    def is_fresh(self, keyword: str, ttl_seconds: float) -> bool:
        """True iff a non-expired cache entry exists for `keyword` (mirrors cache_get)."""
        entry = self._data["cache"].get(self._key(keyword))
        if not entry:
            return False
        return self._clock() - entry.get("ts", 0.0) < ttl_seconds
```

In `query_grid.py`, add to `QueryGrid`:
```python
    def at(self, index: int) -> str:
        size = len(self._grid)
        if size == 0:
            return ""
        return self._grid[index % size]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_search_state.py tests/test_query_grid.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/search_state.py crawler/crawler/discovery/query_grid.py crawler/tests/test_search_state.py crawler/tests/test_query_grid.py
git commit -m "feat(crawler): SearchState.is_fresh + QueryGrid.at (B3c groundwork)"
```

---

### Task 8: Due-query walking in `SearchPass` + wire TTL

**Files:**
- Modify: `crawler/crawler/discovery/search_pass.py`
- Modify: `crawler/crawler/wiring.py:128-129`
- Test: `crawler/tests/test_search_pass.py`

**Interfaces:**
- Consumes: `SearchState.is_fresh(kw, ttl)` (Task 7), `QueryGrid.at(i)` (Task 7), `QueryGrid.__len__`.
- Produces: `SearchPass.__init__(plans, state, grid, block_size, static_keywords=None, ttl_seconds=0.0)`. When `ttl_seconds > 0`, `run` collects up to `block_size` DUE phrases (`is_fresh False`), skipping fresh ones, advancing `grid_cursor` past all phrases scanned; stops at `block_size` due OR after scanning `len(grid)` phrases. `ttl_seconds=0` (default) keeps the plain contiguous walk (back-compat for existing tests).

- [ ] **Step 1: Write the failing tests**

Append to `crawler/tests/test_search_pass.py`:
```python
class _FreshState(SearchState):
    """SearchState with a preset fresh-phrase set for due-walking tests."""
    def __init__(self, path, fresh):
        super().__init__(path)
        self._fresh = set(fresh)
    def is_fresh(self, keyword, ttl_seconds):
        return keyword in self._fresh


def test_due_walking_skips_fresh_and_collects_due(tmp_path):
    st = _FreshState(str(tmp_path / "s.json"), fresh={"q0", "q1", "q3"})
    ddg = _Plan(include_pins=False, ok=True)
    grid = QueryGrid([f"q{i}" for i in range(6)])
    sp = SearchPass([ddg], st, grid, block_size=2, ttl_seconds=1000.0)
    sp.run(set())
    # q0,q1 fresh -> skip; q2 due -> take; q3 fresh -> skip; q4 due -> take (block_size=2)
    assert ddg.discovery.calls == [["q2", "q4"]]
    assert st.grid_cursor == 5              # advanced past all 5 scanned (q0..q4)


def test_due_walking_all_fresh_is_quiet_pass(tmp_path):
    st = _FreshState(str(tmp_path / "s.json"), fresh={f"q{i}" for i in range(4)})
    ddg = _Plan(include_pins=False, ok=True)
    grid = QueryGrid([f"q{i}" for i in range(4)])
    sp = SearchPass([ddg], st, grid, block_size=3, ttl_seconds=1000.0)
    sp.run(set())
    assert ddg.discovery.calls == [[]]      # nothing due -> empty keyword list
    assert st.grid_cursor == 0              # scanned whole grid, wrapped back to start


def test_ttl_zero_keeps_plain_walk(tmp_path):
    st = SearchState(str(tmp_path / "s.json"))
    ddg = _Plan(include_pins=False, ok=True)
    grid = QueryGrid([f"q{i}" for i in range(6)])
    sp = SearchPass([ddg], st, grid, block_size=3, ttl_seconds=0.0)
    sp.run(set())
    assert ddg.discovery.calls == [["q0", "q1", "q2"]]
    assert st.grid_cursor == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_search_pass.py`
Expected: FAIL — `SearchPass` has no `ttl_seconds` param / no due-walking.

- [ ] **Step 3: Implement due-walking in `search_pass.py`**

Replace the file with:
```python
from crawler.discovery.query_grid import merge_queries
from crawler.models import SourceCandidate


class SearchPass:
    """One crawl-pass of active search over a single provider. With ttl_seconds>0 it
    DUE-WALKS: from grid_cursor it collects up to block_size cache-stale phrases,
    skipping still-fresh ones, so every pass does fresh network work and the walk
    self-aligns to the cache TTL. ttl_seconds=0 => plain contiguous block walk.
    Advance-on-success: the cursor moves past all scanned phrases only if the pass
    succeeded (a throttled/backed-off pass re-scans the same phrases next time)."""

    def __init__(self, plans, state, grid, block_size, static_keywords=None,
                 ttl_seconds=0.0):
        self._plans = list(plans)
        self._state = state
        self._grid = grid
        self._bs = block_size
        self._pins = list(static_keywords or [])
        self._ttl = ttl_seconds

    def run(self, known) -> list[SourceCandidate]:
        out: list[SourceCandidate] = []
        size = len(self._grid)
        if size == 0 or not self._plans:
            return out
        plan = self._plans[0]
        cursor = self._state.grid_cursor
        if self._ttl > 0:
            batch, new_cursor = self._collect_due(cursor, size)
        else:
            batch, new_cursor = self._grid.next_batch(self._bs, cursor)
        pins = self._pins if plan.include_pins else []
        keywords = merge_queries(batch, pins)
        out.extend(plan.discovery.run(keywords, known))
        if plan.succeeded():
            self._state.set_grid_cursor(new_cursor)
        return out

    def _collect_due(self, cursor, size):
        """Scan forward from cursor collecting up to block_size due (stale/unseen)
        phrases; return (batch, next_cursor). next_cursor is past every phrase
        scanned (fresh skipped ones included), wrapping modulo size."""
        batch: list[str] = []
        scanned = 0
        while scanned < size and len(batch) < self._bs:
            kw = self._grid.at(cursor)
            if not self._state.is_fresh(kw, self._ttl):
                batch.append(kw)
            cursor = (cursor + 1) % size
            scanned += 1
        return batch, cursor

    def provider_for_site_query(self):
        """The single provider's ActiveDiscovery for `site:` queries."""
        return self._plans[0].discovery if self._plans else None
```

- [ ] **Step 4: Wire the TTL in `wiring.py`**

At `crawler/crawler/wiring.py` (~line 128), change:
```python
            search_pass = SearchPass(plans, state, grid,
                                     config.search_block_size, config.search_keywords)
```
to:
```python
            search_pass = SearchPass(plans, state, grid,
                                     config.search_block_size, config.search_keywords,
                                     ttl_seconds=config.search_cache_ttl_hours * 3600)
```

- [ ] **Step 5: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS (all Phase-1 tests still green; new due-walking tests pass; wiring grid-size tests unaffected since they inspect `_grid`, not `_ttl`).

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/discovery/search_pass.py crawler/crawler/wiring.py crawler/tests/test_search_pass.py
git commit -m "feat(crawler): B3c due-query walking (skip cache-fresh phrases)"
```

---

### Task 9: Phase 2 checkpoint — rebuild + live due-walking verification

**Files:** none (verification/deploy).

- [ ] **Step 1: Full crawler suite green**

Run (from `crawler/`): `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS.

- [ ] **Step 2: Canonical rebuild + restart crawler**

```bash
docker compose --profile crawler build crawler
docker compose --profile crawler up -d crawler
```

- [ ] **Step 3: Verify due-walking live**

```bash
docker logs --tail 80 ubd_probe-crawler-1
```
Expected: active passes run without tracebacks; over consecutive passes, network queries go to stale phrases while cache-fresh phrases are skipped (grid_cursor jumps past fresh runs). Confirm `errors=0`.

- [ ] **Step 4: DONE — report results to the user** (tests count, deploy status, live behaviour) and proceed to branch-finish (merge decision).

---

## Self-Review notes
- **Spec coverage:** 1A→Task 3; 1B→Tasks 1+2+3; 1C→Tasks 4+5; DDG-safety→Task 1 regression + Task 6 live check; Phase-2 2A→Task 7; 2B→Task 8; checkpoints→Tasks 6+9.
- **No placeholders:** every code/edit step shows exact content.
- **Type consistency:** plan object contract (`include_pins`, `succeeded`, `discovery`) matches `SearchProviderPlan` after trim (Task 3) and the `_Plan` doubles (Tasks 2, 8); `is_fresh`/`at`/`ttl_seconds` signatures consistent across Tasks 7–8.
