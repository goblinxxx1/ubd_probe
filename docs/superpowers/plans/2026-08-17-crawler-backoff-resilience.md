# Crawler Backoff Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Зробити global backoff рідшим, а активні проходи довшими/частішими — прибравши отруєння пулу мертвими бекендами, фіксований 6-год «все-або-нічого» бекоф, і додавши SearXNG як незалежний search-провайдер.

**Architecture:** Бекоф стає властивістю окремого бекенда/провайдера. (1) Мертві DDG-бекенди карантиняться й перестають зводити global backoff. (2) Global backoff стає динамічним (сон до найближчого відновлення, а не 6 год). (3) SearXNG воскресає як другий незалежний провайдер; `SearchPass` і `run_active` перестають глушити весь пошук під DDG-бекофом — кожен провайдер сам-гейтиться, тож активний прохід (включно з `site:`) триває, поки живий хоч один провайдер.

**Tech Stack:** Python 3.12, `ddgs`, `httpx`, `pytest`; Docker Compose; self-hosted `searxng/searxng`.

## Global Constraints

- **Мова:** без російських джерел/сервісів будь-де (у т.ч. engine `yandex` у SearXNG — ЗАБОРОНЕНО). Коментарі/повідомлення — українською де доречно, код — англійською як у наявному коді.
- **Back-compat:** за одного провайдера (`search_providers=duckduckgo`) і повного здоров'я поведінка має лишатися байт-ідентичною поточній; наявні тести мусять лишатися зеленими.
- **TDD:** кожна задача — спершу падаючий тест, потім мінімальна реалізація.
- **Тести:** запуск із `crawler/` через `python -m pytest` (див. нижче кожну команду).
- **Дефолти (затверджено, «збалансовано»):** quarantine_threshold=6, quarantine_hours=24, reprobe_hours=6, backoff_floor_seconds=300.
- **Файли стану:** `SearchState` — JSON у `/data/search_state.json`; back-compat при `load` (нові ключі через `setdefault`/`.get`).

---

## File Structure

- `crawler/crawler/discovery/search_state.py` — додати карантин-поля/переходи + `soonest_recovery`; динамічний backoff зберігає `next_allowed_at` (значення тепер похідне, не фіксовані 6 год).
- `crawler/crawler/discovery/providers.py` — `RotatingDdgProvider` враховує карантин при виборі й all-cool; воскресити `SearxngProvider` з власним легким health; `SearchProviderPlan.available`; `build_search_plans` гілка `searxng`; адаптивний `min_delay`.
- `crawler/crawler/discovery/search_pass.py` — `run()` ітерує ВСІ плани; `provider_for_site_query()` і `any_provider_available()` — health-aware.
- `crawler/crawler/runner.py` — `run_active` бере `site:`-провайдер динамічно від `SearchPass` (живий провайдер), не зі статичного `self._discovery`.
- `crawler/crawler/scheduler.py` — `step()` вирішує degraded/повний прохід за `search_available` (будь-який живий провайдер), не за DDG-only.
- `crawler/crawler/__main__.py` — прокинути `search_available` у `run_loop`.
- `crawler/crawler/config.py` — нові поля (обидва: `_RawSettings` і `Config`, + мапінг у `from_settings`).
- `docker-compose.yml` (+ `docker/searxng/settings.yml`) — сервіс `searxng`.
- Тести: `crawler/tests/test_search_state.py`, `test_rotating_provider.py`, `test_providers.py`, `test_search_pass.py`, `test_scheduler.py`, новий `test_searxng_provider.py`, `test_build_provider.py`, `test_search_config.py`.

---

## PHASE 1 — Гігієна здоров'я бекендів

### Task 1: Карантин-поля й переходи у `SearchState`

**Files:**
- Modify: `crawler/crawler/discovery/search_state.py`
- Test: `crawler/tests/test_search_state.py`

**Interfaces:**
- Consumes: наявні `SearchState(path, data, clock)`, `record_block(backend, base, cap, jitter, rand)`, `record_success(backend)`.
- Produces:
  - `record_block(backend, base, cap, jitter, rand, *, quarantine_threshold=0, quarantine_seconds=0.0, reprobe_seconds=0.0) -> float` (нові kw-only параметри; при 0 — поведінка як раніше).
  - `record_success(backend)` — тепер чистить і карантин-поля.
  - `is_quarantined(backend) -> bool`
  - `reprobe_due(backend) -> bool`
  - `soonest_recovery(pool: list[str], floor: float) -> float`

- [ ] **Step 1: Написати падаючі тести**

Додати в `crawler/tests/test_search_state.py`:

```python
def test_record_block_quarantines_at_threshold(tmp_path):
    clock = _Clock(1000.0)  # helper below
    st = SearchState(str(tmp_path / "s.json"), clock=clock)
    # 5 fails: not yet quarantined (threshold 6)
    for _ in range(5):
        st.record_block("google", 300.0, 21600.0, 0.0, lambda: 0.0,
                        quarantine_threshold=6, quarantine_seconds=24*3600, reprobe_seconds=6*3600)
    assert st.is_quarantined("google") is False
    # 6th fail: quarantined for 24h, first re-probe in 6h
    st.record_block("google", 300.0, 21600.0, 0.0, lambda: 0.0,
                    quarantine_threshold=6, quarantine_seconds=24*3600, reprobe_seconds=6*3600)
    assert st.is_quarantined("google") is True
    assert st.reprobe_due("google") is False
    clock.t += 6*3600            # 6h later → re-probe due
    assert st.reprobe_due("google") is True

def test_record_success_clears_quarantine(tmp_path):
    clock = _Clock(1000.0)
    st = SearchState(str(tmp_path / "s.json"), clock=clock)
    for _ in range(6):
        st.record_block("google", 300.0, 21600.0, 0.0, lambda: 0.0,
                        quarantine_threshold=6, quarantine_seconds=24*3600, reprobe_seconds=6*3600)
    assert st.is_quarantined("google") is True
    st.record_success("google")
    assert st.is_quarantined("google") is False
    assert st.reprobe_due("google") is False

def test_soonest_recovery_min_over_nonquarantined_with_floor(tmp_path):
    clock = _Clock(1000.0)
    st = SearchState(str(tmp_path / "s.json"), clock=clock)
    # yahoo cooled 100s out, brave cooled 900s out; floor 300 → min(100,900) clamped to 300
    st._data["backends"] = {
        "yahoo": {"fails": 1, "cooldown_until": 1100.0, "quarantined_until": 0.0, "next_reprobe_at": 0.0},
        "brave": {"fails": 2, "cooldown_until": 1900.0, "quarantined_until": 0.0, "next_reprobe_at": 0.0},
    }
    assert st.soonest_recovery(["yahoo", "brave"], floor=300.0) == 300.0
    # raise yahoo cooldown above floor → min wins
    st._data["backends"]["yahoo"]["cooldown_until"] = 1500.0  # 500s out
    assert st.soonest_recovery(["yahoo", "brave"], floor=300.0) == 500.0
```

