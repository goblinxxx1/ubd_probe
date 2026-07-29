# Crawler Coverage Scale-Up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Розділити ротацію запитів між DDG і SearXNG (окремі слайси/курсори, advance-on-success), прибрати бренди з осі гріду, підняти throughput-ручки й вирівняти cache-TTL.

**Architecture:** Кожен пошуковий провайдер отримує власний ActiveDiscovery + власний курсор у SearchState; новий клас `SearchPass` за 1 прохід послідовно (без потоків) проганяє кожен провайдер по його слайсу гріду й зсуває курсор лише на успіх. Runner викликає `SearchPass.run(known)` замість прямого discovery; `discovery`-атрибут лишається тільки для `site:`-запитів. Бренди прибираються з `build_grid()` (кортеж `BRANDS` лишається як дані brand_feed). Ручки й TTL — зміна дефолтів у config.py + ops-env.

**Tech Stack:** Python 3.12, pytest, pydantic-settings, httpx, ddgs. Spec: `docs/superpowers/specs/2026-07-29-crawler-coverage-scaleup-design.md`.

## Global Constraints

- Робочий каталог тестів: `D:\ubd_probe\crawler`. Запуск: `cd D:/ubd_probe/crawler && .venv/Scripts/python.exe -m pytest ...` (Windows venv).
- Послідовно, БЕЗ потоків: спільний стан (`known`, `SearchState`, `DomainRegistry`, курсори) не thread-safe.
- `BRANDS` кортеж у `query_grid.py` НЕ видаляти — його імпортує `brand_feed.py` (інваріант `set(BRAND_SEEDS) == set(BRANDS)`).
- Не чіпати site_query-механізм і його тести (test_runner.py 260-309): `discovery`-атрибут Runner зберігається саме для нього.
- DDG-only лишається дефолтом коду (`search_providers="duckduckgo"`); SearXNG вмикається лише prod-env.
- Кожен крок коду показує повний код. TDD: тест → падіння → реалізація → зелено → коміт.

---

### Task 1: `SearchState.searxng_cursor` (окремий курсор SearXNG)

**Files:**
- Modify: `crawler/crawler/discovery/search_state.py`
- Test: `crawler/tests/test_search_state.py`

**Interfaces:**
- Produces: `SearchState.searxng_cursor -> int` (сентинел `-1` = «не засіяно»), `SearchState.set_searxng_cursor(value: int) -> None`. Ключ `"searxng_cursor"` у персистованому JSON.

- [ ] **Step 1: Failing test** — додати в кінець `crawler/tests/test_search_state.py`:

```python
def test_searxng_cursor_sentinel_default_and_persist(tmp_path):
    from crawler.discovery.search_state import SearchState
    p = str(tmp_path / "s.json")
    st = SearchState(p)
    assert st.searxng_cursor == -1            # unseeded sentinel (offset applied at read-time)
    st.set_searxng_cursor(7)
    assert SearchState.load(p).searxng_cursor == 7   # persisted round-trip
```

- [ ] **Step 2: Run — expect FAIL**

Run: `.venv/Scripts/python.exe -m pytest tests/test_search_state.py::test_searxng_cursor_sentinel_default_and_persist -v`
Expected: FAIL (`AttributeError: 'SearchState' object has no attribute 'searxng_cursor'`).

- [ ] **Step 3: Implement** — у `search_state.py`:

У `_EMPTY` (рядок 11-13) додати ключ `"searxng_cursor": -1`:

```python
_EMPTY = {"version": 1, "cursor": 0, "grid_cursor": 0, "site_cursor": 0,
          "approved_cursor": 0, "searxng_cursor": -1,
          "next_allowed_at": 0.0, "backends": {}, "cache": {}}
```

Після блоку `grid_cursor` (після рядка 56, перед `# --- site-query rotation cursor`) додати:

```python
    # --- searxng rotation cursor (independent of grid_cursor; -1 = unseeded -> offset at read) ---
    @property
    def searxng_cursor(self) -> int:
        return int(self._data.get("searxng_cursor", -1))

    def set_searxng_cursor(self, value: int) -> None:
        self._data["searxng_cursor"] = int(value)
        self._save()
```

- [ ] **Step 4: Run — expect PASS**

Run: `.venv/Scripts/python.exe -m pytest tests/test_search_state.py -v`
Expected: PASS (усі, включно з новим).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/search_state.py crawler/tests/test_search_state.py
git commit -m "feat(crawler): add independent searxng_cursor to SearchState"
```

---

### Task 2: Прибрати бренди з осі гріду

**Files:**
- Modify: `crawler/crawler/discovery/query_grid.py:37-48` (`build_grid`)
- Test: `crawler/tests/test_query_grid.py:5-13`

**Interfaces:**
- Produces: `build_grid()` повертає лише `intent×audience` (розмір `len(INTENT_FORMS)*len(AUDIENCE_FORMS)`). `BRANDS` лишається експортованим кортежем.

- [ ] **Step 1: Update tests** — у `crawler/tests/test_query_grid.py` замінити тіла двох тестів (рядки 5-13):

```python
def test_grid_size_matches_intent_axis_only():
    grid = build_grid()
    assert len(grid) == len(INTENT_FORMS) * len(AUDIENCE_FORMS)


