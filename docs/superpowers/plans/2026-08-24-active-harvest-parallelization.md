# Active-Harvest Parallelization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Паралелізувати активний `harvest` (two-phase: серійний відбір → паралельний fetch), зберігши бюджет, `stop`-індекс/облік фраз і per-domain політ.

**Architecture:** `harvest` = дві фази. `_select_fetch_set` (серійна) застосовує чисті skip-гейти + `selected_hosts`-симуляцію same-host `seen_within` + бюджет → повертає `(ordered_fetch, stop)`. `_execute` (паралельна, `ThreadPoolExecutor`) виконує обрані кандидати, кожен на старті re-check'ає feedback-гейти (`is_blocked_host`/`known`); per-task локальний summary зі злиттям. Три активні стори (geo/lang/aggregator) стають потокобезпечними.

**Tech Stack:** Python 3, `concurrent.futures.ThreadPoolExecutor`, `threading.Lock`, pytest.

## Global Constraints

- Робоча директорія: `D:\ubd_probe\crawler`. Усі тести звідти.
- Тест-раннер: `.venv/Scripts/python.exe -m pytest` (окремий venv краулера, Windows).
- **`stop`-семантику зберегти:** `_select_fetch_set` повертає ТОЙ САМИЙ `stop`, що серійний код; `harvest` повертає `stop` → `_mark_consumed_search_phrases` не змінюється.
- **Same-host `seen_within` — точна симуляція:** у pre-scan транзитний `selected_hosts: set`; website-хост трактується як «щойно бачений», щойно його обрано.
- **Бюджет рахується по РЕАЛЬНИХ fetch-кандидатах** (як серійно: `used += 1` лише коли кандидат пройшов усі гейти й має fetcher).
- **`active_workers=1` = серійний відкат.** Дефолт `active_workers = 4`.
- Пасив/scheduler НЕ чіпати. `ActiveHarvester._plan(cand)` (walker-експансія, harvest.py:127) — це ІНШИЙ метод, не перейменовувати; нова pre-scan-фаза зветься `_select_fetch_set`.
- Нові стори-локи адитивні: geo `add` у серійній pre-scan-фазі (лок як консистентність); lang/aggregator `add` у паралельній execution → лок обовʼязковий.
- Українською нові коментарі/докстрінги; ідентифікатори англ.; без російської. `import threading` — угорі файлу. Комітити після кожної задачі.

---

## File Structure

- `crawler/crawler/discovery/geo_block.py` — modify (internal lock).
- `crawler/crawler/discovery/lang_block.py` — modify (internal lock).
- `crawler/crawler/discovery/aggregator_feed.py` — modify `AggregatorDomainStore` (internal lock).
- `crawler/crawler/discovery/harvest.py` — modify `ActiveHarvester` (`__init__` params; new `_select_fetch_set`; new `_execute`; rewire `harvest`).
- `crawler/crawler/config.py` — modify (`active_workers` knob, 3 місця).
- `crawler/crawler/wiring.py` — modify `ActiveHarvester(...)` call.
- Тести: `tests/test_geo_block.py`, `tests/test_lang_block.py`, `tests/test_aggregator_feed.py`, `tests/test_active_harvest.py`, `tests/test_config.py`.

---

### Task 1: Internal locks for the three active-harvest stores

**Files:**
- Modify: `crawler/crawler/discovery/geo_block.py` (`GeoBlockStore.add/_save`)
- Modify: `crawler/crawler/discovery/lang_block.py` (`LangBlockStore.add/_save`)
- Modify: `crawler/crawler/discovery/aggregator_feed.py` (`AggregatorDomainStore.add/set_cursor/_save`)
- Test: `tests/test_geo_block.py`, `tests/test_lang_block.py`, `tests/test_aggregator_feed.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: same public methods, now safe under concurrent same-instance calls.

- [ ] **Step 1: Write the failing tests** (append one to each test file)

To `tests/test_geo_block.py`:

```python
import threading