Додати helper угорі файлу (якщо ще нема схожого):

```python
class _Clock:
    def __init__(self, t=1000.0): self.t = t
    def __call__(self): return self.t
```

- [ ] **Step 2: Запустити — переконатися, що падають**

Run: `cd crawler && python -m pytest tests/test_search_state.py -k "quarantine or soonest" -v`
Expected: FAIL (`record_block() got an unexpected keyword argument 'quarantine_threshold'` / `AttributeError: is_quarantined`)

- [ ] **Step 3: Реалізувати**

У `search_state.py` замінити `record_block` і `record_success`, додати три хелпери. Замінити наявний `record_block`:

```python
    def record_success(self, backend: str) -> None:
        self._data["backends"][backend] = {
            "fails": 0, "cooldown_until": 0.0,
            "quarantined_until": 0.0, "next_reprobe_at": 0.0}
        self._save()

    def record_block(self, backend: str, base: float, cap: float, jitter: float, rand,
                     *, quarantine_threshold: int = 0, quarantine_seconds: float = 0.0,
                     reprobe_seconds: float = 0.0) -> float:
        b = self._data["backends"].get(backend) or {"fails": 0, "cooldown_until": 0.0}
        fails = int(b.get("fails", 0)) + 1
        delay = min(base * (2 ** (fails - 1)), cap) * (1 + rand() * jitter)
        now = self._clock()
        entry = {"fails": fails, "cooldown_until": now + delay,
                 "quarantined_until": b.get("quarantined_until", 0.0),
                 "next_reprobe_at": b.get("next_reprobe_at", 0.0)}
        # Structurally-dead backend: quarantine it so it stops dragging the pool to all-cool.
        # A failing re-probe re-enters here (fails already >= threshold) → quarantine re-extended
        # and next re-probe pushed out. A success (record_success) is the only reset.
        if quarantine_threshold and fails >= quarantine_threshold:
            entry["quarantined_until"] = now + quarantine_seconds
            entry["next_reprobe_at"] = now + reprobe_seconds
        self._data["backends"][backend] = entry
        self._save()
        return delay

    def is_quarantined(self, backend: str) -> bool:
        b = self._data["backends"].get(backend)
        return bool(b) and self._clock() < b.get("quarantined_until", 0.0)

    def reprobe_due(self, backend: str) -> bool:
        """Quarantined AND its single low-frequency trial window has arrived."""
        b = self._data["backends"].get(backend)
        if not b:
            return False
        now = self._clock()
        return now < b.get("quarantined_until", 0.0) and now >= b.get("next_reprobe_at", 0.0)

    def soonest_recovery(self, pool: list[str], floor: float) -> float:
        """Seconds until the earliest backend becomes selectable again, clamped up to `floor`.
        Quarantined-not-due backends contribute their next_reprobe_at; others their cooldown."""
        now = self._clock()
        remaining = []
        for name in pool:
            e = self._data["backends"].get(name)
            if e is None:
                continue
            if now < e.get("quarantined_until", 0.0) and now < e.get("next_reprobe_at", 0.0):
                remaining.append(e.get("next_reprobe_at", 0.0) - now)
            else:
                remaining.append(max(0.0, e.get("cooldown_until", 0.0) - now))
        base = min(remaining) if remaining else floor
        return max(floor, base)
```

- [ ] **Step 4: Запустити — зелено**

Run: `cd crawler && python -m pytest tests/test_search_state.py -v`
Expected: PASS (усі, включно з наявними — сигнатура back-compat через kw-only з дефолтами)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/search_state.py crawler/tests/test_search_state.py
git commit -m "feat(crawler): SearchState backend quarantine + soonest_recovery"
```

---

### Task 2: `RotatingDdgProvider` — вибір з урахуванням карантину + динамічний all-cool

**Files:**
- Modify: `crawler/crawler/discovery/providers.py:55-115` (`RotatingDdgProvider`)
- Test: `crawler/tests/test_rotating_provider.py`

**Interfaces:**
- Consumes: `SearchState.record_block(..., quarantine_threshold=, quarantine_seconds=, reprobe_seconds=)`, `is_quarantined`, `reprobe_due`, `is_healthy`, `soonest_recovery`, `set_global_backoff`.
- Produces: `RotatingDdgProvider(..., quarantine_threshold=0, quarantine_hours=0.0, reprobe_hours=0.0, backoff_floor=300.0)` (нові kw params). Метод `_selectable(backend) -> bool`.

- [ ] **Step 1: Написати падаючі тести**

Додати в `crawler/tests/test_rotating_provider.py` (використовує наявні `POOL`, `Clock`, `RecordingDDGS`, `_provider`; у `_provider` дефолтний `kw` уже має потрібні поля — розширити виклик через `**over`):

```python
class FailingDDGS:
    def text(self, query, max_results=7, backend=None):
        raise RuntimeError("boom")

def test_quarantined_backend_excluded_from_pool(tmp_path):
    clock = Clock()
    # cooldown_base=0 → a failed backend isn't cooled, so round-robin keeps hitting it and
    # google reaches the quarantine threshold. (With a real cooldown a dead backend is simply
    # skipped while cooled; quarantine is what stops it dragging all-cool once cooldown lapses.)
    p, st = _provider(tmp_path, clock, FailingDDGS, cooldown_base=0.0,
                      quarantine_threshold=2, quarantine_hours=24.0, reprobe_hours=6.0)
    for _ in range(8):                       # 2 backends per call → google fails >= 2
        p("kw")
    assert st.is_quarantined("google") is True

def test_all_cool_sets_dynamic_backoff_not_fixed_6h(tmp_path):
    clock = Clock()
    # cap cooldowns low so soonest_recovery is small; floor makes it 300
    p, st = _provider(tmp_path, clock, FailingDDGS, cooldown_base=10.0, cooldown_cap=50.0,
                      quarantine_threshold=99, backoff_floor=300.0)
    for _ in range(20):
        p("kw")           # exhaust all backends into cooldown
    secs = st.seconds_until_allowed()
    assert 0 < secs <= 300.0      # dynamic (<= floor), NOT 6h (21600)
