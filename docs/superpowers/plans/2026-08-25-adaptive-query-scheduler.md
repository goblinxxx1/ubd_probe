# Adaptive Query Scheduler (MAB-lite + Chao1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two linked parts. **Part A (query scheduling — a BIDIRECTIONAL, REVERSIBLE self-balancing loop):** the active-search grid must both *shrink* (auto-retire chronically-dry phrases) AND *grow* (auto-add fruitful new phrases), driven by one shared reward, with retirement fully reversible — a suppressed phrase auto-resurrects the moment it yields again. This removes the human from the loop (no more hand-pruning like поліція/ДСНС/НГУ, and no hand-adding either). A capture-recapture (Chao1) gauge measures how much of the discoverable-domain universe is covered. **Part B (fetch cost & politeness):** cut the cost of each fetch the freed budget then spends — conditional GET (304), adaptive 429/`Retry-After` host backoff, `<link rel=canonical>` dedup, and a real UA contact.

**Architecture:** *Part A* reuses the reward signal already computed in `search_pass.py` (`new_by_phrase`). **Retire half (new):** persist per-phrase productivity in `SearchState`; derive an *adaptive freshness TTL* so chronically-dry phrases are revisited exponentially less often (never fully retired — reprobe floor), while young phrases always get base TTL (exploration). Because a reprobe that yields resets the EWMA → TTL drops back to base, **retirement is self-reversing = a form of automatic re-add**. **Add half (reward-linked to the EXISTING self-learning tick):** `runner.learn_and_reload_grid()` already mines the corpus periodically and hot-reloads new service terms into the grid without a restart; Task 5B feeds it a *reward-prioritized* stream — productive cells breed net-new phrases from their own winning results (Ntoulas "acquired terms"), so growth concentrates where offers actually are. The two halves share `new_by_phrase`; together the grid self-balances up and down. A pure Chao1 module estimates coverage, logged as a saturation gauge. *Part B* extends `DomainRateLimiter` with a per-host penalty (honoring `Retry-After`), teaches `WebsiteFetcher` conditional GET via an injected validator store (304 ⇒ cheap), and reads the page-declared canonical URL for dedup. Everything layers onto existing patterns — no new heavy dependencies.

**Tech Stack:** Python 3.12, existing crawler package (`crawler/discovery/*`, `crawler/fetchers/*`, `crawler/ratelimit.py`), httpx, selectolax, pytest, JSON-file persistence.

**Ordering:** Part A first (Tasks 1-8) — it is the primary lever and ships independently. Part B second (Tasks 9-12) — each Part B task also ships independently; they amplify Part A but do not depend on it. A reviewer can accept/reject any single task.

## Global Constraints

- **АВТОНОМНІСТЬ (інваріант проєкту):** усе працює АВТОМАТИЧНО, БЕЗКОШТОВНО і БЕЗ участі людини/агента.
  - *Автоматично й ДВОНАПРАВЛЕНО:* уся нова логіка живе в наявному циклі (`crawler loop` / scheduler), без ручного тригера. Планувальник САМ **прибирає** сухі фрази (adaptive TTL backoff) І САМ **додає** нові з врожайних (reward-linked breeding у наявний self-learning тік `learn_and_reload_grid`, hot-reload без рестарту). Обидва напрями від ОДНОГО reward (`new_by_phrase`). Ретайр РЕВЕРСИВНИЙ: reprobe, що дав улов → EWMA скидає TTL на базу = авто-повернення фрази. Ніякого ручного видалення (як поліція/ДСНС/НГУ) чи ручного додавання.
  - *Безкоштовно:* ЖОДНИХ платних сервісів — ні хмарних LLM, ні платних search/geo API. Лише вільні провайдери (DDG/SearXNG), локальні евристики та локальний $0-суддя (Qwen). Будь-який новий компонент — чистий Python або локальний.
  - *Без участі:* жодного кроку, що потребує людини в рантаймі. Успіх — САМОзвітний через логи/метрики (Task 7 gauge + Task 8 self-logged productivity), не ручний аналіз. Reprobe-floor гарантує, що НІЩО не треба додавати назад руками.
- **ЛЮДСЬКИЙ OVERRIDE СПІВІСНУЄ (запобіжник для корекції, коли автопетля помиляється):** адмінка лишається простором для РУЧНОГО add/remove термінів, і ручне рішення МАЄ ПРІОРИТЕТ над автоматикою. Це страховка на випадок, коли щось піде не так (авто-loop почав додавати шум або душити корисне). Конкретно: (1) авто-breeding НЕ додає термін, який адмін відхилив (reuse наявного `/query-terms/rejected` hard-exclude); (2) термін, доданий/схвалений адміном, ПОЗНАЧЕНИЙ `protected` → авто-ретайр його НЕ душить (завжди базовий TTL); (3) наявний admin query-terms UI (approve/reject/unreject) розширюється прапорцем `protected`/manual та ручним додаванням. Автопетля й людина працюють паралельно; конфлікт вирішується на користь людини.
- Українська мова в усіх коментарях/логах/докстрингах нового коду (це домовленість проєкту). Жодної російської.
- Test runner: `./.venv/Scripts/python.exe -m pytest -q` from `crawler/` (Windows venv per project convention).
- No new third-party dependencies. Pure-Python only.
- `SearchState` mutations must stay atomic (`_save()` writes `.tmp` then `os.replace`). Do not break that.
- Backward compatible on-disk state: a missing key must default (mirror existing `_EMPTY.setdefault` pattern in `SearchState.load`). Old `search_state.json` files must load without error.
- Deterministic scheduling: no wall-clock or RNG inside the ordering logic except through the injectable `clock` already on `SearchState`. Exploration is deterministic (tries-count based), not random, to keep `test_grid_order_is_stable`-style guarantees intact.
- Do NOT change the query-grid contents or size (1662) — this plan changes *scheduling over* the grid, not the grid itself.

---

## File Structure

- **Create** `crawler/crawler/discovery/coverage.py` — pure Chao1 capture-recapture functions (`chao1`, `saturation`). No I/O. One responsibility: coverage math.
- **Create** `crawler/tests/test_coverage.py` — unit tests for the math.
- **Modify** `crawler/crawler/discovery/search_state.py` — add `phrase_stats` + `host_freq` persistence, `record_yield`, `effective_ttl`, `coverage_counts`. This is where per-phrase productivity and global recapture frequencies live.
- **Modify** `crawler/tests/test_search_state.py` (create if absent) — unit tests for the new state methods.
- **Modify** `crawler/crawler/discovery/search_pass.py` — call `record_yield`, feed `host_freq`, use `effective_ttl` in `_collect_due` (retire half), AND route winning terms from high-yield phrases to a `breed_sink` (add half).
- **Modify** `crawler/crawler/learn/` candidate pool + `crawler/crawler/runner.py` `learn_and_reload_grid` — accept the reward-prioritized bred terms so net-new growth concentrates on proven-fruitful phrases (the existing miner tick is kept; it gains a reward-weighted input).
- **Modify** `crawler/tests/test_search_pass.py` (create if absent) — behavioral tests that a dry phrase is skipped and a productive one is revisited.
- **Modify** `crawler/crawler/config.py` — add three tunables (`phrase_cold_tries`, `phrase_ttl_mult_cap`, `phrase_ewma_alpha`) following the existing dataclass→settings→mapping triple.
- **Modify** `crawler/crawler/runner.py` — log the saturation gauge once per active cycle (observability + optional cadence stretch). Read-only w.r.t. scheduling; a single log line + optional flag.

