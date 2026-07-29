# City-вісь у query-grid Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Додати місто як незалежну ротаційну вісь до активного пошуку краулера — місто-суфікс до `{intent} {audience}` фраз — щоб діставати локальні бізнеси по всій Україні.

**Architecture:** Новий ізольований `CityAxis` суфіксує ПОТОЧНЕ місто (окремий `city_cursor` у `SearchState`) на зріз базового batch фраз; `SearchPass` домержує ці city-запити у keywords кожного провайдера й просуває `city_cursor` +1/прохід на успіху. Два незалежні курсори (фрази + місто) з різними періодами дають діагональний sweep простору city×phrase без матеріалізації декартового добутку. Вимкнено → байт-еквівалентний відкат.

**Tech Stack:** Python 3, pytest, pydantic-settings. Краулер-пакет `crawler/crawler/`, тести `crawler/tests/`.

## Global Constraints

- Джерело міст: наявний `crawler/crawler/discovery/gazetteer.json` (1229 = міста+смт), перевикористати **як є**; суфікс = канонічне `name`, НЕ інфлексовані `forms`.
- City-вісь — суто discovery/recall-левер: місто **офера** досі визначається екстракцією зі змісту сторінки (`geo.find_cities`); harvester/attribution/walker/інші фіди/курсори `grid_cursor`/`searxng_cursor`/`site_cursor`/`approved_cursor` — НЕ чіпати.
- Вимкнена вісь (`city_axis_enabled=False` або `city_queries_per_pass=0` або порожній газетир) → **байт-еквівалентний** відкат живого пошуку до pre-track.
- Дефолти: `city_axis_enabled=True`, `city_queries_per_pass=10` (адитивно: 40 базових + 10 city/провайдера/прохід).
- Спілкування українською; TDD, часті коміти.
- Тести: з `crawler/` запускати `./.venv/Scripts/python.exe -m pytest -q` (crawler-тести мережі/MySQL не потребують).

---

### Task 1: `CityAxis` компонент

**Files:**
- Create: `crawler/crawler/discovery/city_axis.py`
- Test: `crawler/tests/test_city_axis.py`

**Interfaces:**
- Consumes: `crawler.discovery.geo._load_entries()` (наявний; повертає `list[dict]` із ключем `"name"`).
- Produces:
  - `CityAxis(cities: list[str] | None = None)` — дефолт вантажить назви з газетира.
  - `CityAxis.__len__() -> int` — кількість міст.
  - `CityAxis.next_batch(base_phrases: list[str], cursor: int, k: int) -> tuple[list[str], int]` — суфіксує `cities[cursor % len]` на перші `k` непорожніх `base_phrases`; повертає `(queries, (cursor+1) % len)`. Порожній газетир / `k<=0` → `([], cursor)`.
  - `_load_city_names(entries=None) -> list[str]` — дедуплені назви у стабільному порядку файлу.

- [ ] **Step 1: Write the failing test**

Create `crawler/tests/test_city_axis.py`:

```python
from crawler.discovery.city_axis import CityAxis


def _axis():
    return CityAxis(["Київ", "Львів", "Одеса"])


def test_suffixes_current_city_onto_phrases():
    out, cur = _axis().next_batch(["знижка військовим", "акція ветеранам"], cursor=0, k=2)
    assert out == ["знижка військовим Київ", "акція ветеранам Київ"]
    assert cur == 1


def test_k_caps_phrase_count():
    out, _ = _axis().next_batch(["a", "b", "c"], cursor=1, k=2)
    assert out == ["a Львів", "b Львів"]


def test_cursor_advances_and_wraps():
    out, cur = _axis().next_batch(["x"], cursor=2, k=1)   # last city
    assert out == ["x Одеса"]
    assert cur == 0                                       # wrapped to start


def test_out_of_range_and_negative_cursor_normalised():
    assert _axis().next_batch(["x"], cursor=5, k=1)[0] == ["x Одеса"]    # 5 % 3 == 2
    assert _axis().next_batch(["x"], cursor=-1, k=1)[0] == ["x Одеса"]   # -1 % 3 == 2


def test_k_zero_returns_empty_and_holds_cursor():
    out, cur = _axis().next_batch(["x"], cursor=1, k=0)
    assert out == [] and cur == 1


def test_empty_gazetteer_is_byte_eq_off():
    out, cur = CityAxis([]).next_batch(["x"], cursor=0, k=3)
    assert out == [] and cur == 0


def test_skips_empty_phrases():
    out, _ = _axis().next_batch(["", "  ", "реальна"], cursor=0, k=3)
    assert out == ["реальна Київ"]


def test_deterministic():
    a = _axis()
    assert a.next_batch(["p"], 0, 1) == a.next_batch(["p"], 0, 1)


def test_default_loads_gazetteer():
    assert len(CityAxis()) > 1000        # газетир ~1229 назв
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_city_axis.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'crawler.discovery.city_axis'`.