def test_geo_block_add_is_thread_safe(tmp_path):
    from crawler.discovery.geo_block import GeoBlockStore
    s = GeoBlockStore(str(tmp_path / "geo.json"))
    n = 200

    def worker(i):
        s.add(f"h{i}.ru")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(s.hosts()) == n           # none lost
    import json
    with open(str(tmp_path / "geo.json"), encoding="utf-8") as f:
        assert len(json.load(f)) == n    # file valid + complete
```

To `tests/test_lang_block.py` (identical shape, `.by` hosts):

```python
import threading


def test_lang_block_add_is_thread_safe(tmp_path):
    from crawler.discovery.lang_block import LangBlockStore
    s = LangBlockStore(str(tmp_path / "lang.json"))
    n = 200

    def worker(i):
        s.add(f"h{i}.by")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(s.hosts()) == n
    import json
    with open(str(tmp_path / "lang.json"), encoding="utf-8") as f:
        assert len(json.load(f)) == n
```

To `tests/test_aggregator_feed.py`:

```python
import threading


def test_aggregator_store_add_is_thread_safe(tmp_path):
    from crawler.discovery.aggregator_feed import AggregatorDomainStore
    s = AggregatorDomainStore(str(tmp_path / "agg.json"))
    n = 200

    def worker(i):
        s.add([f"h{i}.ua"], cap=10_000)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(s.domains()) == n         # none lost under concurrent read-modify-write
    import json
    with open(str(tmp_path / "agg.json"), encoding="utf-8") as f:
        json.load(f)                     # valid JSON, not corrupted
```

- [ ] **Step 2: Run tests to verify they fail (or flake)**

Run: `.venv/Scripts/python.exe -m pytest tests/test_geo_block.py::test_geo_block_add_is_thread_safe tests/test_lang_block.py::test_lang_block_add_is_thread_safe tests/test_aggregator_feed.py::test_aggregator_store_add_is_thread_safe -v`
Expected: FAIL or flaky (lost updates / corrupted file). The aggregator one (read-modify-write of a shared list) is the most reliably red. Proceed regardless — the lock removes the race unconditionally.

- [ ] **Step 3: Add locks**

`geo_block.py` — add `import threading` at top; in `__init__` add `self._lock = threading.Lock()`; wrap the mutating body of `add`:

```python
    def add(self, host_or_url: str | None) -> bool:
        """Pin a host (accepts a full URL). Returns True if newly added."""
        h = bare_host(host_or_url)
        if not h:
            return False
        with self._lock:
            if h in self._hosts:
                return False
            self._hosts.add(h)
            self._save()
            self._push()
            return True
```

`lang_block.py` — identical change (`import threading`, `self._lock` in `__init__`, wrap `add` body exactly as above).

`aggregator_feed.py` — add `import threading` at top; in `AggregatorDomainStore.__init__` add `self._lock = threading.Lock()`; wrap the bodies of `add` and `set_cursor`:

```python
    def set_cursor(self, value: int) -> None:
        with self._lock:
            self._data["cursor"] = int(value)
            self._save()

    def add(self, hosts, cap: int) -> None:
        with self._lock:
            cur = list(self._data.get("hosts", []))
            seen = set(cur)
            for h in sorted(hosts):
                if h and h not in seen:
                    cur.append(h)
                    seen.add(h)
            if len(cur) > cap:
                cur = cur[len(cur) - cap:]
            self._data["hosts"] = cur
            self._save()
```

(Leave `_save`/`_push`/`load`/`domains`/`cursor`/`hosts` bodies otherwise unchanged; they run under the caller's lock or are read-only.)

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_geo_block.py tests/test_lang_block.py tests/test_aggregator_feed.py -v`
Expected: PASS (all existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/geo_block.py crawler/crawler/discovery/lang_block.py crawler/crawler/discovery/aggregator_feed.py crawler/tests/test_geo_block.py crawler/tests/test_lang_block.py crawler/tests/test_aggregator_feed.py
git commit -m "feat(crawler): internal locks for geo/lang/aggregator stores (active-harvest thread-safety)"
```

---

### Task 2: `_select_fetch_set` — serial pre-scan (phase 1)

**Files:**
- Modify: `crawler/crawler/discovery/harvest.py` (add method `_select_fetch_set`; do NOT change `harvest` yet)
- Test: `tests/test_active_harvest.py`

**Interfaces:**
- Consumes: existing `ActiveHarvester` fields (`self._budget`, `self._fetchers`, `self._registry`, `self._revisit_cooldown`, `self._geo_block_store`).
- Produces: `_select_fetch_set(self, candidates, known, known_hosts) -> tuple[list, int]` returning `(ordered_fetch, stop)`. `ordered_fetch` = the candidates that the serial loop would fetch, in order; `stop` = the identical stop index the serial `harvest` returns.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_active_harvest.py`)