**Part B (fetch cost & politeness):**
- **Modify** `crawler/crawler/ratelimit.py` — add `DomainRateLimiter.penalize(domain, seconds)` + honor it in `wait()`. One responsibility: per-host pacing, now with a 429 penalty.
- **Modify** `crawler/tests/test_ratelimit.py` (create if absent) — penalty timing tests with fake clock/sleep.
- **Modify** `crawler/crawler/models.py` — add `RawItem.canonical_url: str | None = None`.
- **Modify** `crawler/crawler/fetchers/website.py` — read `<link rel=canonical>`; conditional GET via an injected validator store; surface 429/`Retry-After` to a throttle sink.
- **Create** `crawler/crawler/discovery/validator_store.py` — tiny JSON `url -> {etag, last_modified}` store for conditional GET.
- **Modify** `crawler/tests/test_website_fetcher.py` (create if absent) — canonical extraction, 304 short-circuit, 429 penalty.
- **Modify** `crawler/crawler/discovery/harvest.py` — wire the throttle sink to `DomainRateLimiter.penalize` around `fetcher.fetch`.
- **Modify** `crawler/crawler/wiring.py` — inject the validator store + real UA contact into the website client/fetcher.

---

## Task 1: Chao1 coverage math (pure module)

**Files:**
- Create: `crawler/crawler/discovery/coverage.py`
- Test: `crawler/tests/test_coverage.py`

**Interfaces:**
- Produces:
  - `chao1(observed: int, f1: int, f2: int) -> float` — estimated lower bound of the total distinct-domain universe.
  - `saturation(observed: int, f1: int, f2: int) -> float` — `observed / chao1(...)`, clamped to `[0.0, 1.0]`.

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_coverage.py
import math
from crawler.discovery.coverage import chao1, saturation


def test_chao1_classic_formula_with_doubletons():
    # observed=10, f1=4 singletons, f2=2 doubletons -> 10 + 16/4 = 14
    assert chao1(10, 4, 2) == 14.0


def test_chao1_bias_corrected_when_no_doubletons():
    # f2==0 -> observed + f1*(f1-1)/2 = 5 + 3*2/2 = 8
    assert chao1(5, 3, 0) == 8.0


def test_chao1_fully_saturated_when_no_singletons():
    # no singletons -> estimate equals observed (nothing new expected)
    assert chao1(10, 0, 0) == 10.0


def test_chao1_zero_observed_is_zero():
    assert chao1(0, 0, 0) == 0.0


def test_saturation_is_ratio_clamped():
    assert math.isclose(saturation(10, 4, 2), 10 / 14)
    assert saturation(10, 0, 0) == 1.0     # nothing left to find
    assert saturation(0, 0, 0) == 1.0      # empty corpus -> treat as saturated
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_coverage.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'crawler.discovery.coverage'`

- [ ] **Step 3: Write minimal implementation**

```python
# crawler/crawler/discovery/coverage.py
"""Capture-recapture (Chao1) coverage estimation for discovery saturation.

Pure functions, no I/O. Chao1 lower-bounds the total number of *discoverable*
domains from the frequency of singletons (домен побачений рівно 1 раз) and
doubletons (рівно 2 рази). Ідея з екології (оцінка чисельності виду), адаптована
для оцінки, скільки бізнес-доменів ще лишилось знайти пошуком.

ЗАСТЕРЕЖЕННЯ (best-practice): Chao1 — НИЖНЯ МЕЖА і припускає ВИПАДКОВИЙ семплінг.
Наш пошук ТАРГЕТОВАНИЙ (грід), тож абсолютне число зсунуте — використовувати ЛИШЕ
як DIRECTIONAL gauge (тренд сатурації в часі), НЕ гейтити тверді рішення на його
абсолютному значенні. При f2==0 і малому f1 оцінка нестабільна (bias-corrected форма
пом'якшує, не усуває)."""


def chao1(observed: int, f1: int, f2: int) -> float:
    """Оцінка-нижня-межа загальної кількості різних доменів.

    observed = скільки різних доменів уже бачили; f1 = бачені рівно раз;
    f2 = бачені рівно двічі. При f2==0 — bias-corrected форма."""
    if observed <= 0:
        return 0.0
    if f2 > 0:
        return observed + (f1 * f1) / (2.0 * f2)
    return observed + (f1 * (f1 - 1)) / 2.0


def saturation(observed: int, f1: int, f2: int) -> float:
    """Частка вже відкритого домен-всесвіту в [0,1]. 1.0 = нема чого шукати."""
    est = chao1(observed, f1, f2)
    if est <= 0:
        return 1.0
    return min(1.0, observed / est)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_coverage.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/coverage.py crawler/tests/test_coverage.py
git commit -m "feat(crawler): Chao1 capture-recapture coverage math (pure module)"
```

---

## Task 2: Per-phrase productivity in SearchState (`record_yield`)

**Files:**
- Modify: `crawler/crawler/discovery/search_state.py` (add `phrase_stats` to `_EMPTY` at line 11-13; add method near the existing `record_page_result`, ~line 166)
- Test: `crawler/tests/test_search_state.py`

**Interfaces:**
- Consumes: existing `SearchState._key(phrase)` (line 245), existing `_save()`.
- Produces: `SearchState.record_yield(phrase: str, new_count: int, alpha: float = 0.3) -> None` — updates `phrase_stats[key] = {"tries": int, "ewma": float, "dry_streak": int}`.

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_search_state.py
from crawler.discovery.search_state import SearchState


def _state(tmp_path):
    return SearchState(str(tmp_path / "state.json"), clock=lambda: 1000.0)


def test_record_yield_tracks_tries_ewma_and_dry_streak(tmp_path):
    s = _state(tmp_path)
    s.record_yield("знижка військові", 4, alpha=0.5)
    e = s._data["phrase_stats"][s._key("знижка військові")]
    assert e["tries"] == 1
    assert e["ewma"] == 2.0            # 0.5*0 + 0.5*4
    assert e["dry_streak"] == 0

    s.record_yield("знижка військові", 0, alpha=0.5)
    e = s._data["phrase_stats"][s._key("знижка військові")]
    assert e["tries"] == 2
    assert e["ewma"] == 1.0            # 0.5*2 + 0.5*0
    assert e["dry_streak"] == 1        # a dry pass increments the streak


def test_record_yield_survives_reload(tmp_path):
    p = str(tmp_path / "state.json")
    SearchState(p, clock=lambda: 1.0).record_yield("акція ЗСУ", 3)
    reloaded = SearchState.load(p, clock=lambda: 2.0)
    assert reloaded._data["phrase_stats"][reloaded._key("акція ЗСУ")]["tries"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_search_state.py -q`
Expected: FAIL — `KeyError: 'phrase_stats'` (method/field absent)

- [ ] **Step 3: Write minimal implementation**

In `search_state.py`, extend `_EMPTY` (line 11-13) to include the new maps:

```python
_EMPTY = {"version": 1, "cursor": 0, "grid_cursor": 0, "site_cursor": 0,
          "approved_cursor": 0,
          "next_allowed_at": 0.0, "backends": {}, "cache": {}, "phrase_pages": {},
          "phrase_stats": {}, "host_freq": {}}
```

Add the method immediately after `record_page_result` (after line 184):