```

- [ ] **Step 2: Запустити — падають**

Run: `cd crawler && python -m pytest tests/test_rotating_provider.py -k "quarantin or dynamic" -v`
Expected: FAIL (`__init__() got an unexpected keyword argument 'quarantine_threshold'`)

- [ ] **Step 3: Реалізувати**

У `providers.py`, `RotatingDdgProvider.__init__` — додати параметри й зберегти:

```python
    def __init__(self, pool, state: SearchState, results_per_keyword: int = 7,
                 min_delay: float = 45.0, jitter: float = 0.5, cooldown_base: float = 300.0,
                 cooldown_cap: float = 21600.0, global_backoff_seconds: float = 21600.0,
                 quarantine_threshold: int = 0, quarantine_hours: float = 0.0,
                 reprobe_hours: float = 0.0, backoff_floor: float = 300.0,
                 ddgs_factory=DDGS, sleep=time.sleep, rand=random.random):
        self._pool = list(pool)
        self._state = state
        self._n = results_per_keyword
        self._delay = min_delay
        self._jitter = jitter
        self._base = cooldown_base
        self._cap = cooldown_cap
        self._global_backoff = global_backoff_seconds
        self._q_threshold = quarantine_threshold
        self._q_seconds = quarantine_hours * 3600
        self._reprobe_seconds = reprobe_hours * 3600
        self._backoff_floor = backoff_floor
        self._ddgs_factory = ddgs_factory
        self._sleep = sleep
        self._rand = rand
```

Замінити `_take_next_healthy` і додати `_selectable`; у `__call__` — all-cool гілка й `record_block` з карантин-параметрами. Патчі:

```python
    def _selectable(self, backend: str) -> bool:
        if self._state.reprobe_due(backend):     # one low-frequency trial for a dead backend
            return True
        if self._state.is_quarantined(backend):  # quarantined & not due → skip
            return False
        return self._state.is_healthy(backend)   # normal transient cooldown check

    def _take_next_healthy(self) -> str | None:
        n = len(self._pool)
        if n == 0:
            return None
        start = self._state.cursor % n
        for offset in range(n):
            idx = (start + offset) % n
            backend = self._pool[idx]
            if self._selectable(backend):
                self._state.set_cursor((idx + 1) % n)
                return backend
        return None
```

У `__call__` — замінити два місця:

```python
        for _ in range(2):
            backend = self._take_next_healthy()
            if backend is None:
                # all non-quarantined backends cooled → sleep only until the soonest recovers
                self._state.set_global_backoff(
                    self._state.soonest_recovery(self._pool, self._backoff_floor))
                self._state.mark_degraded()
                return []
            self._sleep(self._delay * (1 + self._rand() * self._jitter))
            try:
                results = self._ddgs_factory().text(keyword, max_results=self._n, backend=backend)
            except Exception as exc:  # noqa: BLE001 — search is best-effort
                log.warning("ddg backend %s failed for %r: %s", backend, keyword, exc)
                self._state.record_block(backend, self._base, self._cap, self._jitter, self._rand,
                                         quarantine_threshold=self._q_threshold,
                                         quarantine_seconds=self._q_seconds,
                                         reprobe_seconds=self._reprobe_seconds)
                continue
            self._state.record_success(backend)
            return self._classify(results, backend, keyword)
```

- [ ] **Step 4: Запустити — зелено**

Run: `cd crawler && python -m pytest tests/test_rotating_provider.py -v`
Expected: PASS (нові + наявні; наявні передають `quarantine_threshold=0` за замовч. → карантин вимкнено, поведінка як раніше)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/providers.py crawler/tests/test_rotating_provider.py
git commit -m "feat(crawler): quarantine-aware backend selection + dynamic all-cool backoff"
```

---

## PHASE 2 — Динамічний backoff (проводка дефолтів)

### Task 3: Прокинути карантин/floor-дефолти через config у `build_search_plans`

**Files:**
- Modify: `crawler/crawler/config.py` (`_RawSettings`, `Config`, `from_settings`)
- Modify: `crawler/crawler/discovery/providers.py` (`build_search_plans` — передати нові параметри)
- Test: `crawler/tests/test_search_config.py`, `crawler/tests/test_build_provider.py`

**Interfaces:**
- Consumes: `Config`, `RotatingDdgProvider(quarantine_threshold=, quarantine_hours=, reprobe_hours=, backoff_floor=)`.
- Produces: `Config.search_backend_quarantine_threshold: int`, `Config.search_backend_quarantine_hours: float`, `Config.search_backend_reprobe_hours: float`, `Config.search_backoff_floor_seconds: float`.

- [ ] **Step 1: Написати падаючий тест**

Додати в `crawler/tests/test_search_config.py`:

```python
def test_backoff_hygiene_defaults():
    from crawler.config import _RawSettings, from_settings
    cfg = from_settings(_RawSettings())
    assert cfg.search_backend_quarantine_threshold == 6
    assert cfg.search_backend_quarantine_hours == 24.0
    assert cfg.search_backend_reprobe_hours == 6.0
    assert cfg.search_backoff_floor_seconds == 300.0
```

- [ ] **Step 2: Запустити — падає**

Run: `cd crawler && python -m pytest tests/test_search_config.py::test_backoff_hygiene_defaults -v`
Expected: FAIL (`AttributeError: 'Config' object has no attribute 'search_backend_quarantine_threshold'`)

- [ ] **Step 3: Реалізувати**

`_RawSettings` (після `search_global_backoff_hours`):

```python
    search_backend_quarantine_threshold: int = 6
    search_backend_quarantine_hours: float = 24.0
    search_backend_reprobe_hours: float = 6.0
    search_backoff_floor_seconds: float = 300.0
```

`Config` dataclass (після `search_global_backoff_hours: float = 6.0`):

```python
    search_backend_quarantine_threshold: int = 6
    search_backend_quarantine_hours: float = 24.0
    search_backend_reprobe_hours: float = 6.0
    search_backoff_floor_seconds: float = 300.0
```

`from_settings` (після `search_global_backoff_hours=s.search_global_backoff_hours,`):

```python
        search_backend_quarantine_threshold=s.search_backend_quarantine_threshold,
        search_backend_quarantine_hours=s.search_backend_quarantine_hours,
        search_backend_reprobe_hours=s.search_backend_reprobe_hours,
        search_backoff_floor_seconds=s.search_backoff_floor_seconds,
```

`build_search_plans` — у конструктор `RotatingDdgProvider(...)` додати:

```python
                global_backoff_seconds=config.search_global_backoff_hours * 3600,
                quarantine_threshold=config.search_backend_quarantine_threshold,
                quarantine_hours=config.search_backend_quarantine_hours,
                reprobe_hours=config.search_backend_reprobe_hours,
                backoff_floor=config.search_backoff_floor_seconds)
```

- [ ] **Step 4: Запустити — зелено**

Run: `cd crawler && python -m pytest tests/test_search_config.py tests/test_build_provider.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/config.py crawler/crawler/discovery/providers.py crawler/tests/test_search_config.py
git commit -m "feat(crawler): wire quarantine/backoff-floor config into DDG provider"
```

---

## PHASE 3 — Тюнінг тиску

### Task 4: Адаптивний `min_delay` + довший TTL за замовчуванням

**Files:**
- Modify: `crawler/crawler/discovery/providers.py` (`RotatingDdgProvider` — множник затримки)
- Modify: `crawler/crawler/config.py` (`search_cache_ttl_hours` дефолт 96 → 168)
- Test: `crawler/tests/test_rotating_provider.py`

**Interfaces:**
- Produces: `RotatingDdgProvider._adaptive_delay() -> float` — базовий `min_delay`, помножений на `pool_size / healthy_count` (менше живих → довша пауза); за повного здоров'я == `min_delay` (байт-ідентично).

- [ ] **Step 1: Написати падаючі тести**

```python
def test_adaptive_delay_scales_with_unhealthy(tmp_path):
    clock = Clock()
    p, st = _provider(tmp_path, clock, FailingDDGS, min_delay=10.0, jitter=0.0)
    # full health: multiplier 1.0
    assert p._adaptive_delay() == 10.0
    # quarantine 3 of 5 backends → 2 healthy → multiplier 5/2 = 2.5 → 25.0
    for name in ("google", "startpage", "duckduckgo"):
        st._data["backends"][name] = {"fails": 9, "cooldown_until": clock.t + 999,
                                      "quarantined_until": clock.t + 999, "next_reprobe_at": clock.t + 999}
    assert p._adaptive_delay() == 25.0
```

- [ ] **Step 2: Запустити — падає**

Run: `cd crawler && python -m pytest tests/test_rotating_provider.py -k adaptive -v`
Expected: FAIL (`AttributeError: '_adaptive_delay'`)

- [ ] **Step 3: Реалізувати**

Додати метод і застосувати його у `__call__` замість `self._delay`:

```python
    def _adaptive_delay(self) -> float:
        healthy = sum(1 for b in self._pool if self._selectable(b))
        if healthy <= 0:
            return self._delay
        return self._delay * (len(self._pool) / healthy)
```

У `__call__` рядок `self._sleep(self._delay * (1 + self._rand() * self._jitter))` → замінити на:

```python
            self._sleep(self._adaptive_delay() * (1 + self._rand() * self._jitter))
```

Config: `search_cache_ttl_hours: int = 168` у `_RawSettings` і в `Config` dataclass (обидва місця, було `96`).

- [ ] **Step 4: Запустити — зелено**

Run: `cd crawler && python -m pytest tests/test_rotating_provider.py tests/test_search_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/providers.py crawler/crawler/config.py crawler/tests/test_rotating_provider.py
git commit -m "feat(crawler): adaptive search delay under partial pool health + longer cache TTL"
```

---

## PHASE 4 — SearXNG як незалежний провайдер

### Task 5: Воскресити `SearxngProvider` з власним легким health

**Files:**
- Modify: `crawler/crawler/discovery/providers.py` (додати клас; `import httpx`)
- Test: Create `crawler/tests/test_searxng_provider.py`

**Interfaces:**
- Produces: `SearxngProvider(base_url, results_per_keyword=7, min_delay=4.0, client_factory=None, sleep=time.sleep, clock=time.time, fail_threshold=3, cooldown_base=300.0, cooldown_cap=3600.0)`; callable `(keyword) -> list[SourceCandidate]`; `available() -> bool`; `succeeded() -> bool`.

- [ ] **Step 1: Написати падаючі тести**

Create `crawler/tests/test_searxng_provider.py`:

```python
from crawler.discovery.providers import SearxngProvider


class _Clock:
    def __init__(self, t=1000.0): self.t = t
    def __call__(self): return self.t


class _Resp:
    def __init__(self, payload): self._p = payload
    def raise_for_status(self): pass
    def json(self): return self._p


class _Client:
    def __init__(self, payload=None, boom=False):
        self._payload = payload or {"results": []}
        self._boom = boom
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def get(self, url, params=None):
        if self._boom:
            raise RuntimeError("connection refused")
        return _Resp(self._payload)


def test_parses_results_into_candidates():
    payload = {"results": [{"title": "Крамниця", "url": "https://shop.ua/x"}]}
    p = SearxngProvider("http://searxng:8080", client_factory=lambda: _Client(payload),
                        sleep=lambda _s: None)
    cands = p("знижки військовим")
    assert cands[0].type == "website"
    assert cands[0].url_or_handle == "https://shop.ua/x"
    assert cands[0].discovery_note == "searxng: знижки військовим"
    assert p.succeeded() is True
    assert p.available() is True


def test_failure_cools_after_threshold():
    clock = _Clock()
    p = SearxngProvider("http://searxng:8080", client_factory=lambda: _Client(boom=True),
                        sleep=lambda _s: None, clock=clock, fail_threshold=3,
                        cooldown_base=100.0, cooldown_cap=1000.0)
    for _ in range(3):
        assert p("kw") == []
    assert p.available() is False           # 3rd failure trips its own cooldown
    clock.t += 1000                          # cooldown elapsed
    assert p.available() is True
```

- [ ] **Step 2: Запустити — падає**

Run: `cd crawler && python -m pytest tests/test_searxng_provider.py -v`
Expected: FAIL (`ImportError: cannot import name 'SearxngProvider'`)

- [ ] **Step 3: Реалізувати**

У `providers.py` переконатися, що є `import httpx` угорі (додати, якщо нема). Додати клас (перед `SearchProviderPlan`):