- [ ] **Step 3: Write minimal implementation**

Create `crawler/crawler/discovery/city_axis.py`:

```python
"""City query axis: suffix a rotating Ukrainian city onto base search phrases.

City is an INDEPENDENT rotating axis (its own cursor), NOT a cartesian product
with the {intent}{audience} grid — one city per pass is appended to a slice of
the current phrase batch, so the (city × phrase) space is swept diagonally over
passes without materialising it. Reuses the shared gazetteer (cities + смт);
the canonical name is the query suffix (inflected forms are for extraction)."""

from crawler.discovery import geo


def _load_city_names(entries=None) -> list[str]:
    entries = geo._load_entries() if entries is None else entries
    seen: set[str] = set()
    out: list[str] = []
    for e in entries:
        name = (e.get("name") or "").strip()
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


class CityAxis:
    """Deterministic rotation over city names; suffixes the current city onto a
    slice of base phrases. One city advance per pass (caller drives the cursor)."""

    def __init__(self, cities: list[str] | None = None):
        self._cities = list(cities) if cities is not None else _load_city_names()

    def __len__(self) -> int:
        return len(self._cities)

    def next_batch(self, base_phrases: list[str], cursor: int, k: int
                   ) -> tuple[list[str], int]:
        size = len(self._cities)
        if size == 0 or k <= 0:
            return [], cursor
        cursor %= size                              # normalises negative / out-of-range
        city = self._cities[cursor]
        out = [f"{p} {city}".strip() for p in base_phrases[:k] if p and p.strip()]
        return out, (cursor + 1) % size
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_city_axis.py -q`
Expected: PASS (9 passed).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/city_axis.py crawler/tests/test_city_axis.py
git commit -m "feat(crawler): CityAxis — rotating city suffix for search phrases"
```

---

### Task 2: `SearchState.city_cursor`

**Files:**
- Modify: `crawler/crawler/discovery/search_state.py:11-13` (`_EMPTY`) та додати accessors після `approved_cursor` (біля `:84`)
- Test: `crawler/tests/test_search_state.py` (доповнити)

**Interfaces:**
- Consumes: наявний `SearchState` (JSON-стан, `_save` атомарний).
- Produces: `SearchState.city_cursor -> int` (дефолт 0) та `SearchState.set_city_cursor(value: int) -> None` (персист). Незалежне поле `"city_cursor"`.

- [ ] **Step 1: Write the failing test**

Append to `crawler/tests/test_search_state.py`:

```python
def test_city_cursor_defaults_zero(tmp_path):
    st = SearchState(str(tmp_path / "s.json"))
    assert st.city_cursor == 0


def test_set_city_cursor_persists_and_is_independent(tmp_path):
    p = str(tmp_path / "s.json")
    st = SearchState(p)
    st.set_grid_cursor(5)
    st.set_city_cursor(9)
    reloaded = SearchState.load(p)
    assert reloaded.city_cursor == 9
    assert reloaded.grid_cursor == 5          # untouched
    assert reloaded.searxng_cursor == -1      # untouched
```

(У файлі вже є `from crawler.discovery.search_state import SearchState` — не дублювати.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_search_state.py::test_city_cursor_defaults_zero tests/test_search_state.py::test_set_city_cursor_persists_and_is_independent -q`
Expected: FAIL — `AttributeError: 'SearchState' object has no attribute 'city_cursor'`.

- [ ] **Step 3: Write minimal implementation**

In `crawler/crawler/discovery/search_state.py`, update `_EMPTY` (add `"city_cursor": 0`):

```python
_EMPTY = {"version": 1, "cursor": 0, "grid_cursor": 0, "site_cursor": 0,
          "approved_cursor": 0, "searxng_cursor": -1, "city_cursor": 0,
          "next_allowed_at": 0.0, "backends": {}, "cache": {}}
```