```python
    # --- per-phrase productivity (adaptive scheduling) ---
    def record_yield(self, phrase: str, new_count: int, alpha: float = 0.3) -> None:
        """EWMA урожайності фрази + лічильник спроб + серія «сухих» проходів.
        Продуктивність (new_count) уже known-filtered у SearchPass → це маргінальні
        НОВІ кандидати. Живить effective_ttl (рідше вертатись до сухих фраз)."""
        stats = self._data.setdefault("phrase_stats", {})
        k = self._key(phrase)
        e = stats.get(k) or {"tries": 0, "ewma": 0.0, "dry_streak": 0}
        e["tries"] = int(e.get("tries", 0)) + 1
        prev = float(e.get("ewma", 0.0))
        e["ewma"] = (1.0 - alpha) * prev + alpha * float(new_count)
        e["dry_streak"] = 0 if new_count > 0 else int(e.get("dry_streak", 0)) + 1
        stats[k] = e
        self._save()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_search_state.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/search_state.py crawler/tests/test_search_state.py
git commit -m "feat(crawler): per-phrase EWMA productivity in SearchState.record_yield"
```

---

## Task 3: Adaptive freshness TTL (`effective_ttl`)

**Files:**
- Modify: `crawler/crawler/discovery/search_state.py` (add method after `record_yield`)
- Test: `crawler/tests/test_search_state.py` (append)

**Interfaces:**
- Consumes: `phrase_stats` written by Task 2; `SearchState._key`.
- Produces: `SearchState.effective_ttl(phrase: str, base_ttl: float, *, cold_tries: int = 3, mult_cap: float = 8.0) -> float`.

Behaviour: young phrase (`tries < cold_tries`) → `base_ttl` (explore). Productive (`ewma > 0`) → `base_ttl`. Warm-but-dry → `base_ttl * min(mult_cap, 2**(dry_streak - cold_tries + 1))` (exponential backoff, capped = reprobe floor).

- [ ] **Step 1: Write the failing test**

```python
# append to crawler/tests/test_search_state.py
def test_effective_ttl_explores_young_phrases(tmp_path):
    s = _state(tmp_path)
    s.record_yield("рідкісна фраза", 0)          # tries=1 < cold_tries
    assert s.effective_ttl("рідкісна фраза", 100.0, cold_tries=3) == 100.0


def test_effective_ttl_keeps_base_for_productive(tmp_path):
    s = _state(tmp_path)
    for _ in range(5):
        s.record_yield("врожайна", 3)            # ewma stays > 0
    assert s.effective_ttl("врожайна", 100.0, cold_tries=3) == 100.0


def test_effective_ttl_backs_off_warm_dry_phrase_capped(tmp_path):
    s = _state(tmp_path)
    for _ in range(10):
        s.record_yield("суха фраза", 0)          # tries=10, ewma=0, dry_streak=10
    ttl = s.effective_ttl("суха фраза", 100.0, cold_tries=3, mult_cap=8.0)
    assert ttl == 800.0                          # capped at base * mult_cap


def test_effective_ttl_unknown_phrase_is_base(tmp_path):
    s = _state(tmp_path)
    assert s.effective_ttl("невидана", 100.0) == 100.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_search_state.py -q`
Expected: FAIL — `AttributeError: 'SearchState' object has no attribute 'effective_ttl'`

- [ ] **Step 3: Write minimal implementation**

Add after `record_yield` in `search_state.py`:

```python
    def effective_ttl(self, phrase: str, base_ttl: float, *,
                      cold_tries: int = 3, mult_cap: float = 8.0) -> float:
        """Адаптивний freshness-TTL. Молоду фразу (tries<cold_tries) НІКОЛИ не
        душимо (exploration). Продуктивну (ewma>0) вертаємо на базовій каденції.
        Теплу-але-суху — експоненційно рідше (backoff, capped = reprobe-floor),
        той самий патерн, що quarantine/reprobe для бекендів."""
        e = self._data.get("phrase_stats", {}).get(self._key(phrase))
        if not e or int(e.get("tries", 0)) < cold_tries:
            return base_ttl
        if float(e.get("ewma", 0.0)) > 0.0:
            return base_ttl
        dry = int(e.get("dry_streak", 0))
        mult = min(mult_cap, 2.0 ** max(0, dry - cold_tries + 1))
        return base_ttl * mult
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_search_state.py -q`
Expected: PASS (6 passed total in file)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/search_state.py crawler/tests/test_search_state.py
git commit -m "feat(crawler): adaptive per-phrase freshness TTL (dry-phrase backoff)"
```

---

## Task 4: Global recapture frequencies (`host_freq` + `coverage_counts`)

**Files:**
- Modify: `crawler/crawler/discovery/search_state.py` (add `note_host` + `coverage_counts`)
- Test: `crawler/tests/test_search_state.py` (append)

**Interfaces:**
- Consumes: `host_freq` map added to `_EMPTY` in Task 2.
- Produces:
  - `SearchState.note_host(host: str) -> None` — increment sighting frequency for a discovered host.
  - `SearchState.coverage_counts() -> tuple[int, int, int]` — `(observed, f1, f2)` for `coverage.chao1`.

- [ ] **Step 1: Write the failing test**

```python
# append to crawler/tests/test_search_state.py
def test_host_freq_and_coverage_counts(tmp_path):
    s = _state(tmp_path)
    for h in ["a.ua", "a.ua", "a.ua", "b.ua", "b.ua", "c.ua", "d.ua"]:
        s.note_host(h)
    # a=3 (neither), b=2 (doubleton), c=1, d=1 (singletons)
    observed, f1, f2 = s.coverage_counts()
    assert observed == 4
    assert f1 == 2            # c, d
    assert f2 == 1            # b


