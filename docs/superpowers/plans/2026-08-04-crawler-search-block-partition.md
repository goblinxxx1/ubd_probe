# Track B · Phase 2 — Block-partition DDG↔searxng with per-cycle swap

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or executing-plans. Steps use `- [ ]`.

**Goal:** DDG and searxng each search a DIFFERENT adjacent block of the query grid every pass (no overlap → together cover 2 blocks/pass), and they SWAP blocks each full cycle so a block that one engine missed is searched by the other next cycle.

**Architecture:** Replace the two independent grid cursors (`grid_cursor`, `searxng_cursor`) with a single `block_cursor` + `cycle` counter in `SearchState`. `SearchPass.run` assigns provider *i* the block at offset `((i+cycle) % n_providers) * block_size` from the cursor; advances the cursor by `n_providers × block_size` on any success (wrap → `cycle += 1`). `block_size` is a config knob. Due-query walking is deferred to Phase 3 (grid expansion) — the existing `SearchCache` already skips the network for fresh phrases.

**Tech Stack:** Python, crawler pytest.

## Global Constraints
- crawler-only; no backend/admin changes.
- Deterministic, testable; `block_size` config knob (`SEARCH_BLOCK_SIZE`, default 15).
- Swap invariant: with N providers, provider `i` this pass takes block `((i+cycle) % N)`; over consecutive cycles each block alternates provider.
- TDD test-first; run `./.venv/Scripts/python.exe -m pytest -q` from `crawler/`.
- Deploy env (this phase): `SEARCH_BLOCK_SIZE=15`, `SEARCH_MIN_DELAY=20`, `SEARCH_CACHE_TTL_HOURS=168`.

---

### Task 1: SearchState — `block_cursor` + `cycle`

**Files:**
- Modify: `crawler/crawler/discovery/search_state.py`
- Test: `crawler/tests/test_search_state.py`

**Interfaces:**
- Produces: `state.block_cursor` / `state.set_block_cursor(v)`; `state.cycle` / `state.set_cycle(v)`. Persisted in the state JSON (additive; defaults 0).

- [ ] **Step 1: Write failing test**
```python
def test_block_cursor_and_cycle_persist(tmp_path):
    from crawler.discovery.search_state import SearchState
    p = str(tmp_path / "s.json")
    st = SearchState(p)
    assert st.block_cursor == 0 and st.cycle == 0
    st.set_block_cursor(30)
    st.set_cycle(2)
    assert SearchState.load(p).block_cursor == 30
    assert SearchState.load(p).cycle == 2
```

- [ ] **Step 2: Run — fails** (`pytest tests/test_search_state.py::test_block_cursor_and_cycle_persist`).

- [ ] **Step 3: Implement**
In `search_state.py`, add `"block_cursor": 0, "cycle": 0` to `_EMPTY`, and accessors mirroring `grid_cursor`:
```python
    @property
    def block_cursor(self) -> int:
        return int(self._data.get("block_cursor", 0))

    def set_block_cursor(self, value: int) -> None:
        self._data["block_cursor"] = int(value)
        self._save()

    @property
    def cycle(self) -> int:
        return int(self._data.get("cycle", 0))

    def set_cycle(self, value: int) -> None:
        self._data["cycle"] = int(value)
        self._save()
```

- [ ] **Step 4: Run — passes** (`pytest tests/test_search_state.py -q`).

- [ ] **Step 5: Commit**
```bash
git add crawler/crawler/discovery/search_state.py crawler/tests/test_search_state.py
git commit -m "feat(crawler): SearchState block_cursor + cycle"
```

---

### Task 2: SearchPass — block-partition + per-cycle swap

**Files:**
- Modify: `crawler/crawler/discovery/search_pass.py`
- Test: `crawler/tests/test_search_pass.py`

**Interfaces:**
- Consumes: `state.block_cursor`, `state.cycle` (Task 1); `QueryGrid.next_batch(n, start)`; `plan.discovery.run`, `plan.succeeded`, `plan.reset`, `plan.include_pins`.
- Produces: `SearchPass(plans, state, grid, block_size, static_keywords=None, city_axis=None, city_queries_per_pass=0)` — provider `i` searches block `((i+cycle)%N)`; cursor advances `N*block_size` on any success.