Add accessors right after the `approved_cursor` block (after line ~83, before `# --- backend health ---`):

```python
    # --- city-axis rotation cursor (independent of grid/searxng/site cursors) ---
    @property
    def city_cursor(self) -> int:
        return int(self._data.get("city_cursor", 0))

    def set_city_cursor(self, value: int) -> None:
        self._data["city_cursor"] = int(value)
        self._save()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_search_state.py -q`
Expected: PASS (усі наявні + 2 нові).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/search_state.py crawler/tests/test_search_state.py
git commit -m "feat(crawler): SearchState.city_cursor — independent city-axis cursor"
```

---

### Task 3: Інтеграція city-осі у `SearchPass`

**Files:**
- Modify: `crawler/crawler/discovery/search_pass.py:11-29` (`__init__` + `run`)
- Test: `crawler/tests/test_search_pass.py` (доповнити)

**Interfaces:**
- Consumes: `CityAxis` (Task 1: `next_batch`, `__len__`), `SearchState.city_cursor`/`set_city_cursor` (Task 2), наявний `merge_queries`.
- Produces: `SearchPass(plans, state, grid, queries_per_pass, static_keywords=None, city_axis=None, city_queries_per_pass=0)`. Коли `city_axis` задано і `city_queries_per_pass>0` і газетир непорожній — city-запити (суфікс поточного міста на зріз базового batch) домержуються у keywords КОЖНОГО провайдера; `city_cursor` просувається +1 раз/прохід, якщо ≥1 провайдер успішний. `self._city_axis` доступне як атрибут (для wiring-тесту).

- [ ] **Step 1: Write the failing test**

Append to `crawler/tests/test_search_pass.py` (файл уже імпортує `SearchPass`, `SearchState`, `QueryGrid`):

```python
from crawler.discovery.city_axis import CityAxis


def test_city_queries_merged_and_cursor_advances(tmp_path):
    st = SearchState(str(tmp_path / "s.json"))
    ddg = _Plan("duckduckgo", "grid_cursor", True, ok=True)
    sp = SearchPass([ddg], st, _grid(), queries_per_pass=2, static_keywords=["пін"],
                    city_axis=CityAxis(["Львів", "Одеса"]), city_queries_per_pass=2)
    sp.run(set())
    # base q0,q1 + pin, then current city (Львів) suffixed onto the base phrases
    assert ddg.discovery.calls == [["q0", "q1", "пін", "q0 Львів", "q1 Львів"]]
    assert st.city_cursor == 1                    # advanced once: (0+1) % 2


def test_city_cursor_holds_when_all_providers_fail(tmp_path):
    st = SearchState(str(tmp_path / "s.json"))
    ddg = _Plan("duckduckgo", "grid_cursor", True, ok=False)
    sp = SearchPass([ddg], st, _grid(), queries_per_pass=2,
                    city_axis=CityAxis(["Львів", "Одеса"]), city_queries_per_pass=2)
    sp.run(set())
    assert st.city_cursor == 0                    # no advance on all-fail


def test_city_axis_absent_is_byte_equivalent(tmp_path):
    st = SearchState(str(tmp_path / "s.json"))
    ddg = _Plan("duckduckgo", "grid_cursor", True, ok=True)
    sp = SearchPass([ddg], st, _grid(), queries_per_pass=2, static_keywords=["пін"])
    sp.run(set())
    assert ddg.discovery.calls == [["q0", "q1", "пін"]]
    assert st.city_cursor == 0


def test_city_queries_per_pass_zero_is_off(tmp_path):
    st = SearchState(str(tmp_path / "s.json"))
    ddg = _Plan("duckduckgo", "grid_cursor", True, ok=True)
    sp = SearchPass([ddg], st, _grid(), queries_per_pass=2,
                    city_axis=CityAxis(["Львів"]), city_queries_per_pass=0)
    sp.run(set())
    assert ddg.discovery.calls == [["q0", "q1"]]
    assert st.city_cursor == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_search_pass.py::test_city_queries_merged_and_cursor_advances -q`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'city_axis'`.

- [ ] **Step 3: Write minimal implementation**

In `crawler/crawler/discovery/search_pass.py`, replace `__init__` and `run`:

```python
    def __init__(self, plans, state, grid, queries_per_pass, static_keywords=None,
                 city_axis=None, city_queries_per_pass=0):
        self._plans = list(plans)
        self._state = state
        self._grid = grid
        self._n = queries_per_pass
        self._pins = list(static_keywords or [])
        self._city_axis = city_axis
        self._city_k = int(city_queries_per_pass or 0)

    def run(self, known) -> list[SourceCandidate]:
        out: list[SourceCandidate] = []
        city_on = (self._city_axis is not None and self._city_k > 0
                   and len(self._city_axis) > 0)
        any_ok = False
        for plan in self._plans:
            start = self._start_for(plan.cursor_key)
            batch, new_cursor = self._grid.next_batch(self._n, start)
            pins = self._pins if plan.include_pins else []
            keywords = merge_queries(batch, pins)
            if city_on:
                city_qs, _ = self._city_axis.next_batch(
                    batch, self._state.city_cursor, self._city_k)
                keywords = merge_queries(keywords, city_qs)
            plan.reset()
            out.extend(plan.discovery.run(keywords, known))
            if plan.succeeded():
                self._set_cursor(plan.cursor_key, new_cursor)
                any_ok = True
        if city_on and any_ok:
            self._state.set_city_cursor(
                (self._state.city_cursor + 1) % len(self._city_axis))
        return out
```

