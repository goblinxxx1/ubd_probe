# B3a — City as materialized grid multiplier — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the diagonal full-gazetteer `CityAxis` with a true materialized city multiplier over a curated ~45-city list, so `build_grid()` returns a fixed ~1701-phrase space that the existing block-partition machinery rotates over.

**Architecture:** `build_grid` grows a geo block (`GEO_INTENTS × GEO_AUDIENCES × GRID_CITIES` = 5×6×45 = 1350) appended after the unchanged 351 base (intent×audience), total 1701. The diagonal `CityAxis` path (SearchPass params, `city_cursor`, config `city_axis_*`, wiring instance, the file itself) is removed as superseded=dead. A rollback flag `grid_cities_enabled` (default True) makes `build_grid(cities=[])` fall back to the plain 351.

**Tech Stack:** Python 3, pytest. crawler-only; backend/admin untouched.

## Global Constraints

- crawler-only. No backend/admin changes.
- Curated tables live in `crawler/crawler/discovery/query_grid.py`, in the nominative case (matching existing `build_grid`, e.g. "знижка ветерани"). No dative table (YAGNI).
- `GRID_CITIES` = exactly 45 names, occupied cities excluded (Донецьк, Луганськ, Сімферополь, Севастополь, Маріуполь, Мелітополь, Бердянськ).
- `GEO_INTENTS` ⊆ `INTENT_FORMS`; `GEO_AUDIENCES` ⊆ `AUDIENCE_FORMS`.
- The first 351 entries of `build_grid()` must be byte-identical to today's output (byte-stable prefix for the block cursor).
- Case-insensitive dedup, stable deterministic order (as today).
- Run crawler tests from `crawler/`: `python -m pytest -q` (Windows). Full suite must stay green at the end of every task.
- `grid_cities_enabled` class-default True; `False` ⇒ 351 = today's base (minus diagonal), byte-eq to plain grid.
- Spec: `docs/superpowers/specs/2026-08-04-crawler-b3a-city-multiplier-design.md`.

---

### Task 1: Curated tables + materialized `build_grid`

**Files:**
- Modify: `crawler/crawler/discovery/query_grid.py` (add `GRID_CITIES`, `GEO_INTENTS`, `GEO_AUDIENCES`; rewrite `build_grid`)
- Test: `crawler/tests/test_query_grid.py`

**Interfaces:**
- Consumes: existing `INTENT_FORMS` (13), `AUDIENCE_FORMS` (27) in `query_grid.py`.
- Produces:
  - `GRID_CITIES: tuple[str, ...]` (45 unique names)
  - `GEO_INTENTS: tuple[str, ...]` (5), `GEO_AUDIENCES: tuple[str, ...]` (6)
  - `build_grid(cities: list[str] | None = None) -> list[str]` — `None` ⇒ `GRID_CITIES`; `[]` ⇒ plain 351. Order: base 351 first (unchanged), then geo block `intent→audience→city` (city innermost). Deduped case-insensitively.

- [ ] **Step 1: Write the failing tests**

Replace the size test and add coverage in `crawler/tests/test_query_grid.py`. Change the top import line to:

```python
from crawler.discovery.query_grid import (
    AUDIENCE_FORMS, INTENT_FORMS, GRID_CITIES, GEO_INTENTS, GEO_AUDIENCES,
    build_grid, merge_queries)
```

Replace `test_grid_size_matches_intent_axis_only` with:

```python
def test_grid_size_is_base_plus_geo_block():
    base = len(INTENT_FORMS) * len(AUDIENCE_FORMS)          # 351
    geo = len(GEO_INTENTS) * len(GEO_AUDIENCES) * len(GRID_CITIES)  # 5*6*45 = 1350
    grid = build_grid()
    assert base == 351 and geo == 1350
    assert len(grid) == base + geo == 1701


def test_base_prefix_is_byte_stable():
    # first 351 == the plain intent×audience grid, unchanged order
    grid = build_grid()
    plain = build_grid(cities=[])
    assert len(plain) == 351
    assert grid[:351] == plain


def test_geo_block_present_and_ordered():
    grid = build_grid()
    assert "знижка військові Київ" in grid                  # {geo_intent} {geo_aud} {city}
    assert "знижка військові" in grid                       # plain base still present
    # geo entries carry a curated city suffix
    assert grid[351].endswith(f" {GRID_CITIES[0]}")
    assert grid[351] == f"{GEO_INTENTS[0]} {GEO_AUDIENCES[0]} {GRID_CITIES[0]}"


def test_grid_cities_curated_and_no_occupied():
    assert len(GRID_CITIES) == 45
    assert len(set(GRID_CITIES)) == 45                      # unique
    for occ in ("Донецьк", "Луганськ", "Сімферополь", "Севастополь",
                "Маріуполь", "Мелітополь", "Бердянськ"):
        assert occ not in GRID_CITIES


def test_geo_subsets_are_subsets_of_axes():
    assert set(GEO_INTENTS) <= set(INTENT_FORMS)
    assert set(GEO_AUDIENCES) <= set(AUDIENCE_FORMS)


def test_cities_di_controls_geo_size():
    grid = build_grid(cities=["Львів", "Одеса"])
    assert len(grid) == 351 + len(GEO_INTENTS) * len(GEO_AUDIENCES) * 2   # 351 + 60
```