def test_note_host_ignores_empty(tmp_path):
    s = _state(tmp_path)
    s.note_host("")
    s.note_host(None)         # type: ignore[arg-type]
    assert s.coverage_counts() == (0, 0, 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_search_state.py -q`
Expected: FAIL — `AttributeError: 'SearchState' object has no attribute 'note_host'`

- [ ] **Step 3: Write minimal implementation**

Add after `effective_ttl` in `search_state.py`:

```python
    # --- global capture-recapture frequencies (coverage gauge) ---
    def note_host(self, host: str | None) -> None:
        """Зарахувати ще одне «спостереження» домену (для Chao1). Частота, не факт
        наявності — тому інкремент щоразу, коли пошук виносить цей хост."""
        if not host:
            return
        freq = self._data.setdefault("host_freq", {})
        freq[host] = int(freq.get(host, 0)) + 1
        self._save()

    def coverage_counts(self) -> tuple[int, int, int]:
        """(observed, f1, f2): різних доменів, singletons (=1), doubletons (=2)."""
        freq = self._data.get("host_freq", {})
        observed = len(freq)
        f1 = sum(1 for v in freq.values() if int(v) == 1)
        f2 = sum(1 for v in freq.values() if int(v) == 2)
        return observed, f1, f2
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_search_state.py -q`
Expected: PASS (8 passed total in file)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/search_state.py crawler/tests/test_search_state.py
git commit -m "feat(crawler): global host recapture frequencies + coverage_counts"
```

---

## Task 5: Wire SearchPass to record yield, note hosts, and use adaptive TTL

**Files:**
- Modify: `crawler/crawler/discovery/search_pass.py` (`run` ~line 82-85; `_collect_due` ~line 88-100)
- Test: `crawler/tests/test_search_pass.py`

**Interfaces:**
- Consumes: `SearchState.record_yield`, `SearchState.effective_ttl`, `SearchState.note_host` (Tasks 2-4); existing `bare_host` from `crawler.util.hosts`.
- Produces: no new public interface; behaviour change — dry phrases skipped by the due-walk sooner, productive phrases revisited at base cadence, `host_freq` populated.

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_search_pass.py
from crawler.discovery.search_pass import SearchPass
from crawler.discovery.search_state import SearchState
from crawler.discovery.query_grid import QueryGrid


class _Plan:
    include_pins = False
    def __init__(self, results_by_kw):
        self._by = results_by_kw
        self._ok = True
    def available(self):
        return True
    def succeeded(self):
        return self._ok
    class _Disc:
        pass
    @property
    def discovery(self):
        d = _Plan._Disc()
        d.run = self._run
        return d
    def _run(self, keywords, known, pages):
        # return the canned candidates whose phrase is in this batch
        out = []
        for kw in keywords:
            for c in self._by.get(kw, []):
                c.discovery_note = f"ddg: {kw}"
                out.append(c)
        return out


def _cand(name, url):
    from crawler.models import SourceCandidate
    return SourceCandidate(name=name, type="website", url_or_handle=url,
                           discovered_from_source_id=None)


def test_dry_phrase_gets_longer_effective_ttl_and_is_skipped(tmp_path):
    # grid of two phrases; phrase A always dry, phrase B productive.
    grid = QueryGrid(["A", "B"])
    clock = [0.0]
    state = SearchState(str(tmp_path / "s.json"), clock=lambda: clock[0])
    plan = _Plan({"B": [_cand("shopB", "https://b.ua")]})   # A yields nothing
    sp = SearchPass([plan], state, grid, block_size=2, ttl_seconds=100.0,
                    page_cap=1)
    # run several passes; advance clock a little each time (< base ttl)
    for _ in range(6):
        clock[0] += 10.0
        sp.run(known=set())
    # A drifted to a longer effective TTL (dry backoff); B stays base.
    assert state.effective_ttl("A", 100.0, cold_tries=3) > 100.0
    assert state.effective_ttl("B", 100.0, cold_tries=3) == 100.0
    # host_freq recorded B's domain at least once
    assert "b.ua" in state._data["host_freq"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_search_pass.py -q`
Expected: FAIL — `A`'s effective TTL stays 100.0 (record_yield/effective_ttl not wired) or host_freq empty.

- [ ] **Step 3: Write minimal implementation**

In `search_pass.py`, add the import at top:

```python
from crawler.util.hosts import bare_host
```

In `run`, replace the success-advance block (current lines 81-86) with yield + host recording:

```python
        # advance the grid cursor AND each phrase's page cursor only on a covered batch
        if any_success:
            for p in batch:
                self._state.record_page_result(p, pages[p], new_by_phrase[p], self._page_cap)
                self._state.record_yield(p, new_by_phrase[p])          # NEW: productivity
            for c in out:                                              # NEW: recapture freq
                self._state.note_host(bare_host(c.url_or_handle))
            self._state.set_grid_cursor(new_cursor)
```

In `_collect_due`, use the adaptive TTL per phrase (current line 96):

```python
    def _collect_due(self, cursor, size):
        """Scan forward from cursor collecting up to block_size due phrases; a phrase is
        due when its CURRENT SERP page is not cache-fresh UNDER ITS ADAPTIVE TTL. Dry
        phrases carry a longer effective TTL, so the walk self-concentrates on productive
        ones. next_cursor is past every phrase scanned (fresh skipped included), wrapping."""
        batch: list[str] = []
        scanned = 0
        while scanned < size and len(batch) < self._bs:
            kw = self._grid.at(cursor)
            ttl = self._state.effective_ttl(kw, self._ttl)
            if not self._state.is_fresh(kw, ttl, self._state.current_page(kw)):
                batch.append(kw)
            cursor = (cursor + 1) % size
            scanned += 1
        return batch, cursor
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_search_pass.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Run the full crawler suite (no regressions)**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS (all green; prior 888 + the new tests)

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/discovery/search_pass.py crawler/tests/test_search_pass.py
git commit -m "feat(crawler): adaptive due-walk — yield-weighted TTL + recapture host notes"
```

---

## Task 5B: Reward-driven breeding (the ADD half) — respecting admin rejects

**Files:**
- Modify: `crawler/crawler/discovery/search_pass.py` (`__init__`, `run`)
- Modify: `crawler/crawler/runner.py` `learn_and_reload_grid` / wiring — supply the `breed_sink`
- Test: `crawler/tests/test_search_pass.py` (append)

**Interfaces:**
- Consumes: `crawler.learn.tokenize.service_terms(text) -> list[str]` (existing); `new_by_phrase` (Task 5).
- Produces: `SearchPass(..., breed_sink=None, promote_min=2)`. For each phrase with `new_by_phrase[p] >= promote_min`, `breed_sink(term)` is called for every `service_terms()` mined from that phrase's winning candidate names. The sink (wired in runner) appends the term to the miner candidate pool **only if it is not in the admin-rejected set** — human reject wins.

- [ ] **Step 1: Write the failing test**

```python
# append to crawler/tests/test_search_pass.py
def test_productive_phrase_breeds_terms_low_yield_does_not(tmp_path):
    grid = QueryGrid(["стоматологія військовим", "квіти прикордонникам"])
    clock = [0.0]
    state = SearchState(str(tmp_path / "s.json"), clock=lambda: clock[0])
    plan = _Plan({"стоматологія військовим": [
        _cand("Стоматологія Люкс Дніпро", "https://lux.ua"),
        _cand("Стоматклініка Світ", "https://svit.ua")]})   # 2 new -> >= promote_min
    bred = []
    sp = SearchPass([plan], state, grid, block_size=2, ttl_seconds=100.0,
                    page_cap=1, breed_sink=bred.append, promote_min=2)
    clock[0] += 10.0
    sp.run(known=set())
    assert any("стоматолог" in t for t in bred)     # bred from the winning names
    # the barren phrase produced nothing -> no breeding from it
    assert all("квіт" not in t for t in bred)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_search_pass.py -k breeds -q`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'breed_sink'`

- [ ] **Step 3: Write minimal implementation**

Extend `SearchPass.__init__` with `breed_sink=None, promote_min=2` (store on `self`). In `run`, inside the `if any_success:` block (after `record_yield`), add:

```python
            if self._breed_sink is not None:
                from crawler.learn.tokenize import service_terms
                winners_by_phrase: dict[str, list[str]] = {p: [] for p in batch}
                for c in out:
                    ph = attribution.get(
                        (c.discovery_note.split(": ", 1)[1]
                         if c.discovery_note and ": " in c.discovery_note else None))
                    if ph is not None:
                        winners_by_phrase.setdefault(ph, []).append(c.name or "")
                for p in batch:
                    if new_by_phrase[p] >= self._promote_min:
                        for name in winners_by_phrase.get(p, []):
                            for term in service_terms(name):
                                self._breed_sink(term)     # sink filters admin-rejected
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_search_pass.py -k breeds -q`
Expected: PASS

- [ ] **Step 5: Wire the sink (respect admin rejects) + full suite**

In `runner.py` / `wiring.py`, build the sink so it appends to the miner candidate pool the existing `learn_and_reload_grid` tick already consumes, **filtered by the admin-rejected set** the crawler already fetches (`ApiClient` `/query-terms/rejected`). Confirm the exact append target on read (the miner's candidate file, `config.query_candidates_path`, per `crawler/learn/audit.py::write_candidates`). Sink shape:

```python
def _breed_sink(term: str) -> None:
    t = term.casefold().strip()
    if not t or t in rejected_terms:      # human reject wins
        return
    bred_terms.add(t)                     # flushed into the candidate pool at the learn tick
```

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS (all green)

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/discovery/search_pass.py crawler/crawler/runner.py crawler/crawler/wiring.py crawler/tests/test_search_pass.py
git commit -m "feat(crawler): reward-driven phrase breeding (add half), respects admin rejects"
```

---

## Task 5C: Protected terms exempt from auto-retire + admin override surface

**Files:**
- Modify: `crawler/crawler/discovery/search_pass.py` `_collect_due` (protected exemption)
- Modify: backend `query_terms` model/API (add `protected` flag + manual-add endpoint)
- Modify: admin Vue query-terms view (protected toggle + manual add/remove)
- Test: `crawler/tests/test_search_pass.py` (append); backend `tests/test_query_terms_admin.py` (append)

**Interfaces:**
- Consumes: an admin-managed `protected_terms: set[str]` the crawler already can fetch alongside approved/rejected.
- Produces: `SearchPass(..., protected_terms=frozenset())`. A protected phrase always gets base TTL (never auto-retired), regardless of `phrase_stats`.

- [ ] **Step 1: Write the failing test (crawler exemption)**

```python
# append to crawler/tests/test_search_pass.py
def test_protected_phrase_never_retired(tmp_path):
    grid = QueryGrid(["ручний термін"])
    clock = [0.0]
    state = SearchState(str(tmp_path / "s.json"), clock=lambda: clock[0])
    # make it look chronically dry
    for _ in range(10):
        state.record_yield("ручний термін", 0)
    sp = SearchPass([], state, grid, block_size=1, ttl_seconds=100.0,
                    protected_terms=frozenset({"ручний термін"}))
    # protected => due-walk uses base TTL, not the backed-off one
    assert sp._effective_ttl_for("ручний термін") == 100.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_search_pass.py -k protected -q`
Expected: FAIL — no `protected_terms` param / `_effective_ttl_for`.

- [ ] **Step 3: Implement the exemption**

Add `protected_terms=frozenset()` to `SearchPass.__init__`. Add a small helper and use it in `_collect_due`:

```python
    def _effective_ttl_for(self, kw: str) -> float:
        if kw in self._protected_terms:
            return self._ttl                       # human-protected: never suppressed
        return self._state.effective_ttl(kw, self._ttl,
                                         cold_tries=self._cold_tries, mult_cap=self._mult_cap)
```

and in `_collect_due` replace the `effective_ttl` call with `ttl = self._effective_ttl_for(kw)`.

- [ ] **Step 4: Run to verify it passes + full suite**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_search_pass.py -k protected -q && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS

- [ ] **Step 5: Backend — `protected` flag + manual add (confirm-on-read)**

In the backend `query_terms` table/router (see `backend/app/routers/*query*`, and the existing admin endpoints referenced by `backend/tests/test_query_terms_admin.py`): add a boolean `protected` column (Alembic migration), expose it in the term DTO, add `POST /api/internal/query-terms` (or admin route) for manual term add with `protected=true`, and include protected terms in the set the crawler fetches. Write a backend test asserting a manually-added protected term is returned and flagged. Keep the existing approve/reject/unreject intact.

- [ ] **Step 6: Admin UI — toggle + manual add/remove (confirm-on-read)**

In the admin Vue query-terms view (the one from the `ubd-admin-query-term-unreject` work): add a "protected/manual" toggle per term and a manual-add input; wire to the new backend endpoints. This is the human override surface for correcting the auto-loop. Verify via `npm run build` + a Vitest for the new control.

- [ ] **Step 7: Commit**

```bash
git add crawler/crawler/discovery/search_pass.py crawler/tests/test_search_pass.py backend/ admin/
git commit -m "feat: protected/manual query terms — human override exempt from auto-retire"
```

---

## Task 6: Config tunables

**Files:**
- Modify: `crawler/crawler/config.py` (dataclass field ~line 73; settings field ~line 202; mapping ~line 353 — the existing three-part pattern for `crawl_delay_cap_seconds`)
- Test: `crawler/tests/test_config.py` (append)

**Interfaces:**
- Produces: `Config.phrase_cold_tries: int = 3`, `Config.phrase_ttl_mult_cap: float = 8.0`, `Config.phrase_ewma_alpha: float = 0.3`, populated from env `PHRASE_COLD_TRIES`, `PHRASE_TTL_MULT_CAP`, `PHRASE_EWMA_ALPHA`.

- [ ] **Step 1: Write the failing test**

```python
# append to crawler/tests/test_config.py
def test_phrase_scheduler_tunables_have_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("CRAWLER_API_KEY", "k")
    monkeypatch.setenv("INTERNAL_API_URL", "http://x")
    from crawler.config import load_config
    cfg = load_config()
    assert cfg.phrase_cold_tries == 3
    assert cfg.phrase_ttl_mult_cap == 8.0
    assert cfg.phrase_ewma_alpha == 0.3
```

(If `load_config` needs more env, mirror the setup already used by the other tests in `test_config.py`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_config.py -k phrase_scheduler -q`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'phrase_cold_tries'`

- [ ] **Step 3: Write minimal implementation**

Add to the `Config` dataclass (next to `crawl_delay_cap_seconds`, ~line 73):

```python
    phrase_cold_tries: int = 3
    phrase_ttl_mult_cap: float = 8.0
    phrase_ewma_alpha: float = 0.3
```

Add to the settings source class (next to line 202):

```python
    phrase_cold_tries: int = 3
    phrase_ttl_mult_cap: float = 8.0
    phrase_ewma_alpha: float = 0.3
```

Add to the `Config(...)` construction mapping (next to line 353):

```python
        phrase_cold_tries=s.phrase_cold_tries,
        phrase_ttl_mult_cap=s.phrase_ttl_mult_cap,
        phrase_ewma_alpha=s.phrase_ewma_alpha,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_config.py -k phrase_scheduler -q`
Expected: PASS

- [ ] **Step 5: Thread the tunables into the callers**

In `search_pass.py` `_collect_due`, pass the configured values. Simplest: store them on `SearchPass.__init__` (add params `cold_tries`, `mult_cap` with the same defaults) and pass to `effective_ttl`. Then in `wiring.py` where `SearchPass(...)` is constructed, pass `cold_tries=config.phrase_cold_tries, mult_cap=config.phrase_ttl_mult_cap`. Likewise thread `phrase_ewma_alpha` into the `record_yield(p, new_by_phrase[p], alpha=self._alpha)` call. Show the exact `SearchPass.__init__` signature edit:

```python
    def __init__(self, plans, state, grid, block_size, static_keywords=None,
                 ttl_seconds=0.0, page_cap=1, cold_tries=3, mult_cap=8.0, alpha=0.3):
        ...
        self._cold_tries = cold_tries
        self._mult_cap = mult_cap
        self._alpha = alpha
```

and use `self._cold_tries` / `self._mult_cap` in `_collect_due`, `self._alpha` in `record_yield`.

- [ ] **Step 6: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS (all green)

- [ ] **Step 7: Commit**

```bash
git add crawler/crawler/config.py crawler/crawler/discovery/search_pass.py crawler/crawler/wiring.py crawler/tests/test_config.py
git commit -m "feat(crawler): config tunables for adaptive phrase scheduler"
```

---

## Task 7: Saturation gauge log line (observability + optional cadence)

**Files:**
- Modify: `crawler/crawler/runner.py` (active cycle, near where `self._search_pass.run(...)` is appended, ~line 184-187)
- Test: `crawler/tests/test_runner.py` (append a focused test or assert on a log capture)

**Interfaces:**
- Consumes: `SearchState.coverage_counts()` (Task 4), `coverage.saturation` (Task 1).
- Produces: one INFO log per active cycle: `active coverage: observed=<n> saturation=<pct>` — no behaviour change to scheduling in this task. **The saturation value is a DIRECTIONAL gauge only** (targeted sampling biases Chao1 — see coverage.py caveat); log it for trend observability, do NOT branch scheduling on its absolute value. A cadence-stretch is a documented follow-up, and even then only on a sustained upward TREND, never a single reading.

- [ ] **Step 1: Write the failing test**

```python
# append to crawler/tests/test_runner.py
import logging
from crawler.discovery.coverage import saturation


def test_saturation_gauge_is_logged(caplog):
    # coverage_counts -> observed=4,f1=2,f2=1 -> saturation ~0.714
    from crawler.discovery.coverage import saturation as sat
    pct = sat(4, 2, 1)
    assert 0.70 < pct < 0.73     # guards the formula the runner will log
```

(The runner-level assertion can be a `caplog.records` check if `test_runner.py` already builds a Runner; otherwise this guards the value the log line uses.)

- [ ] **Step 2: Run test to verify it fails / passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_runner.py -k saturation -q`
Expected: PASS for the formula guard (this task's risk is the wiring, not the math).

- [ ] **Step 3: Add the log line in runner.py active cycle**

Right after the active `SearchPass` feed is collected (~line 187), add:

```python
                obs, f1, f2 = self._search_pass._state.coverage_counts()
                if obs:
                    from crawler.discovery.coverage import saturation as _sat
                    log.info("active coverage: observed=%d saturation=%.1f%%",
                             obs, 100.0 * _sat(obs, f1, f2))
```

(If `runner.py` holds the state elsewhere, read it from the same place `SearchPass` does; keep it a pure read — no scheduling change here.)

- [ ] **Step 4: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS (all green)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/runner.py crawler/tests/test_runner.py
git commit -m "feat(crawler): log Chao1 active-coverage saturation gauge per cycle"
```

---

## Task 8: Deploy + live validation

**Files:** none (ops task).

- [ ] **Step 1: Rebuild + recreate crawler**

```bash
cd /d/ubd_probe && docker compose build crawler && docker compose up -d crawler
```

- [ ] **Step 2: Confirm the gauge appears and dry phrases back off**

```bash
docker compose logs --since 20m crawler 2>&1 | grep -iE "active coverage|saturation"
```
Expected: periodic `active coverage: observed=… saturation=…%` lines.

- [ ] **Step 3: Inspect that phrase_stats/host_freq persist**

```bash
docker exec ubd_probe-crawler-1 python -c "import json;s=json.load(open('/data/search_state.json'));print('phrases tracked:',len(s.get('phrase_stats',{})));print('hosts tracked:',len(s.get('host_freq',{})))"
```
Expected: non-zero counts growing across cycles.

- [ ] **Step 4: Self-reported productivity metric (no human in the loop)**

Success must be observable from logs alone — the system reports it, no manual analysis. Extend the Task 7 gauge line to also emit per-cycle productivity: sum the batch `new_by_phrase` and the batch size in `SearchPass.run` (already available), expose them, and log:

```python
log.info("active productivity: new_domains=%d / queries=%d (%.2f new/query) | %s",
         new_domains, queries_issued, (new_domains / max(1, queries_issued)),
         f"saturation={100.0 * _sat(obs, f1, f2):.1f}%")
```

Then the ONLY check is: over ~48h the `new/query` ratio holds or rises while total `queries` drops (budget concentrated) and `saturation` trends up. No baseline spreadsheet, no manual comparison — grep the one metric line:

```bash
docker compose logs --since 48h crawler 2>&1 | grep "active productivity" | tail -20
```
This runs unattended; nobody needs to be present for the scheduler to self-tune.

---

# Part B — Fetch cost & politeness (from the infra research thread)

## Task 9: Per-host 429/Retry-After penalty in DomainRateLimiter

**Files:**
- Modify: `crawler/crawler/ratelimit.py` (`DomainRateLimiter.__init__` line 31-37; `wait` line 47-57)
- Test: `crawler/tests/test_ratelimit.py`

**Interfaces:**
- Produces: `DomainRateLimiter.penalize(domain: str, seconds: float) -> None` — extend the domain's next-allowed time; `wait()` sleeps to honor it.

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_ratelimit.py
from crawler.ratelimit import DomainRateLimiter


class _Clock:
    def __init__(self): self.t = 0.0; self.slept = []
    def monotonic(self): return self.t
    def sleep(self, s):
        self.slept.append(s); self.t += s


def test_penalize_forces_wait_until_retry_after():
    c = _Clock()
    rl = DomainRateLimiter(min_delay=0.0, sleep=c.sleep, monotonic=c.monotonic)
    rl.wait("shop.ua")                 # first call, no wait
    rl.penalize("shop.ua", 30.0)       # server said Retry-After: 30
    rl.wait("shop.ua")                 # must sleep ~30s
    assert c.slept and abs(sum(c.slept) - 30.0) < 1e-6


def test_penalize_ignores_nonpositive():
    c = _Clock()
    rl = DomainRateLimiter(min_delay=0.0, sleep=c.sleep, monotonic=c.monotonic)
    rl.penalize("x.ua", 0.0)
    rl.wait("x.ua")
    assert c.slept == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_ratelimit.py -q`
Expected: FAIL — `AttributeError: 'DomainRateLimiter' object has no attribute 'penalize'`

- [ ] **Step 3: Write minimal implementation**

Add `self._penalty_until: dict[str, float] = {}` to `DomainRateLimiter.__init__` (after line 37). Add the method:

```python
    def penalize(self, domain: str, seconds: float) -> None:
        """Продовжити паузу для домену (напр. HTTP 429/503 Retry-After). Наступний
        wait() цього домену чекатиме щонайменше до penalty_until."""
        if seconds <= 0:
            return
        with self._domain_lock(domain):
            until = self._monotonic() + seconds
            self._penalty_until[domain] = max(self._penalty_until.get(domain, 0.0), until)
```

In `wait`, honor the penalty just before recording `_last` (inside the domain lock, after the min-delay sleep block):

```python
            penalty = self._penalty_until.get(domain, 0.0)
            if penalty > now:
                self._sleep(penalty - now)
                now = penalty
            self._last[domain] = now
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_ratelimit.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/ratelimit.py crawler/tests/test_ratelimit.py
git commit -m "feat(crawler): per-host Retry-After penalty in DomainRateLimiter"
```

---

## Task 10: Read `<link rel=canonical>` and carry it on RawItem

**Files:**
- Modify: `crawler/crawler/models.py` (add field to `RawItem`, near line 59)
- Modify: `crawler/crawler/fetchers/website.py` (add `_extract_canonical` near `_extract_image` ~line 54; call it in `fetch` ~line 331; pass to `RawItem` ~line 361)
- Test: `crawler/tests/test_website_fetcher.py`

**Interfaces:**
- Produces: `RawItem.canonical_url: str | None`; `WebsiteFetcher.fetch` populates it from `link[rel="canonical"]` (http/https, `_safe_url`-validated).

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_website_fetcher.py
from crawler.fetchers.website import WebsiteFetcher


class _Resp:
    def __init__(self, text, status=200, headers=None):
        self.text = text; self.status_code = status; self.headers = headers or {}
    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError("err", request=None, response=None)


class _Client:
    def __init__(self, resp): self._resp = resp
    def get(self, url, follow_redirects=True, headers=None):
        return self._resp


def test_fetch_extracts_canonical_url():
    html = ('<html><head><link rel="canonical" href="https://shop.ua/offer">'
            '</head><body><div>Знижка 20% для військових у нашому магазині сьогодні</div>'
            '</body></html>')
    f = WebsiteFetcher(_Client(_Resp(html)))
    items, _ = f.fetch({"id": 1, "url_or_handle": "https://shop.ua/offer?utm=x"}, None)
    assert items and items[0].canonical_url == "https://shop.ua/offer"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_website_fetcher.py -q`
Expected: FAIL — `AttributeError: 'RawItem' object has no attribute 'canonical_url'` (or TypeError on kwarg)

- [ ] **Step 3: Write minimal implementation**

In `models.py`, add to `RawItem` (after line 59-area fields):

```python
    canonical_url: str | None = None
```

In `website.py`, add the extractor:

```python
def _extract_canonical(tree, base_url: str) -> str | None:
    """Сайт сам оголошує канонічну URL сторінки (згортає фасети/пагінацію/utm-варіанти).
    Використовуємо як ідентичність офера для дедупу, з fallback на нашу канонікалізацію."""
    node = tree.css_first('link[rel="canonical"]')
    if node is not None:
        return _safe_url(base_url, node.attributes.get("href"))
    return None
```

In `fetch`, after `tree = HTMLParser(resp.text)` (line 330), add:

```python
            canonical = _extract_canonical(tree, url)
```

and add `canonical_url=canonical,` to the `RawItem(...)` constructor (in the `items.append(...)` block ~line 361).

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_website_fetcher.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Prefer canonical for the page-identity dedup key**

Read `crawler/crawler/extract/aggregate.py` around line 61 (`page_content_hash(head.title, head.provider, head.article_url, discounts)`) and where `article_url` is derived from the `RawItem`. Change that derivation to `item.canonical_url or item.url`. Write a test in `crawler/tests/test_aggregate.py` (or the existing extractor test) asserting two `RawItem`s with the same `canonical_url` but different `url` (e.g. `?utm=a` vs `?utm=b`) produce the same page identity. Commit both together.

- [ ] **Step 6: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS (all green)

- [ ] **Step 7: Commit**

```bash
git add crawler/crawler/models.py crawler/crawler/fetchers/website.py crawler/crawler/extract/aggregate.py crawler/tests/test_website_fetcher.py crawler/tests/test_aggregate.py
git commit -m "feat(crawler): honor <link rel=canonical> for offer page identity/dedup"
```

---

## Task 11: Real UA contact (config-driven)

**Files:**
- Modify: `crawler/crawler/config.py` (add `contact_url`), `crawler/crawler/wiring.py` (line 39 `_UA`)
- Test: `crawler/tests/test_config.py` (append)

**Interfaces:**
- Produces: `Config.contact_url: str` (env `CRAWLER_CONTACT`, default keeps current placeholder); UA becomes `f"Mozilla/5.0 (compatible; UBDCrawler/0.1; +{contact_url})"`.

- [ ] **Step 1: Write the failing test**

```python
# append to crawler/tests/test_config.py
def test_contact_url_default_and_override(monkeypatch):
    monkeypatch.setenv("CRAWLER_API_KEY", "k")
    monkeypatch.setenv("INTERNAL_API_URL", "http://x")
    monkeypatch.setenv("CRAWLER_CONTACT", "https://ubd.real/contact")
    from crawler.config import load_config
    assert load_config().contact_url == "https://ubd.real/contact"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_config.py -k contact_url -q`
Expected: FAIL — `AttributeError: ... 'contact_url'`

- [ ] **Step 3: Write minimal implementation**

Add `contact_url: str = "https://ubd.example"` to the `Config` dataclass and the settings source (env `CRAWLER_CONTACT`), plus the mapping line, mirroring Task 6's triple. In `wiring.py`, build the UA from it:

```python
def _build_ua(contact_url: str) -> str:
    return f"Mozilla/5.0 (compatible; UBDCrawler/0.1; +{contact_url})"
```

and pass `contact_url` where the website client is created (replace the module-level `_UA` use at line 43 with `_build_ua(config.contact_url)`). **Operator note:** set `CRAWLER_CONTACT` in `crawler/.env` to a real reachable page/email so site admins can contact instead of blocking.

- [ ] **Step 4: Run test + full suite**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_config.py -k contact_url -q && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/config.py crawler/crawler/wiring.py crawler/tests/test_config.py
git commit -m "feat(crawler): config-driven real UA contact (CRAWLER_CONTACT)"
```

---

## Task 12: Conditional GET (304) + 429 wiring in WebsiteFetcher

**Files:**
- Create: `crawler/crawler/discovery/validator_store.py`
- Modify: `crawler/crawler/fetchers/website.py` (`WebsiteFetcher.__init__`, `fetch`)
- Modify: `crawler/crawler/discovery/harvest.py` (wire throttle sink to `DomainRateLimiter.penalize`, ~line 175-192)
- Modify: `crawler/crawler/wiring.py` (construct + inject the store)
- Test: `crawler/tests/test_validator_store.py`, `crawler/tests/test_website_fetcher.py` (append)

**Interfaces:**
- Produces:
  - `ValidatorStore(path)` with `.get(url) -> dict|None`, `.put(url, etag, last_modified) -> None` (JSON `{url: {"etag": str, "last_modified": str}}`, atomic save).
  - `WebsiteFetcher(client, store=None, throttle_sink=None)` — when `store` is set, sends `If-None-Match`/`If-Modified-Since`; on 304 returns `([], last_seen_key)` and touches no network parse; on 429/503 calls `throttle_sink(host, seconds)` from `Retry-After`.

- [ ] **Step 1: Write the failing test (store)**

```python
# crawler/tests/test_validator_store.py
from crawler.discovery.validator_store import ValidatorStore


def test_put_get_roundtrip(tmp_path):
    s = ValidatorStore(str(tmp_path / "v.json"))
    s.put("https://a.ua", etag='"abc"', last_modified="Wed, 21 Oct 2026 07:28:00 GMT")
    assert s.get("https://a.ua") == {"etag": '"abc"',
                                     "last_modified": "Wed, 21 Oct 2026 07:28:00 GMT"}
    assert s.get("https://missing.ua") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_validator_store.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement the store**

```python
# crawler/crawler/discovery/validator_store.py
"""Персистентний per-URL стор HTTP-валідаторів (ETag/Last-Modified) для conditional
GET. Незмінна сторінка на переобході коштує 304 (кілька байт) замість повного body."""
import json
import os


class ValidatorStore:
    def __init__(self, path: str):
        self._path = path
        try:
            with open(path, encoding="utf-8") as f:
                self._data = json.load(f)
            if not isinstance(self._data, dict):
                self._data = {}
        except (OSError, ValueError):
            self._data = {}

    def get(self, url: str) -> dict | None:
        return self._data.get(url)

    def put(self, url: str, etag: str | None, last_modified: str | None) -> None:
        if not etag and not last_modified:
            return
        self._data[url] = {"etag": etag, "last_modified": last_modified}
        self._save()

    def _save(self) -> None:
        directory = os.path.dirname(self._path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = f"{self._path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False)
        os.replace(tmp, self._path)
```

- [ ] **Step 4: Write the failing fetcher tests (304 + 429)**

```python
# append to crawler/tests/test_website_fetcher.py
from crawler.discovery.validator_store import ValidatorStore


def test_304_short_circuits_without_parsing(tmp_path):
    store = ValidatorStore(str(tmp_path / "v.json"))
    store.put("https://a.ua", etag='"v1"', last_modified=None)
    sent = {}
    class C:
        def get(self, url, follow_redirects=True, headers=None):
            sent.update(headers or {})
            return _Resp("", status=304, headers={"ETag": '"v1"'})
    items, key = WebsiteFetcher(C(), store=store).fetch(
        {"id": 1, "url_or_handle": "https://a.ua"}, "prev-key")
    assert sent.get("If-None-Match") == '"v1"'
    assert items == [] and key == "prev-key"          # nothing changed, cheap


def test_429_calls_throttle_sink_with_retry_after():
    hits = []
    class C:
        def get(self, url, follow_redirects=True, headers=None):
            return _Resp("", status=429, headers={"Retry-After": "42"})
    WebsiteFetcher(C(), throttle_sink=lambda host, s: hits.append((host, s))).fetch(
        {"id": 1, "url_or_handle": "https://a.ua/x"}, None)
    assert hits == [("a.ua", 42.0)]
```

- [ ] **Step 5: Implement conditional GET + 429 in WebsiteFetcher**

Extend `__init__`:

```python
    def __init__(self, client: httpx.Client, store=None, throttle_sink=None):
        self._client = client
        self._store = store
        self._throttle = throttle_sink
```

At the top of `fetch`, build conditional headers and handle 304/429 **before** `raise_for_status`/parse:

```python
        url = source["url_or_handle"]
        headers = {}
        if self._store is not None:
            v = self._store.get(url) or {}
            if v.get("etag"):
                headers["If-None-Match"] = v["etag"]
            if v.get("last_modified"):
                headers["If-Modified-Since"] = v["last_modified"]
        try:
            resp = self._client.get(url, follow_redirects=True, headers=headers or None)
            if resp.status_code in (429, 503) and self._throttle is not None:
                from crawler.util.hosts import bare_host
                try:
                    secs = float(resp.headers.get("Retry-After", "") or 0.0)
                except ValueError:
                    secs = 0.0
                self._throttle(bare_host(url), secs)
                return [], last_seen_key
            if resp.status_code == 304:
                return [], last_seen_key            # незмінна сторінка — дешево
            resp.raise_for_status()
            if self._store is not None:
                self._store.put(url, resp.headers.get("ETag"),
                                resp.headers.get("Last-Modified"))
            tree = HTMLParser(resp.text)
            ...  # (rest unchanged)
```

(Keep the existing broad `except Exception` tail; the 304/429 returns sit inside the `try`.)

- [ ] **Step 6: Wire the store + throttle sink**

In `harvest.py`, where `fetcher.fetch(...)` is called (line ~192) with `self._domain_rl` available, construct the fetcher (or pass) with `throttle_sink=lambda host, s: self._domain_rl.penalize(host, s)`. In `wiring.py`, create `ValidatorStore(config.validator_store_path)` (add a config path default `/data/validators.json`, Task-6-style triple) and inject it into the `WebsiteFetcher`.

- [ ] **Step 7: Run tests + full suite**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_validator_store.py tests/test_website_fetcher.py -q && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS (all green)

- [ ] **Step 8: Commit**

```bash
git add crawler/crawler/discovery/validator_store.py crawler/crawler/fetchers/website.py crawler/crawler/discovery/harvest.py crawler/crawler/wiring.py crawler/crawler/config.py crawler/tests/test_validator_store.py crawler/tests/test_website_fetcher.py
git commit -m "feat(crawler): conditional GET (304) + 429 Retry-After host backoff"
```

---

## Self-Review

**Spec coverage** (against the two research threads combined):
- Adaptive query selection / MAB exploit-explore → Tasks 2,3,5 (EWMA reward + adaptive TTL + young-phrase exploration). ✅
- Set-cover / "learn rewarding vs non-rewarding keywords" (Ntoulas) → dry-phrase backoff retires low-reward cells automatically. ✅
- BIDIRECTIONAL loop (retire AND add) → retire = Tasks 2,3,5; add = Task 5B (reward-driven breeding into the existing self-learning tick). ✅
- REVERSIBLE retirement (auto re-add) → `effective_ttl` returns to base once EWMA>0 after a reprobe (Task 3). ✅
- HUMAN override coexists (correction when the auto-loop errs) → Task 5C (protected terms exempt from auto-retire; breeding respects admin rejects; admin UI add/remove). ✅
- Capture-recapture / Chao1 stopping & coverage → Tasks 1,4,7. ✅
- Reuse existing reward signal (no new labels) → Task 5 reuses `new_by_phrase`. ✅
- Harvest-rate / relevant-domains metric (TRES) → Task 8 validation on NEW sources/domains. ✅
- Infra cost-reduction from the separate research thread → **now included as Part B**: 429/`Retry-After` backoff (Task 9), `<link rel=canonical>` dedup (Task 10), real UA contact (Task 11), conditional GET 304 (Task 12). ✅

**Placeholder scan:** every code step contains real code; no TBD/TODO. Three integration points explicitly note a "confirm at execution" read because the surrounding code must be re-read then: Task 7 (`runner.py` state access), Task 10 Step 5 (`aggregate.py` article-identity derivation), Task 12 Step 6 (`harvest.py` fetcher construction + `wiring.py` injection). The new code in each is fully specified; only the exact insertion line is confirmed on read.

**Type consistency:** `record_yield(phrase, new_count, alpha)`, `effective_ttl(phrase, base_ttl, *, cold_tries, mult_cap)`, `note_host(host)`, `coverage_counts()->(observed,f1,f2)`, `chao1(observed,f1,f2)`, `saturation(observed,f1,f2)`, `penalize(domain, seconds)`, `ValidatorStore.get/put`, `WebsiteFetcher(client, store, throttle_sink)`, `RawItem.canonical_url` — names/signatures consistent across all tasks. ✅

## Deliberately out of scope (true YAGNI — no evidence yet, revisit only on data)

- **SimHash/MinHash near-duplicate at crawl time** — the backend already dedups (exact hash + Jaccard 0.6 + promo + hub). A second near-dup layer without measured leakage the backend misses = over-engineering.
- **Full per-phrase Chao1** (vs the global gauge here) and **UCB/Thompson randomized exploration** — only if the deterministic tries-based exploration proves insufficient in Task 8 metrics.
- **Scored/weighted frontier ranking beyond the existing offer-slug sort** — the walker already prioritizes offer slugs + cap; a weighted score has unclear ROI under our search-driven model.
- **Embedding cosine keyword expansion** — larger change to grid generation; revisit only if coverage saturation plateaus while Chao1 still estimates unfound-domain headroom.