(Метод `provider_for_site_query`, `_start_for`, `_set_cursor` — без змін.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_search_pass.py -q`
Expected: PASS (наявні 3 + нові 4).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/search_pass.py crawler/tests/test_search_pass.py
git commit -m "feat(crawler): SearchPass merges city-axis queries + advances city_cursor"
```

---

### Task 4: Config-ручки `city_axis_enabled` / `city_queries_per_pass`

**Files:**
- Modify: `crawler/crawler/config.py` (`_RawSettings` біля `:33`, `Config` біля `:117`, `load_config` біля `:224`)
- Test: `crawler/tests/test_config.py` (доповнити; якщо файлу немає — створити)

**Interfaces:**
- Consumes: наявні `_RawSettings`/`Config`/`load_config`.
- Produces: `Config.city_axis_enabled: bool = True`, `Config.city_queries_per_pass: int = 10`; читаються з env через `_RawSettings` й прокидаються у `load_config`.

- [ ] **Step 1: Write the failing test**

Append to `crawler/tests/test_config.py` (file already imports `load_config` at top; follow its `monkeypatch.chdir(tmp_path)` + inline-import conventions):

```python
def test_city_axis_raw_defaults():
    from crawler.config import _RawSettings
    s = _RawSettings()
    assert s.city_axis_enabled is True
    assert s.city_queries_per_pass == 10


def test_city_axis_config_dataclass_defaults():
    from crawler.config import Config
    cfg = Config(internal_api_url="x", crawler_api_key="k", extractor="heuristic",
                 active_discovery=False, request_timeout=1.0, min_delay_seconds=0.0)
    assert cfg.city_axis_enabled is True
    assert cfg.city_queries_per_pass == 10


def test_load_config_passes_city_axis(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)      # no .env -> env overrides apply cleanly
    monkeypatch.setenv("CITY_AXIS_ENABLED", "false")
    monkeypatch.setenv("CITY_QUERIES_PER_PASS", "4")
    cfg = load_config()
    assert cfg.city_axis_enabled is False
    assert cfg.city_queries_per_pass == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_config.py -q`
Expected: FAIL — `AttributeError`/`TypeError` (поля `city_axis_enabled` немає).

- [ ] **Step 3: Write minimal implementation**

In `crawler/crawler/config.py`:

(a) `_RawSettings` — додати після `search_queries_per_pass: int = 40` (`:33`):

```python
    city_axis_enabled: bool = True
    city_queries_per_pass: int = 10
```

(b) `Config` dataclass — додати після `search_queries_per_pass: int = 40` (`:117`):

```python
    city_axis_enabled: bool = True
    city_queries_per_pass: int = 10
```

(c) `load_config` — додати після `search_queries_per_pass=s.search_queries_per_pass,` (`:224`):

```python
        city_axis_enabled=s.city_axis_enabled,
        city_queries_per_pass=s.city_queries_per_pass,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_config.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/config.py crawler/tests/test_config.py
git commit -m "feat(crawler): config knobs city_axis_enabled / city_queries_per_pass"
```

---

### Task 5: Wiring `CityAxis` у `build_runner`

**Files:**
- Modify: `crawler/crawler/wiring.py:17` (import) та `:114-120` (блок `if config.active_discovery:`)
- Test: `crawler/tests/test_wiring.py` (доповнити; використовує наявний `_base_cfg`)

**Interfaces:**
- Consumes: `CityAxis` (Task 1), `SearchPass(..., city_axis=, city_queries_per_pass=)` (Task 3), `Config.city_axis_enabled`/`city_queries_per_pass` (Task 4).
- Produces: `build_runner` передає `CityAxis()` у `SearchPass`, коли `active_discovery` та `city_axis_enabled`; інакше `city_axis=None`. `runner._search_pass._city_axis` відображає стан.

- [ ] **Step 1: Write the failing test**

Append to `crawler/tests/test_wiring.py` (наявний `_base_cfg` має `search_providers=[]`, `search_state_path`, `brand_feed_enabled=False`, `osm_feed_enabled=False`):

```python
def test_build_runner_wires_city_axis(tmp_path):
    cfg = _base_cfg(tmp_path, active_discovery=True, search_providers=["duckduckgo"],
                    city_axis_enabled=True)
    runner = build_runner(cfg)
    assert runner._search_pass is not None
    assert runner._search_pass._city_axis is not None
    assert len(runner._search_pass._city_axis) > 1000        # gazetteer loaded
    assert runner._search_pass._city_k == 10                 # default budget


def test_build_runner_city_axis_disabled(tmp_path):
    cfg = _base_cfg(tmp_path, active_discovery=True, search_providers=["duckduckgo"],
                    city_axis_enabled=False)
    runner = build_runner(cfg)
    assert runner._search_pass is not None
    assert runner._search_pass._city_axis is None            # byte-eq off
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_wiring.py::test_build_runner_wires_city_axis -q`
Expected: FAIL — `AttributeError: 'SearchPass' object has no attribute '_city_axis'` НЕ виникне (Task 3 додав), але `city_axis` не передається → `_city_axis is None`, тож assert `is not None` FAIL.

- [ ] **Step 3: Write minimal implementation**

In `crawler/crawler/wiring.py`, add import near `:17`:

```python
from crawler.discovery.city_axis import CityAxis
```

Replace the `if plans:` block inside `if config.active_discovery:` (`:117-120`):

```python
        if plans:
            city_axis = CityAxis() if config.city_axis_enabled else None
            search_pass = SearchPass(plans, state, QueryGrid(),
                                     config.search_queries_per_pass, config.search_keywords,
                                     city_axis=city_axis,
                                     city_queries_per_pass=config.city_queries_per_pass)
            discovery = search_pass.provider_for_site_query()   # DDG discovery for site: queries
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_wiring.py -q`
Expected: PASS (наявні + 2 нові).

- [ ] **Step 5: Run the full crawler suite**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — усі наявні (~455) + нові city-axis тести зелені.

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/wiring.py crawler/tests/test_wiring.py
git commit -m "feat(crawler): wire CityAxis into SearchPass via build_runner"
```

---

## Post-implementation

- Requesting-code-review (opus whole-branch) перед merge.
- Жива Docker-перевірка: з `active_discovery=ON` + `city_axis_enabled=ON` підтвердити, що пошук видає city-суфіксні запити (лог keywords) і краулер стійкий.
- Merge (ff) у `main`, push, оновити `docs/RESUME.md` + пам'ять.

## Self-Review (виконано)

**Spec coverage:** джерело міст (Global Constraints + Task 1) · CityAxis-компонент (Task 1) · SearchState.city_cursor (Task 2) · SearchPass-інтеграція + advance-on-success + byte-eq (Task 3) · config-ручки (Task 4) · wiring (Task 5) · «не чіпаємо» (Global Constraints) · окуповані-компроміс (спец, свідомо поза скоупом). Усі секції спеки мають таск.

**Placeholder scan:** плейсхолдерів немає — увесь код наведено дослівно.

**Type consistency:** `next_batch(base_phrases, cursor, k) -> (list, int)`, `__len__`, `city_cursor`/`set_city_cursor`, `SearchPass(..., city_axis=, city_queries_per_pass=)`, `_city_axis`/`_city_k` — узгоджені між Tasks 1→3→5.