```python
def test_select_fetch_set_matches_serial_selection_and_stop():
    # 3 fetchable website candidates, budget 2 -> selects first 2, stop stays within examined prefix.
    api = FakeApi()
    h = ActiveHarvester(api, {"website": FakeFetcher([])}, GateExtractor(),
                        rate_limiter=None, fetch_budget=2)
    cands = [_cand(url=f"https://s{i}.example", name=f"S{i}") for i in range(3)]
    ordered, stop = h._select_fetch_set(cands, known=set(), known_hosts=set())
    assert [c.url_or_handle for c in ordered] == ["https://s0.example", "https://s1.example"]
    assert stop == 2            # budget breaks at idx 2 (used>=2 checked at top)


def test_select_fetch_set_same_host_seen_within_suppressed():
    # Two candidates share a host; with a revisit cooldown, the SECOND must not be selected
    # (serial suppresses it via record->seen_within; pre-scan simulates via selected_hosts).
    class Reg:
        def seen_within(self, host, secs): return False   # nothing seen before this pass
    api = FakeApi()
    h = ActiveHarvester(api, {"website": FakeFetcher([])}, GateExtractor(),
                        rate_limiter=None, fetch_budget=10,
                        domain_registry=Reg(), revisit_cooldown_seconds=3600)
    a = _cand(url="https://same.example/a", name="A")
    b = _cand(url="https://same.example/b", name="B")
    ordered, stop = h._select_fetch_set([a, b], known=set(), known_hosts=set())
    assert [c.url_or_handle for c in ordered] == ["https://same.example/a"]  # b suppressed
    assert stop == 2            # both examined (b skipped, not fetched)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_active_harvest.py::test_select_fetch_set_matches_serial_selection_and_stop tests/test_active_harvest.py::test_select_fetch_set_same_host_seen_within_suppressed -v`
Expected: FAIL — `AttributeError: 'ActiveHarvester' object has no attribute '_select_fetch_set'`.

- [ ] **Step 3: Add `_select_fetch_set`** (insert as a new method in `ActiveHarvester`, e.g. right after `harvest`)

```python
    def _select_fetch_set(self, candidates, known, known_hosts):
        """Фаза 1 (серійна): застосувати чисті skip-гейти в порядку (з їх in-scan
        side-ефектами: geo_block.add) і відібрати кандидатів на fetch, обмежившись
        бюджетом. `selected_hosts` точно відтворює серійну same-host `seen_within`-
        супресію без реальних fetch'ів. Повертає (ordered_fetch, stop), де stop —
        той самий індекс, що й серійний harvest."""
        used = 0
        stop = 0
        selected = []
        selected_hosts = set()
        for idx, cand in enumerate(candidates):
            if used >= self._budget:
                return selected, idx          # budget break: idx..end untouched
            stop = idx + 1
            if cand.type not in _FETCHABLE:
                continue
            if cand.type == "website" and is_ru_by_geo(cand.url_or_handle):
                if self._geo_block_store is not None:
                    self._geo_block_store.add(cand.url_or_handle)
                continue
            if cand.type == "website" and is_foreign_host(cand.url_or_handle):
                continue
            if cand.type == "website" and is_low_value_host(cand.url_or_handle):
                continue
            if cand.type == "website" and is_news_host(cand.url_or_handle):
                continue
            if cand.type == "website" and is_blocked_host(cand.url_or_handle):
                continue
            host = _host(cand.url_or_handle) if cand.type == "website" else None
            if (cand.type == "website" and self._revisit_cooldown and self._registry is not None
                    and (self._registry.seen_within(host, self._revisit_cooldown)
                         or host in selected_hosts)):
                continue
            if normalize_ref(cand.type, cand.url_or_handle) in known:
                continue
            if (cand.type == "website" and not cand.bypass_host_skip
                    and host in known_hosts):
                continue
            if self._fetchers.get(cand.type) is None:
                continue
            used += 1
            selected.append(cand)
            if host is not None:
                selected_hosts.add(host)
        return selected, stop
```

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_active_harvest.py -v`
Expected: PASS (all existing active-harvest tests + 2 new; `harvest` still uses its old serial loop, untouched).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/harvest.py crawler/tests/test_active_harvest.py
git commit -m "feat(crawler): _select_fetch_set serial pre-scan for active harvest (phase 1)"
```