- [ ] **Step 1: Rewrite the slice/advance tests**
Replace `test_providers_get_distinct_slices_and_pins` and `test_advance_on_success_moves_only_successful_cursor` with block-model tests (keep the city/pins/provider_for_site_query tests, adapting the `queries_per_pass=` kwarg name to `block_size=`):
```python
def test_providers_get_adjacent_blocks_and_pins(tmp_path):
    st = SearchState(str(tmp_path / "s.json"))
    ddg = _Plan("duckduckgo", "grid_cursor", True, ok=True)
    sx = _Plan("searxng", "searxng_cursor", False, ok=True)
    sp = SearchPass([ddg, sx], st, _grid(), block_size=3, static_keywords=["пін"])
    sp.run(set())
    # cycle 0: DDG block 0 (q0..q2)+pin ; searxng block 1 (q3..q5), no pin
    assert ddg.discovery.calls == [["q0", "q1", "q2", "пін"]]
    assert sx.discovery.calls == [["q3", "q4", "q5"]]
    assert st.block_cursor == 6            # advanced N*block_size = 2*3


def test_blocks_swap_provider_next_cycle(tmp_path):
    # grid of 6, block_size 3, 2 providers -> one pass per cycle; next pass = cycle 1 (swapped)
    st = SearchState(str(tmp_path / "s.json"))
    grid = QueryGrid([f"q{i}" for i in range(6)])
    ddg = _Plan("duckduckgo", "grid_cursor", True, ok=True)
    sx = _Plan("searxng", "searxng_cursor", False, ok=True)
    sp = SearchPass([ddg, sx], st, grid, block_size=3)
    sp.run(set())                          # cycle 0: DDG q0-2, sx q3-5 ; cursor 6 -> wrap -> cycle 1
    assert st.cycle == 1 and st.block_cursor == 0
    sp.run(set())                          # cycle 1: swap -> DDG q3-5, sx q0-2
    assert ddg.discovery.calls[-1] == ["q3", "q4", "q5"]
    assert sx.discovery.calls[-1] == ["q0", "q1", "q2"]


def test_no_advance_when_all_providers_fail(tmp_path):
    st = SearchState(str(tmp_path / "s.json"))
    ddg = _Plan("duckduckgo", "grid_cursor", True, ok=False)
    sp = SearchPass([ddg], st, _grid(), block_size=3)
    sp.run(set())
    assert st.block_cursor == 0 and st.cycle == 0
    assert ddg.reset_calls == 1
```
Update the remaining tests in the file to pass `block_size=` instead of `queries_per_pass=` (city tests: `block_size=2`).

- [ ] **Step 2: Run — fails** (`pytest tests/test_search_pass.py -q`) — `SearchPass` has no `block_size`; block model absent.

- [ ] **Step 3: Rewrite `SearchPass`**
```python
from crawler.discovery.query_grid import merge_queries
from crawler.models import SourceCandidate


class SearchPass:
    """One crawl-pass of active search. Providers search DISJOINT adjacent blocks of the
    grid (no overlap) and swap blocks each cycle for resilience. Sequential (no threads —
    shared state is not thread-safe); the 2h inter-pass sleep dominates wall-clock anyway."""

    def __init__(self, plans, state, grid, block_size, static_keywords=None,
                 city_axis=None, city_queries_per_pass=0):
        self._plans = list(plans)
        self._state = state
        self._grid = grid
        self._bs = block_size
        self._pins = list(static_keywords or [])
        self._city_axis = city_axis
        self._city_k = int(city_queries_per_pass or 0)

    def run(self, known) -> list[SourceCandidate]:
        out: list[SourceCandidate] = []
        size = len(self._grid)
        n = len(self._plans)
        if size == 0 or n == 0:
            return out
        city_on = (self._city_axis is not None and self._city_k > 0
                   and len(self._city_axis) > 0)
        cursor = self._state.block_cursor
        cycle = self._state.cycle
        any_ok = False
        for i, plan in enumerate(self._plans):
            start = (cursor + ((i + cycle) % n) * self._bs) % size   # per-cycle swap
            batch, _ = self._grid.next_batch(self._bs, start)
            pins = self._pins if plan.include_pins else []
            keywords = merge_queries(batch, pins)
            if city_on:
                city_qs, _ = self._city_axis.next_batch(
                    batch, self._state.city_cursor, self._city_k)
                keywords = merge_queries(keywords, city_qs)
            plan.reset()
            out.extend(plan.discovery.run(keywords, known))
            if plan.succeeded():
                any_ok = True
        if any_ok:
            new_cursor = cursor + n * self._bs
            if new_cursor >= size:
                new_cursor %= size
                self._state.set_cycle(cycle + 1)
            self._state.set_block_cursor(new_cursor)
            if city_on:
                self._state.set_city_cursor(
                    (self._state.city_cursor + 1) % len(self._city_axis))
        return out

    def provider_for_site_query(self):
        for plan in self._plans:
            if plan.cursor_key == "grid_cursor":
                return plan.discovery
        return self._plans[0].discovery if self._plans else None
```
(`_start_for`/`_set_cursor` removed — no longer used.)