Keep `test_grid_has_intent_templates_not_brands`, `test_grid_is_deduped_and_nonempty`, `test_grid_order_is_stable`, and all `QueryGrid` tests unchanged.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest crawler/tests/test_query_grid.py -q`
Expected: FAIL — `ImportError: cannot import name 'GRID_CITIES'` (and size asserts).

- [ ] **Step 3: Implement tables + new `build_grid`**

In `crawler/crawler/discovery/query_grid.py`, add after `INTENT_FORMS` (before `BRANDS`):

```python
# Curated top cities as a TRUE grid multiplier (B3a). ~45 largest / oblast
# centres, government-controlled — occupied cities excluded (no live merchant
# offers). Small towns stay in geo.py for EXTRACTION; only query targeting narrows.
GRID_CITIES = (
    "Київ", "Харків", "Одеса", "Дніпро", "Львів", "Запоріжжя", "Вінниця",
    "Полтава", "Чернігів", "Черкаси", "Житомир", "Суми", "Хмельницький",
    "Чернівці", "Рівне", "Тернопіль", "Івано-Франківськ", "Луцьк", "Ужгород",
    "Кропивницький", "Миколаїв", "Херсон",
    "Кривий Ріг", "Кременчук", "Біла Церква", "Кам'янське", "Умань", "Бровари",
    "Бориспіль", "Ірпінь", "Буча", "Нікополь", "Павлоград", "Олександрія",
    "Ковель", "Калуш", "Дрогобич", "Червоноград", "Мукачево", "Бердичів",
    "Ніжин", "Конотоп", "Шостка", "Ізмаїл", "Краматорськ",
)  # 45

# Curated geo-slice: only these strong intent/audience forms get a city suffix,
# keeping the materialized space ~1701 (30 geo-base × 45 cities = 1350 + 351).
GEO_INTENTS = ("знижка", "акція", "безкоштовно", "спеціальна пропозиція",
               "пільгова ціна")
GEO_AUDIENCES = ("військові", "ветерани", "УБД", "учасники бойових дій",
                 "ветерани війни", "мобілізовані")
```

Replace `build_grid` with:

```python
def build_grid(cities: list[str] | None = None) -> list[str]:
    """Materialized search space: the 351 "{intent} {audience}" base (unchanged
    order — byte-stable prefix) then a geo block GEO_INTENTS×GEO_AUDIENCES×cities
    ("{intent} {audience} {city}"), deduped case-insensitively, stable order.

    `cities=None` uses GRID_CITIES (~1701 total); `cities=[]` yields the plain 351
    (rollback / OFF). City is the innermost axis so adjacent entries differ by city."""
    city_list = list(GRID_CITIES) if cities is None else list(cities)
    seen: set[str] = set()
    out: list[str] = []

    def _add(q: str) -> None:
        key = q.casefold()
        if q and key not in seen:
            seen.add(key)
            out.append(q)

    for head in INTENT_FORMS:                # base 351 — order unchanged
        for aud in AUDIENCE_FORMS:
            _add(f"{head} {aud}".strip())
    for head in GEO_INTENTS:                 # geo block: intent → audience → city
        for aud in GEO_AUDIENCES:
            for city in city_list:
                _add(f"{head} {aud} {city}".strip())
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest crawler/tests/test_query_grid.py -q`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/query_grid.py crawler/tests/test_query_grid.py
git commit -m "feat(crawler): B3a build_grid materialized city multiplier (351+1350=1701)"
```

---

### Task 2: Retire diagonal `CityAxis` path + rollback flag

**Files:**
- Modify: `crawler/crawler/discovery/search_pass.py` (drop `city_axis`/`city_queries_per_pass` params + `city_on` branch)
- Modify: `crawler/crawler/discovery/search_state.py` (drop `city_cursor`)
- Modify: `crawler/crawler/config.py` (drop `city_axis_enabled`/`city_queries_per_pass` in both dataclasses + `from_settings`; add `grid_cities_enabled`)
- Modify: `crawler/crawler/wiring.py` (drop `CityAxis` import/instance; gate `build_grid` via `grid_cities_enabled`)
- Test: `crawler/tests/test_search_pass.py`, `crawler/tests/test_search_state.py`, `crawler/tests/test_config.py`, `crawler/tests/test_wiring.py`