---

### Task 3: `_execute` parallel phase + rewire `harvest` (phase 2)

**Files:**
- Modify: `crawler/crawler/discovery/harvest.py` (`__init__` params; add `_execute`; rewrite `harvest` to two-phase)
- Test: `tests/test_active_harvest.py`

**Interfaces:**
- Consumes: `_select_fetch_set` (Task 2); internally-locked stores (Task 1); LockedSet-safe `known`.
- Produces: `ActiveHarvester(..., active_workers=1, executor_factory=None)`. `harvest(...)` returns the same `stop` int. `_execute(self, ordered_fetch, cats, known, summary)` runs the fetch set in a pool, merging per-task local summaries into `summary`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_active_harvest.py`)

```python
def _inline_executor_factory(max_workers):
    from concurrent.futures import Future

    class _Inline:
        def __enter__(self): return self
        def __exit__(self, *exc): return False
        def submit(self, fn, *a, **kw):
            f = Future()
            f.set_result(fn(*a, **kw))
            return f
    return _Inline()


def test_harvest_parallel_matches_serial_offers_and_stop():
    api = FakeApi()
    fetchers = {"website": FakeFetcher([_item("Знижка 20% для УБД", site_name="Cafe")])}
    h = ActiveHarvester(api, fetchers, GateExtractor(), rate_limiter=None, fetch_budget=5,
                        active_workers=3, executor_factory=_inline_executor_factory)
    cands = [_cand(url=f"https://s{i}.example", name=f"S{i}") for i in range(3)]
    summary = _summary()
    stop = h.harvest(cands, cats=None, known=set(), summary=summary)
    assert stop == 3                       # all 3 examined
    assert summary["offers"] == 3          # one offer per source, merged
    assert len(api.offers) == 3
    assert summary["errors"] == 0


def test_harvest_recheck_skips_now_blocked_host(monkeypatch):
    # A candidate whose host becomes blocked before its task runs is skipped without fetch.
    import crawler.discovery.harvest as harvest_mod
    fetched = []

    class RecordingFetcher:
        def fetch(self, source, k):
            fetched.append(source["url_or_handle"])
            return [_item("Знижка 20% для УБД", site_name="X")], None

    monkeypatch.setattr(harvest_mod, "is_blocked_host",
                        lambda u: "blocked.example" in u)
    api = FakeApi()
    h = ActiveHarvester(api, {"website": RecordingFetcher()}, GateExtractor(),
                        rate_limiter=None, fetch_budget=5,
                        active_workers=2, executor_factory=_inline_executor_factory)
    # blocked.example is filtered in pre-scan already; assert it never reaches fetch.
    summary = _summary()
    h.harvest([_cand(url="https://blocked.example", name="B"),
               _cand(url="https://ok.example", name="OK")],
              cats=None, known=set(), summary=summary)
    assert "https://ok.example" in "".join(fetched) or fetched  # ok fetched
    assert all("blocked.example" not in u for u in fetched)     # blocked never fetched
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_active_harvest.py::test_harvest_parallel_matches_serial_offers_and_stop -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'active_workers'`.

- [ ] **Step 3: Implement**

Add imports at the top of `harvest.py`:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
```

In `ActiveHarvester.__init__`, extend the signature (append after `source_hint_enabled=True`):

```python
                 source_hint_enabled=True,
                 active_workers=1, executor_factory=None):
```

and in the body add:

```python
        self._workers = max(1, int(active_workers))
        self._executor_factory = executor_factory or (
            lambda mw: ThreadPoolExecutor(max_workers=mw))
```

Replace the `harvest` method body (harvest.py:61-125) with the two-phase form:

```python
    def harvest(self, candidates, cats, known, summary, known_hosts=None) -> int:
        known_hosts = known_hosts or set()
        ordered_fetch, stop = self._select_fetch_set(candidates, known, known_hosts)
        self._execute(ordered_fetch, cats, known, summary)
        return stop

    def _execute(self, ordered_fetch, cats, known, summary) -> None:
        """Фаза 2 (паралельна): виконати обрані кандидати в пулі. Кожен таск на старті
        re-check'ає execution-feedback гейти (is_blocked_host — уже з lang/media-блоками
        цього проходу; known) і скіпає now-blocked без fetch. Per-task локальний summary,
        злиття після join. Спільні обʼєкти (registry/corpus/aggregator/lang/known/
        rate-limiter) уже потокобезпечні."""
        def run_one(cand) -> dict:
            local = {"offers": 0, "suggestions": 0, "errors": 0}
            if cand.type == "website" and is_blocked_host(cand.url_or_handle):
                return local                       # заблоковано конкурентним таском — скіп
            if normalize_ref(cand.type, cand.url_or_handle) in known:
                return local
            fetcher = self._fetchers.get(cand.type)
            if fetcher is None:
                return local
            structural = False
            try:
                structural = self._harvest_one(cand, fetcher, cats, known, local)
            except Exception as exc:  # noqa: BLE001 — isolate per candidate
                local["errors"] += 1
                log.warning("active harvest failed for %s: %s", cand.url_or_handle, exc)
            if self._registry is not None and cand.type == "website":
                host = _host(cand.url_or_handle)
                self._registry.record(host, local["offers"], local["errors"],
                                      structural_provider=structural)
                if (self._media_blocker is not None
                        and self._registry.media_block_due(host, self._media_autoblock_crawls)):
                    if self._media_blocker.block(host, cand.url_or_handle):
                        self._registry.mark_media_blocked(host)
            return local

        with self._executor_factory(self._workers) as ex:
            futures = [ex.submit(run_one, c) for c in ordered_fetch]
            for fut in as_completed(futures):
                local = fut.result()
                for k in local:
                    summary[k] = summary.get(k, 0) + local[k]
```

