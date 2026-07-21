# Crawler Query-Grid Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the static ~40-phrase `SEARCH_KEYWORDS` list with a query grid generated from curated vocabulary axes, sampled deterministically across passes to stay within the DDG throttling budget.

**Architecture:** One new curated module (`discovery/query_grid.py`) generates `{intent} {audience}` + `{brand} {audience}` queries and rotates through them via a persisted cursor. Three small wiring changes: a `grid_cursor` on the existing `SearchState`, a `SEARCH_QUERIES_PER_PASS` config knob, and batch assembly in `build_runner` (each `python -m crawler run` process = one pass, so the cursor persists to `search_state.json`). Extraction/attribution untouched; the precision gates downstream remain the safety net.

**Tech Stack:** Python crawler; curated Python tuples/`re` (same pattern as `lexicon.py`/`geo.py`); tests `cd crawler && ./.venv/Scripts/python.exe -m pytest -q` (no network, no DB).

## Global Constraints

- **Scope: crawler logic only.** No DB schema, no backend endpoints, no admin/public UI, no LLM.
- **v1 templates only:** `{intent} {audience}` and `{brand} {audience}`. NO `{...}{vertical}` template, no yield-prioritization, no snowball, no brand→domain crawl.
- **Cities are NOT a query axis** — they remain only in `geo.py` for location extraction.
- **`grid_cursor` is a NEW field, separate from the existing backend-rotation `cursor`** in `SearchState`.
- **Backward compatible:** the generated batch is unioned with any static `SEARCH_KEYWORDS` (manual pins); an empty `SEARCH_KEYWORDS` makes the grid the sole source.
- **Default `SEARCH_QUERIES_PER_PASS` = 40** (keeps DDG footprint ≈ today's).
- **Determinism:** `build_grid()` is pure and stable-ordered; matching/generation is curated, unit-tested.

---

### Task 1: Query-grid vocabulary + generator

**Files:**
- Create: `crawler/crawler/discovery/query_grid.py`
- Test: `crawler/tests/test_query_grid.py`

**Interfaces:**
- Produces: `AUDIENCE_FORMS`, `INTENT_FORMS`, `BRANDS` (tuples of `str`); `build_grid() -> list[str]`; `merge_queries(primary: list[str], extra: list[str]) -> list[str]` (dedup by casefold, order-preserving, `primary` first).

- [ ] **Step 1: Write the failing tests**

Create `crawler/tests/test_query_grid.py`:

```python
from crawler.discovery.query_grid import (
    AUDIENCE_FORMS, INTENT_FORMS, BRANDS, build_grid, merge_queries)


def test_grid_size_matches_axes():
    grid = build_grid()
    assert len(grid) == (len(INTENT_FORMS) + len(BRANDS)) * len(AUDIENCE_FORMS)


def test_grid_has_expected_templates():
    grid = build_grid()
    assert "знижка військові" in grid          # {intent} {audience}
    assert "OKKO ветерани" in grid              # {brand} {audience}


def test_grid_is_deduped_and_nonempty():
    grid = build_grid()
    assert grid == list(dict.fromkeys(grid))    # no duplicates, order preserved
    assert all(q.strip() for q in grid)         # no empty/whitespace entries


def test_grid_order_is_stable():
    assert build_grid() == build_grid()


def test_merge_queries_dedups_casefold_primary_first():
    merged = merge_queries(["знижка військові", "акція ЗСУ"], ["Акція ЗСУ", "мій пін"])
    assert merged == ["знижка військові", "акція ЗСУ", "мій пін"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_query_grid.py -q`
Expected: FAIL — `crawler.discovery.query_grid` does not exist yet.

- [ ] **Step 3: Create the module**

Create `crawler/crawler/discovery/query_grid.py`:

```python
"""Offline curated query grid: generate DDG search phrases from vocabulary axes.

v1 templates only: "{intent} {audience}" and "{brand} {audience}". Cities are
NOT a query axis (they live in geo.py for extraction). Deterministic, stable
order — the same technique as lexicon.py/geo.py: curated tuples, no ML."""

# Audience surface forms (map onto the 7 canonical TARGET_LEXICON slugs).
AUDIENCE_FORMS = (
    "військові", "військовослужбовці", "військові ЗСУ", "ЗСУ", "чинні військові",
    "мобілізовані", "контрактники", "резервісти", "ветерани", "ветеран",
    "ветеран війни", "ветерани АТО", "ветерани ООС", "УБД", "учасники бойових дій",
    "особи з інвалідністю внаслідок війни", "родини військових", "дружини військових",
    "діти військових", "сім'ї УБД", "сім'ї загиблих Захисників", "члени сімей полеглих",
    "поліцейські", "ДСНС", "прикордонники", "ТРО", "Нацгвардія",
)

# Concrete discount-type surface forms (gov/NGO-noise program terms excluded).
INTENT_FORMS = (
    "знижка", "безкоштовно", "акція", "спеціальна пропозиція", "бонус", "подарунок",
    "кешбек", "промокод", "сертифікат", "компенсація", "ваучер",
    "спеціальна ціна", "пільгова ціна",
)

# Brand names (retail / fuel / pharmacy / tech / clothing / banks / post / telecom).
BRANDS = (
    "Rozetka", "Comfy", "Фокстрот", "Епіцентр", "Нова Лінія", "JYSK", "EVA", "Prostor",
    "Аврора", "Копійочка", "Сільпо", "АТБ", "Novus", "VARUS", "Metro",
    "OKKO", "WOG", "UPG", "SOCAR", "БРСМ", "KLO", "Parallel",
    "Подорожник", "АНЦ", "Бажаємо здоров'я", "Аптека Доброго Дня",
    "Алло", "Цитрус", "MOYO", "Brain", "Eldorado",
    "INTERTOP", "Colin's", "LC Waikiki", "Adidas", "Puma", "New Balance", "Megasport",
    "ПриватБанк", "monobank", "Ощадбанк", "ПУМБ", "Sense Bank", "Райффайзен Банк",
    "Нова пошта", "Київстар", "Vodafone", "lifecell",
)


def build_grid() -> list[str]:
    """All "{intent} {audience}" then all "{brand} {audience}", deduped, stable order."""
    seen: set[str] = set()
    out: list[str] = []
    for head in (*INTENT_FORMS, *BRANDS):
        for aud in AUDIENCE_FORMS:
            q = f"{head} {aud}".strip()
            key = q.casefold()
            if q and key not in seen:
                seen.add(key)
                out.append(q)
    return out


def merge_queries(primary: list[str], extra: list[str]) -> list[str]:
    """Union preserving order, `primary` first, deduped case-insensitively."""
    seen: set[str] = set()
    out: list[str] = []
    for q in (*primary, *extra):
        key = (q or "").strip().casefold()
        if key and key not in seen:
            seen.add(key)
            out.append(q)
    return out
```

- [ ] **Step 4: Run the tests**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_query_grid.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/query_grid.py crawler/tests/test_query_grid.py
git commit -m "feat(crawler): curated query-grid vocabulary + generator"
```

---

### Task 2: Deterministic rotation (`QueryGrid.next_batch`)

**Files:**
- Modify: `crawler/crawler/discovery/query_grid.py`
- Test: `crawler/tests/test_query_grid.py`

**Interfaces:**
- Consumes: `build_grid()` (Task 1).
- Produces: `class QueryGrid` with `__init__(self, queries: list[str] | None = None)`, `__len__`, and `next_batch(self, n: int, cursor: int) -> tuple[list[str], int]` (returns `n` queries from `cursor` wrapping around, and the new cursor `(cursor + n) % len`).

- [ ] **Step 1: Write the failing tests**

Append to `crawler/tests/test_query_grid.py`:

```python
from crawler.discovery.query_grid import QueryGrid


def _tiny():
    return QueryGrid(["a", "b", "c", "d"])


def test_next_batch_advances_cursor():
    batch, cur = _tiny().next_batch(2, 0)
    assert batch == ["a", "b"]
    assert cur == 2


def test_next_batch_wraps_around_end():
    batch, cur = _tiny().next_batch(3, 3)   # d, a, b
    assert batch == ["d", "a", "b"]
    assert cur == 2


def test_full_sweep_visits_each_once():
    g = _tiny()
    seen, cur = [], 0
    for _ in range(len(g)):
        b, cur = g.next_batch(1, cur)
        seen += b
    assert sorted(seen) == ["a", "b", "c", "d"]
    assert cur == 0                          # back to start after a full sweep


def test_next_batch_clamps_bad_cursor_and_n():
    g = _tiny()
    assert g.next_batch(99, 0)[0] == ["a", "b", "c", "d"]   # n clamped to len
    assert g.next_batch(1, -5)[0] == ["a"]                  # negative cursor -> 0
    assert g.next_batch(1, 999)[0] == ["a"]                 # out-of-range cursor -> 0


def test_empty_grid_is_safe():
    batch, cur = QueryGrid([]).next_batch(5, 0)
    assert batch == [] and cur == 0
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_query_grid.py -q`
Expected: FAIL — `QueryGrid` not defined.

- [ ] **Step 3: Add the `QueryGrid` class**

Append to `crawler/crawler/discovery/query_grid.py`:

```python
class QueryGrid:
    """Deterministic rotation over the generated grid via an integer cursor."""

    def __init__(self, queries: list[str] | None = None):
        self._grid = queries if queries is not None else build_grid()

    def __len__(self) -> int:
        return len(self._grid)

    def next_batch(self, n: int, cursor: int) -> tuple[list[str], int]:
        size = len(self._grid)
        if size == 0:
            return [], 0
        n = max(1, min(int(n), size))
        if cursor < 0 or cursor >= size:
            cursor = 0
        batch = [self._grid[(cursor + i) % size] for i in range(n)]
        return batch, (cursor + n) % size
```

- [ ] **Step 4: Run the tests**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_query_grid.py -q`
Expected: PASS (all Task 1 + Task 2 tests).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/query_grid.py crawler/tests/test_query_grid.py
git commit -m "feat(crawler): deterministic query-grid rotation (next_batch)"
```

---

### Task 3: `grid_cursor` on `SearchState`

**Files:**
- Modify: `crawler/crawler/discovery/search_state.py`
- Test: `crawler/tests/test_search_state.py`

**Interfaces:**
- Produces: `SearchState.grid_cursor` (property `-> int`, default 0) and `SearchState.set_grid_cursor(value: int) -> None` (persists atomically). Independent of the existing backend-rotation `cursor`.

- [ ] **Step 1: Write the failing tests**

Append to `crawler/tests/test_search_state.py`:

```python
def test_grid_cursor_defaults_zero(tmp_path):
    st = _state(tmp_path, Clock())
    assert st.grid_cursor == 0


def test_set_grid_cursor_persists_and_is_independent(tmp_path):
    path = str(tmp_path / "state.json")
    st = SearchState(path, clock=Clock())
    st.set_cursor(3)            # backend-rotation cursor
    st.set_grid_cursor(42)      # grid cursor — separate field
    reloaded = SearchState.load(path)
    assert reloaded.grid_cursor == 42
    assert reloaded.cursor == 3
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_search_state.py -q`
Expected: FAIL — `grid_cursor` attribute/`set_grid_cursor` missing.

- [ ] **Step 3: Add the field + accessors**

In `crawler/crawler/discovery/search_state.py`, add `"grid_cursor": 0` to `_EMPTY`:

```python
_EMPTY = {"version": 1, "cursor": 0, "grid_cursor": 0,
          "next_allowed_at": 0.0, "backends": {}, "cache": {}}
```

Then, right after the existing `set_cursor` method (the `# --- backend health ---` block begins after it), add:

```python
    # --- query-grid rotation cursor (separate from backend `cursor`) ---
    @property
    def grid_cursor(self) -> int:
        return int(self._data.get("grid_cursor", 0))

    def set_grid_cursor(self, value: int) -> None:
        self._data["grid_cursor"] = int(value)
        self._save()
```

- [ ] **Step 4: Run the tests**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_search_state.py -q`
Expected: PASS (new + existing search-state tests).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/search_state.py crawler/tests/test_search_state.py
git commit -m "feat(crawler): add grid_cursor to SearchState (query-grid rotation)"
```

---

### Task 4: `SEARCH_QUERIES_PER_PASS` config

**Files:**
- Modify: `crawler/crawler/config.py`
- Test: `crawler/tests/test_config.py`

**Interfaces:**
- Produces: `Config.search_queries_per_pass: int` (env `SEARCH_QUERIES_PER_PASS`, default 40).

- [ ] **Step 1: Write the failing tests**

Append to `crawler/tests/test_config.py`:

```python
def test_search_queries_per_pass_default(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)      # no .env -> defaults apply
    assert load_config().search_queries_per_pass == 40


def test_search_queries_per_pass_override(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SEARCH_QUERIES_PER_PASS", "12")
    assert load_config().search_queries_per_pass == 12
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_config.py -q`
Expected: FAIL — `Config` has no `search_queries_per_pass`.

- [ ] **Step 3: Add the setting in three places**

In `crawler/crawler/config.py`:

In `_RawSettings`, after `active_fetch_budget: int = 20`:
```python
    search_queries_per_pass: int = 40
```

In the `Config` dataclass, after `active_fetch_budget: int = 20`:
```python
    search_queries_per_pass: int = 40
```

In `load_config()`'s `Config(...)` call, after `active_fetch_budget=s.active_fetch_budget,`:
```python
        search_queries_per_pass=s.search_queries_per_pass,
```

- [ ] **Step 4: Run the tests**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_config.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/config.py crawler/tests/test_config.py
git commit -m "feat(crawler): SEARCH_QUERIES_PER_PASS config knob"
```

---

### Task 5: Wire the rotated batch into `build_runner`

**Files:**
- Modify: `crawler/crawler/discovery/providers.py` (accept an optional shared `state`)
- Modify: `crawler/crawler/wiring.py` (assemble batch, advance cursor, union with pins)
- Test: `crawler/tests/test_wiring.py`

**Interfaces:**
- Consumes: `QueryGrid`, `merge_queries` (Tasks 1-2); `SearchState.grid_cursor`/`set_grid_cursor` (Task 3); `Config.search_queries_per_pass` (Task 4).
- Produces: `build_runner` passes a per-pass rotated keyword batch (unioned with `SEARCH_KEYWORDS`) to `Runner`, advancing and persisting `grid_cursor`. `build_search_provider(config, state=None)` reuses a passed-in `SearchState` when given.

- [ ] **Step 1: Write the failing test**

Append to `crawler/tests/test_wiring.py`:

```python
from crawler.discovery.query_grid import QueryGrid
from crawler.discovery.search_state import SearchState


def test_build_runner_rotates_query_grid_and_unions_pins(tmp_path):
    state_path = str(tmp_path / "state.json")
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=True, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={},
        search_providers=[],                 # provider None -> no network at build
        search_keywords=["мій пін"],
        search_state_path=state_path,
        search_queries_per_pass=3,
    )
    runner = build_runner(cfg)

    expected_batch, expected_cursor = QueryGrid().next_batch(3, 0)
    assert runner._keywords == expected_batch + ["мій пін"]
    assert SearchState.load(state_path).grid_cursor == expected_cursor
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_wiring.py -q`
Expected: FAIL — `build_runner` still passes the static `config.search_keywords`; cursor never advances.

- [ ] **Step 3: Make `build_search_provider` accept a shared state**

In `crawler/crawler/discovery/providers.py`, change the signature and the lazy-load line so a caller can inject the `SearchState`:

```python
def build_search_provider(config, state=None):
    """Combine enabled search providers into one callable, or None."""
    providers = []
    for name in config.search_providers:
        if name == "duckduckgo":
            if state is None:
                state = SearchState.load(config.search_state_path)
            rotating = RotatingDdgProvider(
```

(Only the `def` line and the removal of the standalone `state = None` initialiser change; the `if state is None: state = SearchState.load(...)` guard now falls back to loading only when no state was injected. The rest of the function body is unchanged.)

- [ ] **Step 4: Assemble the batch in `build_runner`**

In `crawler/crawler/wiring.py`, add imports at the top (next to the other `from crawler.discovery...` imports):

```python
from crawler.discovery.query_grid import QueryGrid, merge_queries
from crawler.discovery.search_state import SearchState
```

Then replace the discovery block in `build_runner` (currently):

```python
    discovery = None
    harvester = None
    if config.active_discovery:
        provider = build_search_provider(config)
        if provider is not None:
            budget = config.search_budget or len(config.search_keywords)
            discovery = ActiveDiscovery(budget=budget, search_provider=provider)
            if config.active_fetch_budget:
                harvester = ActiveHarvester(api, fetchers, extractor, rate_limiter,
                                            fetch_budget=config.active_fetch_budget)
    return Runner(api, fetchers, extractor, rate_limiter,
                  discovery=discovery, keywords=config.search_keywords, harvester=harvester,
                  freshness_ttl_days=config.freshness_ttl_days)
```

with:

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

- [ ] **Step 5: Run the tests**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_wiring.py tests/test_build_provider.py -q`
Expected: PASS — new wiring test passes; `test_build_provider.py` still passes (state defaults to `None` → loads internally as before).

- [ ] **Step 6: Full suite + commit**

Run the whole crawler suite — everything green:
`cd crawler && ./.venv/Scripts/python.exe -m pytest -q`

```bash
git add crawler/crawler/discovery/providers.py crawler/crawler/wiring.py crawler/tests/test_wiring.py
git commit -m "feat(crawler): rotate query-grid batch into discovery, union with SEARCH_KEYWORDS pins"
```

---

## Notes for the implementer

- Each `python -m crawler run` is a **fresh process = one pass** (see `docker-entrypoint.sh`), so the `grid_cursor` MUST round-trip through `search_state.json` — that is exactly what Task 5 does (load → next_batch → set_grid_cursor).
- Do NOT touch the existing backend-rotation `cursor` (used in `providers.py::_take_next_healthy`). `grid_cursor` is a separate field.
- Do NOT add a `{vertical}` template, cities, prioritization, or snowball — those are later sub-projects (see the spec's "OUT of v1").