```python
class SearxngProvider:
    """Callable (keyword) -> list[SourceCandidate] via a self-hosted SearXNG JSON API.
    Independent of DDG: keeps its own consecutive-failure cooldown so a throttled SearXNG
    self-suppresses without touching the DDG SearchState global backoff."""

    def __init__(self, base_url: str, results_per_keyword: int = 7, min_delay: float = 4.0,
                 client_factory=None, sleep=time.sleep, clock=time.time,
                 fail_threshold: int = 3, cooldown_base: float = 300.0,
                 cooldown_cap: float = 3600.0):
        self._base = base_url.rstrip("/")
        self._n = results_per_keyword
        self._delay = min_delay
        self._client_factory = client_factory or (lambda: httpx.Client(timeout=20))
        self._sleep = sleep
        self._clock = clock
        self._fail_threshold = fail_threshold
        self._cooldown_base = cooldown_base
        self._cooldown_cap = cooldown_cap
        self._fails = 0
        self._cooldown_until = 0.0
        self._slice_ok = False

    def available(self) -> bool:
        return self._clock() >= self._cooldown_until

    def succeeded(self) -> bool:
        return self._slice_ok

    def __call__(self, keyword: str) -> list[SourceCandidate]:
        self._slice_ok = False
        if self._clock() < self._cooldown_until:
            return []
        if self._delay:
            self._sleep(self._delay)
        try:
            with self._client_factory() as client:
                resp = client.get(f"{self._base}/search",
                                  params={"q": keyword, "format": "json"})
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001 — search is best-effort
            log.warning("searxng search failed for %r: %s", keyword, exc)
            self._fails += 1
            if self._fails >= self._fail_threshold:
                over = self._fails - self._fail_threshold
                self._cooldown_until = self._clock() + min(
                    self._cooldown_base * (2 ** over), self._cooldown_cap)
            return []
        self._fails = 0
        self._cooldown_until = 0.0
        self._slice_ok = True
        out: list[SourceCandidate] = []
        for r in (data.get("results") or [])[:self._n]:
            classified = classify_candidate(r.get("url", ""))
            if classified is None:
                continue
            type_, url_or_handle = classified
            out.append(SourceCandidate(
                name=r.get("title") or url_or_handle, type=type_, url_or_handle=url_or_handle,
                discovered_from_source_id=None, discovery_note=f"searxng: {keyword}"))
        return out
```

- [ ] **Step 4: Запустити — зелено**

Run: `cd crawler && python -m pytest tests/test_searxng_provider.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/providers.py crawler/tests/test_searxng_provider.py
git commit -m "feat(crawler): resurrect SearxngProvider with independent self-cooldown"
```

---

### Task 6: `SearchProviderPlan.available` + гілка `searxng` у `build_search_plans` + config

**Files:**
- Modify: `crawler/crawler/discovery/providers.py` (`SearchProviderPlan`, `build_search_plans`)
- Modify: `crawler/crawler/config.py` (`searxng_url`, `searxng_engines`, `searxng_min_delay`, `search_providers` дефолт)
- Test: `crawler/tests/test_build_provider.py`, `crawler/tests/test_search_config.py`

**Interfaces:**
- Consumes: `SearxngProvider`, `RotatingDdgProvider`, `SearchCache`, `ActiveDiscovery`.
- Produces: `SearchProviderPlan(name, discovery, include_pins, succeeded, available)` (нове поле `available: Callable[[], bool]`); `build_search_plans` повертає план `searxng`, коли `"searxng"` у `config.search_providers`.

- [ ] **Step 1: Написати падаючий тест**

Додати в `crawler/tests/test_build_provider.py` (перевір наявні імпорти/фікстури `Config` у файлі й використай той самий спосіб конструювання config; нижче — мінімальний варіант через `from_settings`):

```python
def test_build_plans_includes_searxng_when_enabled():
    from crawler.config import _RawSettings, from_settings
    from crawler.discovery.providers import build_search_plans
    cfg = from_settings(_RawSettings(search_providers="duckduckgo,searxng",
                                     active_discovery=True))
    plans = build_search_plans(cfg)
    names = [p.name for p in plans]
    assert names == ["duckduckgo", "searxng"]
    assert all(callable(p.available) for p in plans)
    # searxng plan is independent of DDG global backoff
    searxng = [p for p in plans if p.name == "searxng"][0]
    assert searxng.available() is True
```

Додати в `crawler/tests/test_search_config.py`:

```python
def test_searxng_config_defaults():
    from crawler.config import _RawSettings, from_settings
    cfg = from_settings(_RawSettings())
    assert cfg.searxng_url == "http://searxng:8080"
    assert "yandex" not in cfg.searxng_engines
    assert "google" not in cfg.searxng_engines
```

- [ ] **Step 2: Запустити — падає**

Run: `cd crawler && python -m pytest tests/test_build_provider.py::test_build_plans_includes_searxng_when_enabled tests/test_search_config.py::test_searxng_config_defaults -v`
Expected: FAIL (`TypeError: __init__() missing ... 'available'` / `AttributeError: searxng_url`)

- [ ] **Step 3: Реалізувати**

Config `_RawSettings` (після blok Task 3):

```python
    searxng_url: str = "http://searxng:8080"
    searxng_engines: str = "duckduckgo,brave,mojeek,qwant,marginalia,wikidata"  # no google/bing/yandex
    searxng_min_delay: float = 4.0
```

І змінити дефолт провайдерів:

```python
    search_providers: str = "duckduckgo,searxng"
```

Config dataclass:

```python
    searxng_url: str = "http://searxng:8080"
    searxng_engines: str = "duckduckgo,brave,mojeek,qwant,marginalia,wikidata"
    searxng_min_delay: float = 4.0
```

`from_settings`:

```python
        searxng_url=s.searxng_url,
        searxng_engines=s.searxng_engines,
        searxng_min_delay=s.searxng_min_delay,
```

`SearchProviderPlan` — додати поле:

```python
@dataclass
class SearchProviderPlan:
    """One search provider bound to its own ActiveDiscovery, per-pass success check,
    and forward-looking availability (health) predicate. Consumed by SearchPass."""
    name: str
    discovery: ActiveDiscovery
    include_pins: bool
    succeeded: Callable[[], bool]
    available: Callable[[], bool]
```

`build_search_plans` — у DDG-гілці додати `available`, і додати гілку `searxng`:

```python
        if name == "duckduckgo":
            if state is None:
                state = SearchState.load(config.search_state_path)
            rotating = RotatingDdgProvider(
                pool=config.search_backends, state=state,
                results_per_keyword=config.search_results_per_keyword,
                min_delay=config.search_min_delay, jitter=config.search_jitter,
                cooldown_base=config.search_backend_cooldown_base_seconds,
                cooldown_cap=config.search_backend_cooldown_cap_seconds,
                global_backoff_seconds=config.search_global_backoff_hours * 3600,
                quarantine_threshold=config.search_backend_quarantine_threshold,
                quarantine_hours=config.search_backend_quarantine_hours,
                reprobe_hours=config.search_backend_reprobe_hours,
                backoff_floor=config.search_backoff_floor_seconds)
            provider = SearchCache(rotating, state, config.search_cache_ttl_hours * 3600)
            plans.append(SearchProviderPlan(
                name="duckduckgo",
                discovery=ActiveDiscovery(budget=budget, search_provider=provider),
                include_pins=True,
                succeeded=(lambda st=state: not st.in_global_backoff()),
                available=(lambda st=state: not st.in_global_backoff())))
        elif name == "searxng":
            sx = SearxngProvider(config.searxng_url,
                                 results_per_keyword=config.search_results_per_keyword,
                                 min_delay=config.searxng_min_delay)
            plans.append(SearchProviderPlan(
                name="searxng",
                discovery=ActiveDiscovery(budget=budget, search_provider=sx),
                include_pins=True,
                succeeded=sx.succeeded,
                available=sx.available))
        else:
            log.warning("unknown search provider %r, ignoring", name)
```

**Note:** SearXNG-запит має нести обраний список рушіїв. Найпростіше — передати `engines` у params. Розширити `SearxngProvider.__init__` параметром `engines: str = ""`, і якщо непорожній — додавати `params["engines"] = engines`. У `build_search_plans` передати `engines=config.searxng_engines`. (Оновити `SearxngProvider` і тест `test_parses_results_into_candidates` не ламається, бо `_Client.get` ігнорує params.)

Патч `SearxngProvider`: додати `engines: str = ""` у `__init__`, зберегти `self._engines = engines`, і у виклику:

```python
                params = {"q": keyword, "format": "json"}
                if self._engines:
                    params["engines"] = self._engines
                resp = client.get(f"{self._base}/search", params=params)
```

- [ ] **Step 4: Запустити — зелено**

Run: `cd crawler && python -m pytest tests/test_build_provider.py tests/test_search_config.py tests/test_searxng_provider.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/providers.py crawler/crawler/config.py crawler/tests/test_build_provider.py crawler/tests/test_search_config.py crawler/tests/test_searxng_provider.py
git commit -m "feat(crawler): searxng plan + SearchProviderPlan.available + engine selection"
```

---

### Task 7: `SearchPass` — ітерувати всі плани + health-aware `site:`/availability

**Files:**
- Modify: `crawler/crawler/discovery/search_pass.py` (`run`, `provider_for_site_query`, новий `any_provider_available`)
- Test: `crawler/tests/test_search_pass.py`

**Interfaces:**
- Consumes: `SearchProviderPlan.available`, `.succeeded`, `.discovery`, `.include_pins`.
- Produces: `SearchPass.run(known)` виконує ВСІ доступні плани; `provider_for_site_query() -> ActiveDiscovery | None` (перший доступний план); `any_provider_available() -> bool`.

- [ ] **Step 1: Написати падаючі тести**

Додати в `crawler/tests/test_search_pass.py` (подивись наявні хелпери файлу — `FakePlan`/`FakeGrid`/`FakeState` чи подібні — і використай їх; нижче мінімальні фейки, якщо їх нема):

```python
from crawler.discovery.search_pass import SearchPass
from crawler.models import SourceCandidate


class _Grid:
    def __init__(self, phrases): self._p = phrases
    def __len__(self): return len(self._p)
    def at(self, i): return self._p[i % len(self._p)]
    def next_batch(self, bs, cursor): return (self._p[:bs], (cursor + bs) % len(self._p))


class _State:
    def __init__(self): self.grid_cursor = 0
    def unharvested(self, ttl): return []
    def is_fresh(self, kw, ttl): return False
    def set_grid_cursor(self, v): self.grid_cursor = v


class _Disc:
    def __init__(self, cands): self._c = cands
    def run(self, keywords, known): return list(self._c)


def _plan(name, cands, available=True, succeeded=True):
    from crawler.discovery.providers import SearchProviderPlan
    return SearchProviderPlan(name=name, discovery=_Disc(cands), include_pins=False,
                              succeeded=(lambda: succeeded), available=(lambda: available))


def _cand(url):
    return SourceCandidate(name="x", type="website", url_or_handle=url,
                           discovered_from_source_id=None, discovery_note=f"searxng: {url}")


def test_run_iterates_all_available_plans():
    ddg = _plan("duckduckgo", [_cand("https://a.ua/1")], available=False)  # DDG backed off
    sx = _plan("searxng", [_cand("https://b.ua/2")], available=True)
    sp = SearchPass([ddg, sx], _State(), _Grid(["знижка"]), block_size=1, ttl_seconds=0.0)
    out = sp.run(known=set())
    urls = {c.url_or_handle for c in out}
    assert urls == {"https://b.ua/2"}          # only the available (searxng) plan ran
    assert sp.any_provider_available() is True

def test_site_query_provider_prefers_available():
    ddg = _plan("duckduckgo", [], available=False)
    sx = _plan("searxng", [], available=True)
    sp = SearchPass([ddg, sx], _State(), _Grid(["x"]), block_size=1, ttl_seconds=0.0)
    assert sp.provider_for_site_query() is sx.discovery   # DDG down → site: routes via searxng

def test_no_provider_available():
    ddg = _plan("duckduckgo", [], available=False)
    sx = _plan("searxng", [], available=False)
    sp = SearchPass([ddg, sx], _State(), _Grid(["x"]), block_size=1, ttl_seconds=0.0)
    assert sp.any_provider_available() is False
    assert sp.provider_for_site_query() is None
```

- [ ] **Step 2: Запустити — падає**

Run: `cd crawler && python -m pytest tests/test_search_pass.py -k "iterates or site_query_provider or no_provider" -v`
Expected: FAIL (`run` бере лише `plans[0]`; `any_provider_available` нема)

- [ ] **Step 3: Реалізувати**

Замінити `run`, `provider_for_site_query`, додати `any_provider_available`:

```python
    def run(self, known) -> list[SourceCandidate]:
        out: list[SourceCandidate] = []
        size = len(self._grid)
        if size == 0 or not self._plans:
            return out
        # 1) DRAIN once (no re-search): re-surface cached-but-unharvested candidates.
        out.extend(self.drain())
        # 2) Pick the due batch ONCE; every available provider searches the same phrases
        #    (cross-provider redundancy raises recall).
        cursor = self._state.grid_cursor
        if self._ttl > 0:
            batch, new_cursor = self._collect_due(cursor, size)
        else:
            batch, new_cursor = self._grid.next_batch(self._bs, cursor)
        any_success = False
        for plan in self._plans:
            if not plan.available():
                continue
            pins = self._pins if plan.include_pins else []
            keywords = merge_queries(batch, pins)
            searched = plan.discovery.run(keywords, known)
            for c in searched:
                if c.origin_key is None and c.discovery_note and ": " in c.discovery_note:
                    c.origin_key = c.discovery_note.split(": ", 1)[1]
            out.extend(searched)
            if plan.succeeded():
                any_success = True
        # advance the cursor only if at least one provider covered this batch
        if any_success:
            self._state.set_grid_cursor(new_cursor)
        return out

    def any_provider_available(self) -> bool:
        return any(p.available() for p in self._plans)

    def provider_for_site_query(self):
        """ActiveDiscovery of the first currently-available provider (health-aware), or None.
        Under DDG backoff this returns the SearXNG discovery so the site: leg still runs."""
        for plan in self._plans:
            if plan.available():
                return plan.discovery
        return None
```

- [ ] **Step 4: Запустити — зелено**

Run: `cd crawler && python -m pytest tests/test_search_pass.py -v`
Expected: PASS (нові + наявні; за одного доступного плану поведінка = поточна)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/search_pass.py crawler/tests/test_search_pass.py
git commit -m "feat(crawler): SearchPass runs all available providers; health-aware site: routing"
```

---

### Task 8: `run_active` бере site:-провайдер динамічно + `scheduler.step` за будь-яким живим провайдером

**Files:**
- Modify: `crawler/crawler/runner.py:143-156` (site: leg gate)
- Modify: `crawler/crawler/scheduler.py` (`step`, `run_loop`)
- Modify: `crawler/crawler/__main__.py` (прокинути `search_available`)
- Test: `crawler/tests/test_scheduler.py`

**Interfaces:**
- Consumes: `SearchPass.any_provider_available()`, `SearchPass.provider_for_site_query()`.
- Produces: `scheduler.step(runner, state, passive_schedule, *, active_delay, backoff_max_sleep, hard_factor, search_available=None)`; `run_loop(..., search_available=None)`.

- [ ] **Step 1: Написати падаючі тести**

Додати в `crawler/tests/test_scheduler.py` (перевір наявні фейки `runner`/`state` у файлі й використай їх; нижче — самодостатні):

```python
from crawler.scheduler import step


class _Runner:
    def __init__(self): self.active = []; self.passive = 0
    def run_active(self, ddg_allowed=True): self.active.append(ddg_allowed)
    def run_passive(self): self.passive += 1


class _State:
    def __init__(self, backoff, secs=120.0): self._b = backoff; self._s = secs
    def in_global_backoff(self): return self._b
    def seconds_until_allowed(self): return self._s


def test_step_full_pass_when_any_provider_available():
    r = _Runner()
    # DDG in global backoff, but search_available() True (searxng alive)
    secs = step(r, _State(backoff=True), None, active_delay=60, backoff_max_sleep=1800,
                hard_factor=3, search_available=lambda: True)
    assert r.active == [True]           # full active pass, NOT degraded
    assert secs == 60                    # short sleep, not long backoff sleep

def test_step_degraded_when_no_provider_available():
    r = _Runner()
    secs = step(r, _State(backoff=True, secs=200.0), None, active_delay=60,
                backoff_max_sleep=1800, hard_factor=3, search_available=lambda: False)
    assert r.active == [False]          # degraded (drain-only) pass
    assert secs == 200.0                 # sleep until soonest recovery

def test_step_backcompat_without_search_available():
    r = _Runner()
    # no search_available → falls back to state.in_global_backoff() (existing behavior)
    step(r, _State(backoff=True, secs=200.0), None, active_delay=60,
         backoff_max_sleep=1800, hard_factor=3)
    assert r.active == [False]
```

- [ ] **Step 2: Запустити — падає**

Run: `cd crawler && python -m pytest tests/test_scheduler.py -k "any_provider or no_provider or backcompat" -v`
Expected: FAIL (`step() got an unexpected keyword argument 'search_available'`)

- [ ] **Step 3: Реалізувати**

`scheduler.py` — замінити `step` (додати параметр і обчислення `backed_off`), і прокинути через `run_loop`:

```python
def step(runner, state, passive_schedule, *, active_delay, backoff_max_sleep, hard_factor,
         search_available=None):
    """One scheduling decision. `search_available()` (any provider healthy) decides degraded
    vs full pass; without it, falls back to DDG-only state.in_global_backoff() (back-compat)."""
    if search_available is not None:
        backed_off = not search_available()
    else:
        backed_off = state is not None and state.in_global_backoff()
    if state is not None and backed_off:
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

У `run_loop` — прийняти й передати `search_available`:

```python
def run_loop(runner, state_loader, passive_schedule, *, active_delay, backoff_max_sleep,
             hard_factor, sleep=time.sleep, iterations=None,
             learn=None, learn_interval_seconds=0, now=time.monotonic,
             search_available=None):
    ...
        try:
            state = state_loader()
            secs = step(runner, state, passive_schedule, active_delay=active_delay,
                        backoff_max_sleep=backoff_max_sleep, hard_factor=hard_factor,
                        search_available=search_available)
```

`runner.py` — у `run_active`, site: leg: замість статичного `self._discovery` брати живий провайдер від `SearchPass`. Замінити рядок-умову (`runner.py:143`) і додати обчислення `site_discovery` перед нею:

```python
            # site: routes through whichever provider is currently healthy (DDG or SearXNG),
            # so the site: leg survives DDG backoff too.
            site_discovery = (self._search_pass.provider_for_site_query()
                              if self._search_pass is not None else self._discovery)
            if (ddg_allowed and self._site_planner is not None and self._site_state is not None
                    and site_discovery is not None and self._domain_registry is not None):
                cur = self._site_state.site_cursor
                reg = [h for h in self._domain_registry.top(
                           self._site_query_budget, known_hosts, self._revisit_cooldown)
                       if not is_blocked_host(h)]
                site_queries, new_cur = self._site_planner.next_batch(
                    reg, self._site_query_budget, cur)
                if site_queries:
                    site_cands = site_discovery.run(site_queries, known)
                    for c in site_cands:
                        c.bypass_host_skip = True
                    candidates += site_cands
                    self._site_state.set_site_cursor(new_cur)
```

(Замінено `self._discovery` → `site_discovery` у двох місцях: умові й `.run`.)