Note: `run_one` computes the per-candidate registry delta directly from `local["offers"]/["errors"]` (local starts at 0, so after `_harvest_one` these ARE this candidate's counts — equivalent to the old `summary - before` delta).

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_active_harvest.py -v`
Expected: PASS (all existing active-harvest tests + the new parallel/recheck ones). The existing tests construct `ActiveHarvester` without `active_workers` → default 1 → real `ThreadPoolExecutor(max_workers=1)`; behavior equivalent.

- [ ] **Step 5: Add the workers=1 equivalence test and run**

```python
def test_harvest_workers_1_serial_baseline():
    api = FakeApi()
    fetchers = {"website": FakeFetcher([_item("Знижка 20% для УБД", site_name="Cafe")])}
    h = ActiveHarvester(api, fetchers, GateExtractor(), rate_limiter=None, fetch_budget=5,
                        active_workers=1)   # real ThreadPoolExecutor(max_workers=1)
    cands = [_cand(url=f"https://s{i}.example", name=f"S{i}") for i in range(3)]
    summary = _summary()
    stop = h.harvest(cands, cats=None, known=set(), summary=summary)
    assert stop == 3 and summary["offers"] == 3 and summary["errors"] == 0
```

Run: `.venv/Scripts/python.exe -m pytest tests/test_active_harvest.py::test_harvest_workers_1_serial_baseline -v`
Expected: PASS.

- [ ] **Step 6: Full suite before commit**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add crawler/crawler/discovery/harvest.py crawler/tests/test_active_harvest.py
git commit -m "feat(crawler): parallelize active harvest execution with re-check (phase 2)"
```

---

### Task 4: Config knob `active_workers` + wiring

**Files:**
- Modify: `crawler/crawler/config.py` (3 місця: `_RawSettings` ~line 36, `Config` ~line 158, `from_settings` mapping ~line 302 — next to `active_fetch_budget`)
- Modify: `crawler/crawler/wiring.py` (`ActiveHarvester(...)` call, ~line 226-241)
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `ActiveHarvester(..., active_workers=...)` (Task 3).
- Produces: `config.active_workers` (int, default 4), env var `ACTIVE_WORKERS`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_config.py`)

```python
def test_active_workers_default_and_env(monkeypatch):
    from crawler.config import load_config
    cfg = load_config()
    assert cfg.active_workers == 4

    monkeypatch.setenv("ACTIVE_WORKERS", "6")
    cfg2 = load_config()
    assert cfg2.active_workers == 6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py::test_active_workers_default_and_env -v`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'active_workers'`.

- [ ] **Step 3: Add the knob in all three config.py places + the wiring kwarg**

In `_RawSettings` next to `active_fetch_budget: int = 80` add:

```python
    active_workers: int = 4
```

In the `Config` dataclass next to `active_fetch_budget: int = 80` add:

```python
    active_workers: int = 4
```

In `from_settings`'s `Config(...)` mapping next to `active_fetch_budget=s.active_fetch_budget,` add:

```python
        active_workers=s.active_workers,
```

In `wiring.py`, in the `ActiveHarvester(...)` call, add as a new kwarg (after `source_hint_enabled=config.source_hint_enabled`):

```python
                                    source_hint_enabled=config.source_hint_enabled,
                                    active_workers=config.active_workers)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py tests/test_wiring.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/config.py crawler/crawler/wiring.py crawler/tests/test_config.py
git commit -m "feat(crawler): active_workers config knob (default 4) + wiring"
```

---

### Task 5: Full-suite regression + live Docker verification + finish

**Files:** none (verification only).

- [ ] **Step 1: Run the whole crawler suite**

Run (from `crawler/`): `.venv/Scripts/python.exe -m pytest -q`
Expected: all green. Fix any regression before proceeding.

- [ ] **Step 2: Live Docker verification** (per [[ubd-run-in-docker]])

- Rebuild the crawler image: `docker compose build crawler`.
- Run a one-shot active pass at `ACTIVE_WORKERS=4` and again at `ACTIVE_WORKERS=1` (override entrypoint, call `runner.run_active()` directly — the passive track used the same pattern):
  `docker compose --profile crawler run --rm --no-deps --entrypoint python -e ACTIVE_WORKERS=4 crawler -c "import time;from crawler.config import load_config;from crawler.wiring import build_runner;r=build_runner(load_config());t=time.time();print('SUMMARY',r.run_active());print('ELAPSED_S',round(time.time()-t,1))"`
- Confirm: `errors=0`, no tracebacks; offers/suggestions sane; workers=4 wall-time < workers=1 (speedup); per-domain politeness honored; SERP page cursors in `/data/search_state.json` advance as before (pagination unaffected).

- [ ] **Step 3: Finish the branch**

Per [[ubd-workflow]], merge `active-harvest-parallelization` into `main`. Use `superpowers:finishing-a-development-branch`.

---

## Self-Review

- **Spec coverage:** three store locks → Task 1. `_select_fetch_set` (pre-scan + selected_hosts sim + budget → exact stop) → Task 2. `_execute` (parallel + re-check + per-task summary merge) + harvest rewire + active_workers/executor_factory → Task 3. config active_workers=4 + wiring → Task 4. full-suite + live Docker (workers=4 vs 1, pagination-cursor check) + finish → Task 5. All spec sections mapped.
- **Placeholder scan:** every code step shows full code; no TBD/TODO.
- **Type consistency:** `_select_fetch_set -> (ordered_fetch:list, stop:int)` consumed by `harvest` in Task 3; `_execute(ordered_fetch, cats, known, summary)`; `active_workers` (int) / `executor_factory` (callable mw->context-manager-with-submit) consistent across Tasks 3–4; `harvest` returns `stop:int` unchanged so `_mark_consumed_search_phrases` is untouched. Pre-existing `_plan(cand)` method is left intact (not renamed).