def test_grid_has_intent_templates_not_brands():
    grid = build_grid()
    assert "знижка військові" in grid           # {intent} {audience}
    assert "OKKO ветерани" not in grid          # brands removed from the query axis
    assert "Rozetka військові" not in grid
```

- [ ] **Step 2: Run — expect FAIL**

Run: `.venv/Scripts/python.exe -m pytest tests/test_query_grid.py -v`
Expected: FAIL (грід ще містить бренд-фрази; розмір включає BRANDS).

- [ ] **Step 3: Implement** — у `query_grid.py` змінити цикл у `build_grid()` (рядок 41) з:

```python
    for head in (*INTENT_FORMS, *BRANDS):
```

на:

```python
    for head in INTENT_FORMS:
```

І оновити докстрінг функції (рядок 38) на:

```python
    """All "{intent} {audience}" phrases, deduped, stable order.

    Brands are NOT a query axis — brand DOMAINS are covered directly by brand_feed
    (BRAND_SEEDS ≡ BRANDS, resolved to domains and fetched each pass), so brand
    search queries were redundant. The BRANDS tuple stays for brand_feed's use."""
```

- [ ] **Step 4: Run — expect PASS**

Run: `.venv/Scripts/python.exe -m pytest tests/test_query_grid.py tests/test_brand_feed.py -v`
Expected: PASS (грід лише intent; `test_brand_feed.py` `set(BRAND_SEEDS)==set(BRANDS)` зелений — BRANDS не чіпали).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/query_grid.py crawler/tests/test_query_grid.py
git commit -m "feat(crawler): drop brands from query grid axis (kept as brand_feed data)"
```

---

### Task 3: `SearxngProvider` slice-success сигнал

**Files:**
- Modify: `crawler/crawler/discovery/providers.py:153-185` (`SearxngProvider`)
- Test: `crawler/tests/test_searxng_provider.py`

**Interfaces:**
- Produces: `SearxngProvider.reset_slice() -> None`, `SearxngProvider.slice_ok() -> bool`. `slice_ok()` стає `True`, якщо хоча б один запит слайсу успішно відповів; `reset_slice()` скидає в `False`. Помилка HTTP не піднімає прапорець.

- [ ] **Step 1: Failing test** — додати в `crawler/tests/test_searxng_provider.py`:

```python
def test_searxng_slice_ok_tracks_success_and_reset():
    def ok_handler(req):
        return httpx.Response(200, json={"results": [{"url": "https://a.example/", "title": "A"}]})
    p = SearxngProvider("http://searxng:8080", min_delay=0,
                        client_factory=_factory(ok_handler), sleep=lambda _s: None)
    assert p.slice_ok() is False        # fresh
    p("kw")
    assert p.slice_ok() is True         # a successful query happened
    p.reset_slice()
    assert p.slice_ok() is False        # reset for next slice


def test_searxng_slice_ok_stays_false_on_error():
    def err_handler(req): return httpx.Response(500)
    p = SearxngProvider("http://searxng:8080", min_delay=0,
                        client_factory=_factory(err_handler), sleep=lambda _s: None)
    p.reset_slice()
    p("kw")
    assert p.slice_ok() is False        # error must not mark the slice productive
```

- [ ] **Step 2: Run — expect FAIL**

Run: `.venv/Scripts/python.exe -m pytest tests/test_searxng_provider.py::test_searxng_slice_ok_tracks_success_and_reset -v`
Expected: FAIL (`AttributeError: ... 'slice_ok'`).

- [ ] **Step 3: Implement** — у `SearxngProvider.__init__` (після рядка 162, `self._sleep = sleep`) додати:

```python
        self._slice_ok = False
```

Додати два методи в клас (перед `def __call__`):

```python
    def reset_slice(self) -> None:
        self._slice_ok = False

    def slice_ok(self) -> bool:
        return self._slice_ok
```

У `__call__`, одразу після успішного `data = resp.json()` (тобто після рядка 172, перед `except`… ні — після `try`-блоку, коли розбір удався), підняти прапорець. Конкретно: після рядка `data = resp.json()` й до `out: list[...] = []` вставити:

```python
        self._slice_ok = True
```

Тобто структура стає:

```python
        try:
            with self._client_factory() as client:
                resp = client.get(f"{self._base}/search",
                                  params={"q": keyword, "format": "json"})
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001 — search is best-effort
            log.warning("searxng search failed for %r: %s", keyword, exc)
            return []
        self._slice_ok = True
        out: list[SourceCandidate] = []
```

- [ ] **Step 4: Run — expect PASS**

Run: `.venv/Scripts/python.exe -m pytest tests/test_searxng_provider.py -v`
Expected: PASS (нові + наявні `test_searxng_maps_results...`, `test_searxng_best_effort_on_http_error`).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/providers.py crawler/tests/test_searxng_provider.py
git commit -m "feat(crawler): SearxngProvider slice-success flag for advance-on-success"
```

---

### Task 4: `SearchProviderPlan` + `build_search_plans` (per-provider ActiveDiscovery)

**Files:**
- Modify: `crawler/crawler/discovery/providers.py` (додати dataclass + функцію; ActiveDiscovery import)
- Modify: `crawler/crawler/discovery/active.py:14-22` (budget=0 = unlimited)
- Test: `crawler/tests/test_build_plans.py` (новий)

**Interfaces:**
- Consumes: `SearxngProvider.reset_slice/slice_ok` (Task 3), `SearchState` (Task 1), `ActiveDiscovery`.
- Produces:
  - `SearchProviderPlan` dataclass: `name: str`, `discovery: ActiveDiscovery`, `cursor_key: str`, `include_pins: bool`, `succeeded: Callable[[], bool]`, `reset: Callable[[], None]`.
  - `build_search_plans(config, state=None) -> list[SearchProviderPlan]`. DDG → `cursor_key="grid_cursor"`, `include_pins=True`, `succeeded = not state.in_global_backoff()`, `reset = no-op`. SearXNG → `cursor_key="searxng_cursor"`, `include_pins=False`, `succeeded = sx.slice_ok`, `reset = sx.reset_slice`.
  - `ActiveDiscovery`: `budget=0` (або falsy) → без ліміту.

- [ ] **Step 1: ActiveDiscovery budget tweak — failing test** у `crawler/tests/test_active_discovery.py` додати:

```python
def test_zero_budget_is_unlimited():
    from crawler.models import SourceCandidate
    calls = []
    def provider(keyword):
        calls.append(keyword)
        return [SourceCandidate(name=keyword, type="telegram", url_or_handle=f"t.me/{keyword}")]
    ad = ActiveDiscovery(budget=0, search_provider=provider)
    ad.run(["a", "b", "c"], set())
    assert calls == ["a", "b", "c"]     # 0 == unlimited, all keywords processed
```

- [ ] **Step 2: Run — expect FAIL**

Run: `.venv/Scripts/python.exe -m pytest tests/test_active_discovery.py::test_zero_budget_is_unlimited -v`
Expected: FAIL (наразі `if used >= self._budget` з budget=0 → перериває одразу, `calls == []`).

- [ ] **Step 3: Implement ActiveDiscovery** — у `active.py` рядок `if used >= self._budget:` (у `run`) замінити на:

```python
            if self._budget and used >= self._budget:
                break
```

- [ ] **Step 4: Run — expect PASS**

Run: `.venv/Scripts/python.exe -m pytest tests/test_active_discovery.py -v`
Expected: PASS (усі 4).

- [ ] **Step 5: build_search_plans — failing test** створити `crawler/tests/test_build_plans.py`:

```python
from types import SimpleNamespace

from crawler.discovery.providers import build_search_plans