`__main__.py` — у гілці `loop`, після побудови `runner`, дістати `search_pass` з runner і прокинути предикат. Runner уже тримає `self._search_pass`; додати у `Runner` властивість-геттер, якщо приватне. Найпростіше — додати у `Runner` метод:

```python
    def search_available(self) -> bool:
        return self._search_pass.any_provider_available() if self._search_pass is not None else True
```

(додати в `runner.py`), і в `__main__.py`:

```python
        run_loop(runner, _load_state, passive,
                 active_delay=config.active_loop_delay_seconds,
                 backoff_max_sleep=config.backoff_max_sleep_seconds,
                 hard_factor=config.passive_hard_overdue_factor,
                 learn=_learn, learn_interval_seconds=config.learn_interval_seconds,
                 search_available=runner.search_available)
```

- [ ] **Step 4: Запустити — зелено**

Run: `cd crawler && python -m pytest tests/test_scheduler.py -v`
Expected: PASS (нові + наявні; наявні не передають `search_available` → back-compat гілка)

- [ ] **Step 5: Прогнати ВЕСЬ сют**

Run: `cd crawler && python -m pytest -q`
Expected: PASS (усі; якщо якийсь наявний тест конструює `SearchProviderPlan` без `available` — додати `available=lambda: True`; якщо тест `SearchPass`/`run_active` покладався на `plans[0]`-семантику — оновити під ітерацію всіх планів)

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/runner.py crawler/crawler/scheduler.py crawler/crawler/__main__.py crawler/tests/test_scheduler.py
git commit -m "feat(crawler): active pass + site: survive DDG backoff via any live provider"
```

---

### Task 9: Docker-сервіс SearXNG + налаштування + env + docs

**Files:**
- Create: `docker/searxng/settings.yml`
- Modify: `docker-compose.yml`
- Modify: `crawler/README.md` (короткий блок env)
- Test: ручний smoke (нижче)

**Interfaces:**
- Produces: сервіс `searxng` у Compose, доступний краулеру за `http://searxng:8080`; env `SEARXNG_URL`, `SEARCH_PROVIDERS`.

- [ ] **Step 1: Створити `docker/searxng/settings.yml`**

```yaml
# SearXNG — self-hosted metasearch for crawler discovery. JSON API on; only engines that
# work from our single residential IP (NO google/bing → CAPTCHA; NO yandex → project rule).
use_default_settings: true
server:
  secret_key: "change-me-searxng-secret"   # override in prod via env SEARXNG_SECRET
  bind_address: "0.0.0.0"
  port: 8080
search:
  formats:
    - html
    - json
  autocomplete: ""
  default_lang: "uk"
engines:
  - name: google
    disabled: true
  - name: bing
    disabled: true
  - name: yandex
    disabled: true
```

(SearXNG вмикає duckduckgo/brave/mojeek/qwant/marginalia/wikidata з дефолтів; ми лише глушимо заборонені. Наш `searxng_engines` у запиті додатково звужує per-query.)

- [ ] **Step 2: Додати сервіс у `docker-compose.yml`**

Під `services:` (поряд із `crawler`):

```yaml
  searxng:
    image: searxng/searxng:latest
    profiles: ["crawler"]
    restart: unless-stopped
    environment:
      SEARXNG_BASE_URL: http://searxng:8080/
      SEARXNG_SECRET: ${SEARXNG_SECRET:-change-me-searxng-secret}
    volumes:
      - ./docker/searxng/settings.yml:/etc/searxng/settings.yml:ro
```

У сервісі `crawler`, `depends_on:` — додати:

```yaml
      searxng:
        condition: service_started
```

У `crawler` `environment:` — додати:

```yaml
      SEARXNG_URL: http://searxng:8080
      SEARCH_PROVIDERS: ${SEARCH_PROVIDERS:-duckduckgo,searxng}
```

- [ ] **Step 3: Smoke — підняти й перевірити JSON API**

```bash
docker compose --profile crawler up -d searxng
sleep 15
docker compose exec crawler python -c "import httpx; r=httpx.get('http://searxng:8080/search', params={'q':'знижки військовим','format':'json'}, timeout=30); print(r.status_code, len(r.json().get('results', [])))"
```

Expected: `200 <N>` де N > 0 (є результати). Якщо `403`/`429` — перевірити, що google/bing вимкнені й що `format: json` увімкнено в settings.

- [ ] **Step 4: Перевірити краулер бачить провайдера**

```bash
docker compose exec crawler python -c "from crawler.config import load_config; from crawler.discovery.providers import build_search_plans; c=load_config(); print([p.name for p in build_search_plans(c)])"
```

Expected: `['duckduckgo', 'searxng']`

- [ ] **Step 5: Оновити `crawler/README.md`**

Додати блок:

```markdown
### SearXNG (незалежний search-провайдер)
Краулер використовує self-hosted SearXNG як другий, DDG-незалежний канал discovery.
- `SEARCH_PROVIDERS=duckduckgo,searxng` (дефолт)
- `SEARXNG_URL=http://searxng:8080`
- `SEARXNG_ENGINES` — звуження рушіїв per-query (дефолт: duckduckgo,brave,mojeek,qwant,marginalia,wikidata; БЕЗ google/bing/yandex)
- Сервіс `searxng` піднімається профілем `crawler`. Налаштування — `docker/searxng/settings.yml`.
```

- [ ] **Step 6: Commit**

```bash
git add docker/searxng/settings.yml docker-compose.yml crawler/README.md
git commit -m "feat(infra): self-hosted SearXNG service for DDG-independent discovery"
```

---

## Self-Review notes (для виконавця)

- **Спек-покриття:** Фаза1→Tasks 1-2; Фаза2→Task 3 (+ динамічний backoff уже в Task 2); Фаза3→Task 4; Фаза4→Tasks 5-9. `site:`-через-живий-провайдер→Task 8. Дослідження провайдерів (лише SearXNG, широкі рушії)→Tasks 6,9.
- **Back-compat пильнувати:** будь-який наявний тест, що конструює `SearchProviderPlan(...)` — тепер потребує `available=`. Прогнати `python -m pytest -q` наприкінці Task 8 і полагодити такі місця.
- **Порядок мерджу:** фази незалежно-мерджабельні; кожна лишає сют зеленим. Мерджити у `main` через гілку треку `track/crawler-backoff-resilience` (спек уже там).
- **Деплой (після мерджу):** ребілд контейнерів crawler; підняти `searxng`; переконатися, що том стану `/data` не втратив карантин-міграцію (нові ключі додаються ліниво).
```