**Interfaces:**
- Consumes: `build_grid` from Task 1; existing `QueryGrid`, `SearchPass`, `SearchState`, config `Config`/`Settings`/`from_settings`.
- Produces:
  - `SearchPass.__init__(self, plans, state, grid, block_size, static_keywords=None)` — no city params.
  - `SearchState`: no `city_cursor` property/setter, no `"city_cursor"` in `_EMPTY`.
  - config `Config` and raw `Settings`: `grid_cities_enabled: bool = True` (replaces `city_axis_enabled`, `city_queries_per_pass`); `from_settings` maps it.
  - wiring: `grid = QueryGrid() if config.grid_cities_enabled else QueryGrid(build_grid(cities=[]))`.

- [ ] **Step 1: Update the tests (red)**

In `crawler/tests/test_search_pass.py`: remove the `from crawler.discovery.city_axis import CityAxis` import (line 5) and delete the four city tests: `test_city_*` (the ones constructing `SearchPass(..., city_axis=..., city_queries_per_pass=...)` and asserting `st.city_cursor`). Any remaining `SearchPass(...)` construction in the kept block-partition tests must not pass `city_axis`/`city_queries_per_pass`.

In `crawler/tests/test_search_state.py`: delete `test_city_cursor_defaults_zero` and `test_set_city_cursor_persists_and_is_independent`.

In `crawler/tests/test_config.py`: replace the three city tests (`test_city_axis_raw_defaults`, `test_city_axis_config_dataclass_defaults`, `test_load_config_passes_city_axis`) with:

```python
def test_grid_cities_raw_default_true():
    s = Settings()
    assert s.grid_cities_enabled is True


def test_grid_cities_config_dataclass_default_true():
    cfg = Config()
    assert cfg.grid_cities_enabled is True


def test_load_config_passes_grid_cities(monkeypatch, tmp_path):
    monkeypatch.setenv("GRID_CITIES_ENABLED", "false")
    cfg = load_config()
    assert cfg.grid_cities_enabled is False
```