def _cfg(tmp_path, **over):
    base = dict(
        search_providers=["duckduckgo"], search_results_per_keyword=3, search_min_delay=0,
        search_backends=["google", "brave"], search_state_path=str(tmp_path / "state.json"),
        search_cache_ttl_hours=168, search_jitter=0.5,
        search_backend_cooldown_base_seconds=300.0, search_backend_cooldown_cap_seconds=21600.0,
        search_global_backoff_hours=6.0, searxng_url="http://searxng:8080", search_budget=0,
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_ddg_only_plan(tmp_path):
    plans = build_search_plans(_cfg(tmp_path))
    assert [p.name for p in plans] == ["duckduckgo"]
    p = plans[0]
    assert p.cursor_key == "grid_cursor"
    assert p.include_pins is True


def test_ddg_and_searxng_plans_distinct_cursors(tmp_path):
    plans = build_search_plans(_cfg(tmp_path, search_providers=["duckduckgo", "searxng"]))
    assert [p.name for p in plans] == ["duckduckgo", "searxng"]
    assert {p.cursor_key for p in plans} == {"grid_cursor", "searxng_cursor"}
    sx = [p for p in plans if p.name == "searxng"][0]
    assert sx.include_pins is False          # pins only on DDG


def test_no_known_providers_yields_empty(tmp_path):
    assert build_search_plans(_cfg(tmp_path, search_providers=[])) == []
    assert build_search_plans(_cfg(tmp_path, search_providers=["nope"])) == []
```

- [ ] **Step 6: Run — expect FAIL**

Run: `.venv/Scripts/python.exe -m pytest tests/test_build_plans.py -v`
Expected: FAIL (`ImportError: cannot import name 'build_search_plans'`).

- [ ] **Step 7: Implement build_search_plans** — у `providers.py` на початку файлу додати імпорти (біля інших import, рядок ~9):

```python
from dataclasses import dataclass
from typing import Callable

from crawler.discovery.active import ActiveDiscovery
```

Наприкінці файлу (після `build_search_provider`, який поки лишаємо) додати:

```python
@dataclass
class SearchProviderPlan:
    """One search provider bound to its own ActiveDiscovery, grid cursor, and
    per-slice success check. Consumed by SearchPass to run providers sequentially
    over distinct grid slices with advance-on-success."""
    name: str
    discovery: ActiveDiscovery
    cursor_key: str
    include_pins: bool
    succeeded: Callable[[], bool]
    reset: Callable[[], None]


def build_search_plans(config, state=None) -> list[SearchProviderPlan]:
    """Build one plan per enabled search provider (no combine/fan-out)."""
    plans: list[SearchProviderPlan] = []
    budget = config.search_budget or 0        # 0 == unlimited (slice already bounds it)
    for name in config.search_providers:
        if name == "duckduckgo":
            if state is None:
                state = SearchState.load(config.search_state_path)
            rotating = RotatingDdgProvider(
                pool=config.search_backends, state=state,
                results_per_keyword=config.search_results_per_keyword,
                min_delay=config.search_min_delay, jitter=config.search_jitter,
                cooldown_base=config.search_backend_cooldown_base_seconds,
                cooldown_cap=config.search_backend_cooldown_cap_seconds,
                global_backoff_seconds=config.search_global_backoff_hours * 3600)
            provider = SearchCache(rotating, state, config.search_cache_ttl_hours * 3600)
            plans.append(SearchProviderPlan(
                name="duckduckgo",
                discovery=ActiveDiscovery(budget=budget, search_provider=provider),
                cursor_key="grid_cursor", include_pins=True,
                succeeded=(lambda st=state: not st.in_global_backoff()),
                reset=(lambda: None)))
        elif name == "searxng":
            sx = SearxngProvider(
                base_url=config.searxng_url,
                results_per_keyword=config.search_results_per_keyword,
                min_delay=config.search_min_delay)
            plans.append(SearchProviderPlan(
                name="searxng",
                discovery=ActiveDiscovery(budget=budget, search_provider=sx),
                cursor_key="searxng_cursor", include_pins=False,
                succeeded=sx.slice_ok, reset=sx.reset_slice))
        else:
            log.warning("unknown search provider %r, ignoring", name)
    return plans
```

- [ ] **Step 8: Run — expect PASS**

Run: `.venv/Scripts/python.exe -m pytest tests/test_build_plans.py tests/test_active_discovery.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add crawler/crawler/discovery/providers.py crawler/crawler/discovery/active.py \
        crawler/tests/test_build_plans.py crawler/tests/test_active_discovery.py
git commit -m "feat(crawler): build_search_plans (per-provider ActiveDiscovery + cursor) + unlimited budget"
```

---

### Task 5: `SearchPass` + Runner/wiring switch (advance-on-success)

**Files:**
- Create: `crawler/crawler/discovery/search_pass.py`
- Modify: `crawler/crawler/runner.py` (constructor + harvester discovery feed)
- Modify: `crawler/crawler/wiring.py` (build plans/SearchPass; remove build-time batching)
- Modify: `crawler/crawler/discovery/providers.py` (видалити `build_search_provider`)
- Test: `crawler/tests/test_search_pass.py` (новий), `crawler/tests/test_runner_discovery.py`, `crawler/tests/test_wiring.py`, `crawler/tests/test_build_provider.py`, `crawler/tests/test_searxng_provider.py`

**Interfaces:**
- Consumes: `SearchProviderPlan`, `build_search_plans` (Task 4), `SearchState` (Task 1), `QueryGrid`, `merge_queries`.
- Produces:
  - `SearchPass(plans, state, grid, queries_per_pass, static_keywords=None)` з `run(known) -> list[SourceCandidate]` і `provider_for_site_query() -> ActiveDiscovery | None`.
  - `Runner(...)` тепер приймає `search_pass=None` (замість `keywords`); `discovery=None` лишається (лише site_query).

- [ ] **Step 1: SearchPass — failing test** створити `crawler/tests/test_search_pass.py`:

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
    def __init__(self, name, cursor_key, include_pins, ok):
        self.name = name; self.discovery = _Disc(); self.cursor_key = cursor_key
        self.include_pins = include_pins; self._ok = ok; self.reset_calls = 0
    def succeeded(self): return self._ok
    def reset(self): self.reset_calls += 1


def _grid(): return QueryGrid([f"q{i}" for i in range(10)])


def test_providers_get_distinct_slices_and_pins(tmp_path):
    st = SearchState(str(tmp_path / "s.json"))
    ddg = _Plan("duckduckgo", "grid_cursor", True, ok=True)
    sx = _Plan("searxng", "searxng_cursor", False, ok=True)
    sp = SearchPass([ddg, sx], st, _grid(), queries_per_pass=3, static_keywords=["пін"])
    sp.run(set())
    # DDG starts at grid_cursor 0 -> q0..q2 + pin; SearXNG seeded at len//2=5 -> q5..q7, no pin
    assert ddg.discovery.calls == [["q0", "q1", "q2", "пін"]]
    assert sx.discovery.calls == [["q5", "q6", "q7"]]


def test_advance_on_success_moves_only_successful_cursor(tmp_path):
    st = SearchState(str(tmp_path / "s.json"))
    ddg = _Plan("duckduckgo", "grid_cursor", True, ok=True)
    sx = _Plan("searxng", "searxng_cursor", False, ok=False)   # searxng failed this pass
    sp = SearchPass([ddg, sx], st, _grid(), queries_per_pass=3)
    sp.run(set())
    assert st.grid_cursor == 3            # DDG advanced 0 -> 3
    assert st.searxng_cursor == -1        # SearXNG stayed unseeded (no advance on failure)
    assert ddg.reset_calls == 1 and sx.reset_calls == 1   # reset called each pass


def test_provider_for_site_query_prefers_ddg(tmp_path):
    st = SearchState(str(tmp_path / "s.json"))
    ddg = _Plan("duckduckgo", "grid_cursor", True, ok=True)
    sx = _Plan("searxng", "searxng_cursor", False, ok=True)
    sp = SearchPass([sx, ddg], st, _grid(), queries_per_pass=2)
    assert sp.provider_for_site_query() is ddg.discovery
```

- [ ] **Step 2: Run — expect FAIL**

Run: `.venv/Scripts/python.exe -m pytest tests/test_search_pass.py -v`
Expected: FAIL (`ModuleNotFoundError: ... search_pass`).

- [ ] **Step 3: Implement SearchPass** — створити `crawler/crawler/discovery/search_pass.py`:

```python
from crawler.discovery.query_grid import merge_queries
from crawler.models import SourceCandidate


class SearchPass:
    """One crawl-pass of active search. Each provider plan runs SEQUENTIALLY over its
    own grid slice (distinct chunks via independent cursors); a plan's cursor advances
    only if that provider succeeded (advance-on-success). No threads — shared state is
    not thread-safe."""

    def __init__(self, plans, state, grid, queries_per_pass, static_keywords=None):
        self._plans = list(plans)
        self._state = state
        self._grid = grid
        self._n = queries_per_pass
        self._pins = list(static_keywords or [])

    def run(self, known) -> list[SourceCandidate]:
        out: list[SourceCandidate] = []
        for plan in self._plans:
            start = self._start_for(plan.cursor_key)
            batch, new_cursor = self._grid.next_batch(self._n, start)
            pins = self._pins if plan.include_pins else []
            keywords = merge_queries(batch, pins)
            plan.reset()
            out.extend(plan.discovery.run(keywords, known))
            if plan.succeeded():
                self._set_cursor(plan.cursor_key, new_cursor)
        return out

    def provider_for_site_query(self):
        """DDG plan's ActiveDiscovery for `site:` queries (falls back to first plan)."""
        for plan in self._plans:
            if plan.cursor_key == "grid_cursor":
                return plan.discovery
        return self._plans[0].discovery if self._plans else None

    def _start_for(self, cursor_key: str) -> int:
        if cursor_key == "searxng_cursor":
            c = self._state.searxng_cursor
            return c if c >= 0 else len(self._grid) // 2
        return self._state.grid_cursor

    def _set_cursor(self, cursor_key: str, value: int) -> None:
        if cursor_key == "searxng_cursor":
            self._state.set_searxng_cursor(value)
        else:
            self._state.set_grid_cursor(value)
```

- [ ] **Step 4: Run — expect PASS**

Run: `.venv/Scripts/python.exe -m pytest tests/test_search_pass.py -v`
Expected: PASS.

- [ ] **Step 5: Commit SearchPass**

```bash
git add crawler/crawler/discovery/search_pass.py crawler/tests/test_search_pass.py
git commit -m "feat(crawler): SearchPass — sequential per-provider slices, advance-on-success"
```

- [ ] **Step 6: Switch Runner** — у `runner.py`:

Конструктор (рядок 16): замінити `discovery=None, keywords=None, harvester=None,` на:

```python
                 discovery=None, search_pass=None, harvester=None, brand_feed=None,
```

(тобто прибрати `keywords`, додати `search_pass`; решта рядка 16 без змін — `brand_feed=None`).

Рядки 27-28: замінити:

```python
        self._discovery = discovery
        self._keywords = keywords or []
```

на:

```python
        self._discovery = discovery            # retained ONLY for site: queries
        self._search_pass = search_pass
```

Рядки 77-78: замінити:

```python
                if self._discovery is not None and self._keywords:
                    feeds.append(self._discovery.run(self._keywords, known))
```

на:

```python
                if self._search_pass is not None:
                    feeds.append(self._search_pass.run(known))
```

(site_query-блок рядки 87-108 НЕ чіпати — він і далі використовує `self._discovery`.)

- [ ] **Step 7: Update Runner discovery test** — переписати `crawler/tests/test_runner_discovery.py` рядки 16-32 (`FakeDiscovery`, `_runner`):

```python
class FakeSearchPass:
    def __init__(self, cands): self._cands = cands; self.called_with = None
    def run(self, known):
        self.called_with = set(known)
        return self._cands
    def provider_for_site_query(self): return None


class FakeHarvester:
    def __init__(self): self.calls = []
    def harvest(self, candidates, cats, known, summary, known_hosts=None):
        self.calls.append(list(candidates))
        summary["offers"] += len(candidates)


def _runner(api, search_pass, harvester):
    return Runner(api, {}, extractor=None, rate_limiter=None, search_pass=search_pass,
                  harvester=harvester)
```

І в трьох тестах замінити `FakeDiscovery(...)` → `FakeSearchPass(...)`, а `_runner(api, None, None)` лишити (search_pass=None). Прибрати рядок `from ... FakeDiscovery` якщо є. Тіла тестів (assert-и) не змінюються.

- [ ] **Step 8: Switch wiring** — у `wiring.py`:

Рядок 16: замінити `from crawler.discovery.providers import build_search_provider` на:

```python
from crawler.discovery.providers import build_search_plans
from crawler.discovery.search_pass import SearchPass
```

Рядок 7 (`from crawler.discovery.active import ActiveDiscovery`) — видалити (більше не використовується у wiring).

Рядок 17 import: замінити `from crawler.discovery.query_grid import QueryGrid, merge_queries` на `from crawler.discovery.query_grid import QueryGrid` (merge_queries більше не тут).

Блок active_discovery (рядки 109-123) замінити:

```python
    discovery = None
    harvester = None
    brand_feed = None
    keywords = config.search_keywords
    state = None
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
```

на:

```python
    discovery = None
    search_pass = None
    harvester = None
    brand_feed = None
    state = None
    if config.active_discovery:
        state = SearchState.load(config.search_state_path)
        plans = build_search_plans(config, state=state)
        if plans:
            search_pass = SearchPass(plans, state, QueryGrid(),
                                     config.search_queries_per_pass, config.search_keywords)
            discovery = search_pass.provider_for_site_query()   # DDG discovery for site: queries
```

Harvester-гейт (рядки 173-176): замінити `discovery is not None` на `search_pass is not None`:

```python
    if ((search_pass is not None or brand_feed is not None
         or osm_feed is not None or domain_feed is not None
         or aggregator_feed is not None)
            and config.active_fetch_budget):
```

Runner-конструктор (рядок 187): замінити `discovery=discovery, keywords=keywords, harvester=harvester,` на:

```python
                  discovery=discovery, search_pass=search_pass, harvester=harvester,
```

- [ ] **Step 9: Remove build_search_provider** — у `providers.py` видалити всю функцію `build_search_provider` (рядки 188-220, від `def build_search_provider(config, state=None):` до кінця `return combined`).

- [ ] **Step 10: Update provider/searxng build tests**

`crawler/tests/test_build_provider.py` — замінити весь файл на:

```python
from types import SimpleNamespace

from crawler.discovery.providers import build_search_plans


def _cfg(tmp_path, **over):
    base = dict(
        search_providers=["duckduckgo"], search_results_per_keyword=3, search_min_delay=0,
        search_backends=["google", "brave"], search_state_path=str(tmp_path / "state.json"),
        search_cache_ttl_hours=168, search_jitter=0.5,
        search_backend_cooldown_base_seconds=300.0, search_backend_cooldown_cap_seconds=21600.0,
        search_global_backoff_hours=6.0, searxng_url="http://searxng:8080", search_budget=0,
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_plans_for_known_provider(tmp_path):
    plans = build_search_plans(_cfg(tmp_path))
    assert [p.name for p in plans] == ["duckduckgo"]


def test_no_plans_for_unknown_or_empty(tmp_path):
    assert build_search_plans(_cfg(tmp_path, search_providers=[])) == []
    assert build_search_plans(_cfg(tmp_path, search_providers=["unknown"])) == []
```

`crawler/tests/test_searxng_provider.py` — рядок 4 import змінити на:

```python
from crawler.discovery.providers import SearxngProvider, build_search_plans
```

І тіло `test_build_provider_supports_searxng` (рядки 36-39) замінити на:

```python
def test_build_plans_supports_searxng(tmp_path):
    cfg = SimpleNamespace(search_providers=["searxng"], search_results_per_keyword=3,
                          search_min_delay=0, searxng_url="http://searxng:8080",
                          search_state_path=str(tmp_path / "s.json"), search_budget=0)
    plans = build_search_plans(cfg)
    assert [p.name for p in plans] == ["searxng"]
    assert plans[0].cursor_key == "searxng_cursor"
```

(додати параметр `tmp_path` у сигнатуру тесту.)

- [ ] **Step 11: Update wiring tests** — у `crawler/tests/test_wiring.py`:

(a) Тест `test_build_runner_rotates_query_grid_and_unions_pins` (рядки 37-53) замінити на:

```python
def test_build_runner_no_build_time_cursor_advance(tmp_path):
    state_path = str(tmp_path / "state.json")
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=True, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={},
        search_providers=[],                 # no providers -> no plans, no SearchPass
        search_keywords=["мій пін"],
        search_state_path=state_path,
        search_queries_per_pass=3,
        brand_feed_enabled=False, osm_feed_enabled=False,
    )
    runner = build_runner(cfg)
    assert runner._search_pass is None
    assert SearchState.load(state_path).grid_cursor == 0    # cursor advances at RUN, not BUILD
```

(b) Тест на union харвестера (рядки ~104-121): замінити клас `_Discovery` та виклик Runner. Знайти блок, де оголошено `_Discovery` (повертає candidate name "ddg") і `Runner(..., discovery=_Discovery(), keywords=["kw"], ...)`. Замінити `_Discovery` на:

```python
    class _SearchPass:
        def run(self, known):
            return [SourceCandidate(name="ddg", type="website",
                                    url_or_handle="https://ddg.example")]
        def provider_for_site_query(self): return None
```

і виклик (рядки 117-119) на:

```python
    runner = Runner(_Api(), {}, extractor=None, rate_limiter=None,
                    search_pass=_SearchPass(), harvester=harv,
                    brand_feed=_Feed())
```

(assert `{"ddg", "OKKO"}` лишається.)

(c) Тест `test_runner_skips_harvest_when_no_candidates` (рядки 124-154): замінити `_EmptyDiscovery` на:

```python
    class _EmptySearchPass:
        def run(self, known): return []
        def provider_for_site_query(self): return None
```

і виклик (рядки 150-152) на:

```python
    runner = Runner(_Api(), {}, extractor=None, rate_limiter=None,
                    search_pass=_EmptySearchPass(), harvester=harv,
                    brand_feed=None)
```

(Переконатися, що `SearchState` імпортовано у test_wiring — воно вже є, рядок 34.)

- [ ] **Step 12: Run full crawler suite**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: усі PASS. Якщо якийсь тест ще посилається на `build_search_provider`/`keywords=`/`discovery=`-як-головний-feed — привести до нової моделі (search_pass). site_query-тести у test_runner.py мають лишитися зеленими без змін.

- [ ] **Step 13: Commit the switch**

```bash
git add crawler/crawler/runner.py crawler/crawler/wiring.py crawler/crawler/discovery/providers.py \
        crawler/tests/test_runner_discovery.py crawler/tests/test_wiring.py \
        crawler/tests/test_build_provider.py crawler/tests/test_searxng_provider.py
git commit -m "feat(crawler): wire SearchPass into runner; DDG/SearXNG split with advance-on-success"
```

---

### Task 6: Дефолти ручок + TTL у config.py

**Files:**
- Modify: `crawler/crawler/config.py` (`_RawSettings` + `Config` defaults)
- Test: `crawler/tests/test_config.py`

**Interfaces:**
- Produces: дефолти `active_fetch_budget=80`, `osm_feed_max_domains=1500`, `osm_min_pois=1`, `search_cache_ttl_hours=96`.

- [ ] **Step 1: Update tests** — у `crawler/tests/test_config.py`:
  - рядок 26: `== 20` → `== 80`
  - рядок 34: `cfg.search_cache_ttl_hours == 168` → `== 96`
  - рядки 161-162: `osm_feed_max_domains == 500` → `== 1500`; `osm_min_pois == 2` → `== 1`

- [ ] **Step 2: Run — expect FAIL**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py -v`
Expected: FAIL на цих 4 assert-ах.

- [ ] **Step 3: Implement** — у `config.py` змінити дефолти у **обох** місцях (`_RawSettings` і `Config`):
  - `active_fetch_budget: int = 20` → `= 80` (рядки 32 і 116)
  - `search_cache_ttl_hours: int = 168` → `= 96` (рядки 26 і 110)
  - `osm_feed_max_domains: int = 500` → `= 1500` (рядки 48 і 132)
  - `osm_min_pois: int = 2` → `= 1` (рядки 49 і 133)

- [ ] **Step 4: Run — expect PASS**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/config.py crawler/tests/test_config.py
git commit -m "feat(crawler): raise throughput defaults (budget 80, OSM 1500/1, cache-TTL 96h)"
```

---

### Task 7: Ops-значення + deploy-нотатка (без unit-тестів)

**Files:**
- Modify: `.env.example` (документація інтервалу)
- Modify: `crawler/.env.example` (документація SEARCH_PROVIDERS split)
- Deploy-only (untracked): реальні `.env` / `crawler/.env`, OSM-кеш

**Interfaces:** ops; коду не змінює.

- [ ] **Step 1: Документувати інтервал** — у `.env.example` замінити рядок 13 (`CRAWL_INTERVAL_SECONDS=0`) блоком:

```
# Crawler: 0 = single one-shot pass then exit; >0 = loop every N seconds.
# Coverage prod value: 10800 (3h) — 2 passes/day. Watch DDG/SearXNG throttle in logs.
CRAWL_INTERVAL_SECONDS=0
```

- [ ] **Step 2: Документувати split** — у `crawler/.env.example` додати/оновити рядок про провайдери (якщо є `SEARCH_PROVIDERS=` — оновити коментар; якщо нема — додати):

```
# Search providers: "duckduckgo" (default) or "duckduckgo,searxng" to enable the
# DDG/SearXNG split (distinct query slices per provider, ~2x unique coverage/pass).
SEARCH_PROVIDERS=duckduckgo
```

- [ ] **Step 3: Commit docs**

```bash
git add .env.example crawler/.env.example
git commit -m "docs(ops): document coverage prod interval and DDG/SearXNG split provider list"
```

- [ ] **Step 4: Deploy checklist (виконати при живому деплої, НЕ в git):**
  - У реальному `crawler/.env`: `SEARCH_PROVIDERS=duckduckgo,searxng` (увімкнути split).
  - У реальному кореневому `.env`: `CRAWL_INTERVAL_SECONDS=10800`.
  - Форс-рефреш OSM-пулу під нові параметри (1500/min_pois=1): видалити кеш у volume —
    `docker compose run --rm --entrypoint sh crawler -c "rm -f /data/osm_domains.json"`
    (або `docker compose exec crawler rm -f /data/osm_domains.json`, якщо контейнер живий).
  - Канонічний ребілд crawler-образу (щоб нові config-дефолти набрали чинності):
    `docker compose --profile crawler build crawler && docker compose --profile crawler up -d crawler`
  - Жива перевірка: OSM-пул домен росте (>291), нові suggested/sources з'являються швидше,
    у логах search — обидва провайдери (`ddg:*` і `searxng:*`) на РІЗНИХ запитах, без сплеску банів.

---

## Self-Review

**Spec coverage:**
- §3 split (незалежні курсори, advance-on-success, sequential, static-pins→DDG, SearXNG degraded, backward-compat) → Tasks 1,3,4,5. ✔
- §4 бренди з осі → Task 2. ✔
- §5 ручки + TTL + OSM force-refresh → Tasks 6,7. ✔
- §3.5 ban-risk (min_delay зберігається, advance-on-success гальмує) → успадковано (SearxngProvider min_delay не чіпаємо; succeeded=slice_ok). ✔
- §2 out-of-scope (city/dedup/reject/UX/concurrency) → не в плані. ✔

**Placeholder scan:** без TBD/TODO; кожен крок має повний код. ✔

**Type consistency:** `SearchProviderPlan` поля (name/discovery/cursor_key/include_pins/succeeded/reset) однакові в Task 4 (визначення), Task 5 (SearchPass._Plan-фейк + споживання). `cursor_key` значення `"grid_cursor"`/`"searxng_cursor"` збігаються скрізь. `SearxngProvider.slice_ok/reset_slice` (Task 3) = `succeeded`/`reset` у Task 4. `search_pass` param Runner (Task 5) збігається у wiring і тестах. ✔

**Порядок green:** Task 1-4 адитивні (build_search_provider ще живий) → зелено. Task 5 робить перемикання + видаляє build_search_provider + оновлює ВСІ його споживачі й тести в одному коміті → зелено. ✔