- [ ] **Step 4: Run — passes** (`pytest tests/test_search_pass.py -q`).

- [ ] **Step 5: Commit**
```bash
git add crawler/crawler/discovery/search_pass.py crawler/tests/test_search_pass.py
git commit -m "feat(crawler): SearchPass block-partition + per-cycle provider swap"
```

---

### Task 3: config `search_block_size` + wiring

**Files:**
- Modify: `crawler/crawler/config.py`, `crawler/crawler/wiring.py`
- Test: `crawler/tests/test_config.py`

**Interfaces:**
- Produces: `config.search_block_size` (default 15); wiring passes it as `block_size=` to `SearchPass`.

- [ ] **Step 1: Write failing test**
```python
def test_search_block_size_default_and_override(monkeypatch, tmp_path):
    from crawler.config import load_config
    monkeypatch.chdir(tmp_path)
    assert load_config().search_block_size == 15
    monkeypatch.setenv("SEARCH_BLOCK_SIZE", "8")
    assert load_config().search_block_size == 8
```

- [ ] **Step 2: Run — fails.**

- [ ] **Step 3: Implement**
In `config.py`, add `search_block_size: int = 15` to BOTH `_RawSettings` and `Config` (near `search_queries_per_pass`), and `search_block_size=s.search_block_size,` in `load_config`.
In `wiring.py`, change the `SearchPass(...)` construction to pass `config.search_block_size` as the `block_size` positional/kw arg in place of `config.search_queries_per_pass`:
```python
            search_pass = SearchPass(plans, state, QueryGrid(),
                                     config.search_block_size, config.search_keywords,
                                     city_axis=city_axis,
                                     city_queries_per_pass=config.city_queries_per_pass)
```
(Keep `search_queries_per_pass` config for backward compat; no longer used by SearchPass.)

- [ ] **Step 4: Run — passes + full suite**
`./.venv/Scripts/python.exe -m pytest tests/test_config.py tests/test_wiring.py tests/test_search_pass.py -q` then `./.venv/Scripts/python.exe -m pytest -q`.

- [ ] **Step 5: Commit**
```bash
git add crawler/crawler/config.py crawler/crawler/wiring.py crawler/tests/test_config.py
git commit -m "feat(crawler): search_block_size config + wire into SearchPass"
```

---

## Deploy
Canonical crawler rebuild; set in `crawler/.env`: `SEARCH_BLOCK_SIZE=15`, `SEARCH_MIN_DELAY=20`, `SEARCH_CACHE_TTL_HOURS=168`; restart. Live-verify: DDG and searxng issue disjoint adjacent blocks; `block_cursor`/`cycle` advance & persist; `search_min_delay=20`.

## Self-Review notes
- Spec §1 (block-partition + swap) → Tasks 1-2; ручки block_size/min_delay/TTL → Task 3 + deploy env.
- Due-walking (spec §2) deferred to Phase 3 (grid expansion) — noted.
- No placeholders; complete code per step.
- Names consistent: `block_cursor`, `cycle`, `block_size`, `search_block_size`.