(Match the existing `Settings`/`Config`/`load_config` import names and env-parsing convention already used in `test_config.py`; if the file constructs `Config(...)` with required args, mirror the existing sibling test's construction.)

In `crawler/tests/test_wiring.py`: replace `test_build_runner_wires_city_axis` and `test_build_runner_city_axis_disabled` with:

```python
def test_build_runner_grid_has_cities(tmp_path):
    config = _min_active_config(tmp_path, grid_cities_enabled=True)
    runner = build_runner(config)
    assert len(runner._search_pass._grid) == 1701


def test_build_runner_grid_cities_disabled(tmp_path):
    config = _min_active_config(tmp_path, grid_cities_enabled=False)
    runner = build_runner(config)
    assert len(runner._search_pass._grid) == 351
```

(Use whatever active-config factory / `build_runner` symbol the existing two tests used — copy their construction, swapping `city_axis_enabled=` for `grid_cities_enabled=`, and assert on `_search_pass._grid` length. `SearchPass` keeps `self._grid`, so `len(runner._search_pass._grid)` works via `QueryGrid.__len__`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest crawler/tests/test_search_pass.py crawler/tests/test_search_state.py crawler/tests/test_config.py crawler/tests/test_wiring.py -q`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'grid_cities_enabled'` / `_grid` length 1701-vs mismatch / import errors.

- [ ] **Step 3: Strip city path from `search_pass.py`**

Replace the class body of `crawler/crawler/discovery/search_pass.py` with (drop the city docstring clause, params, and branch):

```python
    def __init__(self, plans, state, grid, block_size, static_keywords=None):
        self._plans = list(plans)
        self._state = state
        self._grid = grid
        self._bs = block_size
        self._pins = list(static_keywords or [])

    def run(self, known) -> list[SourceCandidate]:
        out: list[SourceCandidate] = []
        size = len(self._grid)
        n = len(self._plans)
        if size == 0 or n == 0:
            return out
        cursor = self._state.block_cursor
        cycle = self._state.cycle
        any_ok = False
        for i, plan in enumerate(self._plans):
            start = (cursor + ((i + cycle) % n) * self._bs) % size   # per-cycle provider↔block swap
            batch, _ = self._grid.next_batch(self._bs, start)
            pins = self._pins if plan.include_pins else []
            keywords = merge_queries(batch, pins)
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
        return out
```

Leave `provider_for_site_query` unchanged.

- [ ] **Step 4: Drop `city_cursor` from `search_state.py`**

In `_EMPTY` (line 11-14) remove `"city_cursor": 0,` so it reads:

```python
_EMPTY = {"version": 1, "cursor": 0, "grid_cursor": 0, "site_cursor": 0,
          "approved_cursor": 0, "searxng_cursor": -1,
          "block_cursor": 0, "cycle": 0,
          "next_allowed_at": 0.0, "backends": {}, "cache": {}}
```

Delete the `city_cursor` property and `set_city_cursor` method (the `# --- city-axis rotation cursor ...` block, lines ~103-110).

- [ ] **Step 5: Swap config fields**

In `crawler/crawler/config.py`, in BOTH the raw settings block (lines ~35-36) and the `Config` dataclass (lines ~125-126), replace:

```python
    city_axis_enabled: bool = True
    city_queries_per_pass: int = 10
```

with:

```python
    grid_cities_enabled: bool = True
```

In `from_settings` (lines ~238-239) replace:

```python
        city_axis_enabled=s.city_axis_enabled,
        city_queries_per_pass=s.city_queries_per_pass,
```

with:

```python
        grid_cities_enabled=s.grid_cities_enabled,
```

If the raw `Settings` uses an env-parsing helper (BaseSettings / manual `os.getenv`), ensure `grid_cities_enabled` reads env `GRID_CITIES_ENABLED` the same way its neighbours (e.g. `site_query_enabled`) do — mirror the existing boolean field's pattern exactly.

- [ ] **Step 6: Rewire `wiring.py`**

Remove the import `from crawler.discovery.city_axis import CityAxis` (line 11). Change the query-grid import (line 18) to:

```python
from crawler.discovery.query_grid import QueryGrid, build_grid
```

Replace the `if plans:` block (lines ~119-124):

```python
        if plans:
            grid = QueryGrid() if config.grid_cities_enabled else QueryGrid(build_grid(cities=[]))
            search_pass = SearchPass(plans, state, grid,
                                     config.search_block_size, config.search_keywords)
            discovery = search_pass.provider_for_site_query()   # DDG discovery for site: queries
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest crawler/tests/test_search_pass.py crawler/tests/test_search_state.py crawler/tests/test_config.py crawler/tests/test_wiring.py -q`
Expected: PASS (all).

- [ ] **Step 8: Commit**

```bash
git add crawler/crawler/discovery/search_pass.py crawler/crawler/discovery/search_state.py crawler/crawler/config.py crawler/crawler/wiring.py crawler/tests/test_search_pass.py crawler/tests/test_search_state.py crawler/tests/test_config.py crawler/tests/test_wiring.py
git commit -m "feat(crawler): B3a retire diagonal CityAxis; grid_cities_enabled flag"
```

---

### Task 3: Delete orphaned `city_axis.py` + its test

**Files:**
- Delete: `crawler/crawler/discovery/city_axis.py`
- Delete: `crawler/tests/test_city_axis.py`

**Interfaces:**
- Consumes: nothing — after Task 2 no module imports `CityAxis` (verified by grep).
- Produces: nothing.

- [ ] **Step 1: Confirm no live importers**

Run: `git grep -n "city_axis\|CityAxis" -- crawler/crawler crawler/tests`
Expected: no output (only spec/plan docs may still mention it).

- [ ] **Step 2: Delete the files**

```bash
git rm crawler/crawler/discovery/city_axis.py crawler/tests/test_city_axis.py
```

- [ ] **Step 3: Run the full crawler suite**

Run: `python -m pytest -q` (from `crawler/`)
Expected: PASS, no collection errors, count ≈ prior 526 minus the removed city tests plus the new ones.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore(crawler): B3a remove orphaned city_axis module + test"
```

---

## Self-Review

**Spec coverage:**
- Curated tables (`GRID_CITIES` 45, `GEO_INTENTS` 5, `GEO_AUDIENCES` 6) → Task 1. ✓
- `build_grid` materialization, byte-stable 351 prefix, geo order intent→audience→city, `cities=[]`→351, DI → Task 1 tests. ✓
- Occupied cities excluded → Task 1 `test_grid_cities_curated_and_no_occupied`. ✓
- Retire diagonal `CityAxis` (SearchPass params/branch, `city_cursor`, config, wiring) → Task 2. ✓
- Rollback flag `grid_cities_enabled` (True→1701, False→351) → Task 2 config + wiring + tests. ✓
- Delete `city_axis.py` + `test_city_axis.py` → Task 3. ✓
- Extraction breadth unchanged (geo.py untouched) → no task edits geo.py; noted in spec. ✓
- Canonical crawler rebuild + live verification → post-merge (deploy step, outside plan; noted in spec §Деплой).

**Placeholder scan:** No TBD/TODO. Every code step shows full code. The two "mirror the existing pattern" notes (config env-parsing, wiring/config test factories) are pointers to concrete sibling code the implementer can read, not vague instructions. ✓

**Type consistency:** `build_grid(cities=None)`, `GRID_CITIES`/`GEO_INTENTS`/`GEO_AUDIENCES` tuples, `SearchPass.__init__(plans, state, grid, block_size, static_keywords=None)`, `grid_cities_enabled: bool`, `runner._search_pass._grid` — names identical across tasks. ✓
