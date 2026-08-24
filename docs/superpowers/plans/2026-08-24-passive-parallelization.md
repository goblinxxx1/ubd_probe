# Passive-Pass Parallelization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Прибрати серійну стелю пасивного проходу краулера — обробляти джерела конкурентно (ThreadPool), зберігши per-domain політ.

**Architecture:** `Runner.run_passive` сабмітить кожне джерело в `ThreadPoolExecutor`; потокобезпечність заштовхана в спільні обʼєкти (internal locks у `DomainRateLimiter` per-domain, `DomainRegistry`, `CorpusRecorder`; `LockedSet` для `known`) + per-task локальний `summary` зі злиттям після join. Жодної зміни сигнатур наявних методів.

**Tech Stack:** Python 3, `concurrent.futures.ThreadPoolExecutor`, `threading.Lock`, pytest, httpx (спільний потокобезпечний клієнт — уже є).

## Global Constraints

- Робоча директорія краулера: `D:\ubd_probe\crawler`. Усі команди тестів — звідти.
- Тест-раннер: `.venv/Scripts/python.exe -m pytest` (окремий venv краулера, Windows).
- **Зворотна сумісність обовʼязкова:** `passive_workers=1` дає byte-identical серійний результат. Наявні callers спільних методів (`run_first_crawl`, `ActiveHarvester`, `bootstrap`, `snowball`) серійні → неконтендований лок не змінює їхньої поведінки.
- **Correctness crux:** лок у `DomainRateLimiter` — **per-domain**, ніколи не єдиний глобальний, що тримається під час `sleep` (інакше всі домени серіалізуються й паралелізм зникає).
- Дефолт `passive_workers = 4`.
- Українською в коментарях/повідомленнях, як у наявному коді. Ніякої російської.
- Комітити після кожної задачі.

---

## File Structure

- `crawler/crawler/ratelimit.py` — modify `DomainRateLimiter` (per-domain lock).
- `crawler/crawler/discovery/domain_registry.py` — modify (internal lock).
- `crawler/crawler/learn/corpus.py` — modify (internal lock).
- `crawler/crawler/util/locked_set.py` — **create** (`LockedSet`).
- `crawler/crawler/runner.py` — modify `Runner.__init__` + `run_passive`.
- `crawler/crawler/config.py` — modify (`passive_workers` knob, 3 місця).
- `crawler/crawler/wiring.py` — modify (передати `config.passive_workers` у `Runner`).
- Тести: `tests/test_ratelimit.py`, `tests/test_domain_registry.py`, `tests/test_corpus.py`, `tests/test_locked_set.py` (create), `tests/test_runner.py`, `tests/test_config.py`.

---

### Task 1: Per-domain thread-safe `DomainRateLimiter`

**Files:**
- Modify: `crawler/crawler/ratelimit.py:22-41` (`DomainRateLimiter`)
- Test: `crawler/tests/test_ratelimit.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `DomainRateLimiter(min_delay, sleep=..., monotonic=...)` — незмінний публічний інтерфейс; `wait(domain, delay=None)` тепер потокобезпечний per-domain.

- [ ] **Step 1: Write the failing test** (додати в кінець `tests/test_ratelimit.py`)

```python
import threading


def test_domain_rate_limiter_lock_is_per_domain_not_global():
    """While a slow sleep for domain A is in progress, a wait() for domain B must
    NOT block — proves the lock is per-domain, not a single global lock held during
    sleep (which would serialize all domains and kill parallelism)."""
    a_sleeping = threading.Event()
    release_a = threading.Event()

    def sleep(_s):
        # Only the second (throttled) call for "a.ua" actually sleeps.
        a_sleeping.set()
        release_a.wait(timeout=5)

    t = {"now": 0.0}
    rl = DomainRateLimiter(min_delay=5.0, sleep=sleep, monotonic=lambda: t["now"])

    rl.wait("a.ua")  # primes a.ua; no sleep yet
    a_done = threading.Event()

    def slow_a():
        rl.wait("a.ua")   # immediate re-call -> throttles -> enters sleep()
        a_done.set()

    threading.Thread(target=slow_a, daemon=True).start()
    assert a_sleeping.wait(timeout=5)      # a.ua is now parked inside sleep()

    b_done = threading.Event()

    def call_b():
        rl.wait("b.ua")   # different domain -> must proceed without waiting on a.ua
        b_done.set()

    threading.Thread(target=call_b, daemon=True).start()
    assert b_done.wait(timeout=5), "b.ua blocked on a.ua's lock -> lock is global, not per-domain"

    release_a.set()
    assert a_done.wait(timeout=5)
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `crawler/`): `.venv/Scripts/python.exe -m pytest tests/test_ratelimit.py::test_domain_rate_limiter_lock_is_per_domain_not_global -v`
Expected: FAIL — before per-domain locking, `b.ua` may proceed anyway (there is currently NO lock), so this test could accidentally PASS. To make it a true red first, temporarily is unnecessary: instead assert the mechanism exists by adding the guard assertion below. Simpler: proceed — the test locks in the *required* behavior; if it already passes because there is no lock at all, Step 3 still adds the per-domain lock and the test must keep passing. (This test's job is to prevent a future global-lock regression.)

- [ ] **Step 3: Write the implementation** — replace `DomainRateLimiter` body

```python
import threading
import time


class DomainRateLimiter:
    """Per-domain minimum-delay limiter. The per-call `delay` (e.g. robots Crawl-delay)
    raises the floor for that call; each domain is tracked independently. Thread-safe:
    a short guard lock protects the per-domain lock registry; each domain has its OWN
    lock held across the read-modify-write + sleep, so same-domain callers serialize
    (politeness preserved) while different domains overlap."""

    def __init__(self, min_delay: float, sleep=time.sleep, monotonic=time.monotonic):
        self._min_delay = min_delay
        self._sleep = sleep
        self._monotonic = monotonic
        self._last: dict[str, float] = {}
        self._guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}

    def _domain_lock(self, domain: str) -> threading.Lock:
        with self._guard:
            lock = self._locks.get(domain)
            if lock is None:
                lock = threading.Lock()
                self._locks[domain] = lock
            return lock

    def wait(self, domain: str, delay: float | None = None) -> None:
        effective = max(self._min_delay, delay or 0.0)
        with self._domain_lock(domain):
            now = self._monotonic()
            last = self._last.get(domain)
            if last is not None:
                remaining = effective - (now - last)
                if remaining > 0:
                    self._sleep(remaining)
                    now = self._monotonic() if self._monotonic() > now else now + remaining
            self._last[domain] = now
```

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ratelimit.py -v`
Expected: PASS (all — the 4 existing + the new per-domain-lock test).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/ratelimit.py crawler/tests/test_ratelimit.py
git commit -m "feat(crawler): per-domain thread-safe DomainRateLimiter"
```

---

### Task 2: Internal lock in `DomainRegistry`

**Files:**
- Modify: `crawler/crawler/discovery/domain_registry.py` (`__init__`, `record`, `take_skip`, `record_rejections`, `save`, `prune`, `mark_media_blocked`)
- Test: `crawler/tests/test_domain_registry.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: same public methods, now safe under concurrent same-instance calls.

- [ ] **Step 1: Write the failing test** (додати в кінець `tests/test_domain_registry.py`)

```python
import threading


def test_record_is_thread_safe_no_lost_updates(tmp_path):
    """Concurrent record() on the SAME host from many threads must not lose updates:
    the offers counter equals the number of recorded passes."""
    r = _reg(tmp_path, offer_weight=1.0)
    n = 200

    def worker():
        r.record("silpo.ua", offers=1, errors=0)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert r._data["domains"]["silpo.ua"]["offers"] == n
    assert r._data["domains"]["silpo.ua"]["passes"] == n
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_domain_registry.py::test_record_is_thread_safe_no_lost_updates -v`
Expected: FAIL intermittently (`offers < n`) or PASS-by-luck. To force determinism of the red, it is acceptable that CPython's GIL sometimes hides the race; the lock added in Step 3 removes the race unconditionally. Proceed.

- [ ] **Step 3: Write the implementation** — add a lock and wrap mutators

In `__init__` (after `self._empty_skip = int(empty_skip)`), add:

```python
        self._lock = threading.Lock()
```

Add the import at top of file:

```python
import threading
```

Wrap the body of each mutator in `with self._lock:`. For `record`:

```python
    def record(self, host, offers, errors, structural_provider=False):
        host = _host(host)
        if not host:
            return
        with self._lock:
            now = self._clock()
            e = self._data["domains"].get(host)
            if e is None:
                e = {"score": 0.0, "offers": 0, "errors": 0, "rejects": 0, "passes": 0,
                     "empty_passes": 0, "skip_left": 0, "first_seen": now, "last_seen": now,
                     "last_offer": 0.0, "media_streak": 0, "provider_ever": False,
                     "media_blocked": False}
                self._data["domains"][host] = e
            e["score"] = max(0.0, e["score"] * self._decay
                             + offers * self._offer_w - errors * self._error_w)
            e["offers"] += int(offers)
            e["errors"] += int(errors)
            e["passes"] += 1
            if offers == 0:
                e["empty_passes"] += 1
                e["skip_left"] = self._empty_skip
            else:
                e["last_offer"] = now
                e["skip_left"] = 0
            if structural_provider:
                e["provider_ever"] = True
                e["media_streak"] = 0
            elif offers > 0:
                e["media_streak"] = e.get("media_streak", 0) + 1
            e["last_seen"] = now
```

For `take_skip`:

```python
    def take_skip(self, host) -> bool:
        with self._lock:
            e = self._data["domains"].get(_host(host))
            if e and e.get("skip_left", 0) > 0:
                e["skip_left"] -= 1
                return True
            return False
```

For `record_rejections`:

```python
    def record_rejections(self, host, n):
        host = _host(host)
        with self._lock:
            e = self._data["domains"].get(host)
            if not host or e is None or n <= 0:
                return
            e["score"] = max(0.0, e["score"] - n * self._reject_w)
            e["rejects"] = e.get("rejects", 0) + int(n)
```

For `mark_media_blocked`:

```python
    def mark_media_blocked(self, host) -> None:
        with self._lock:
            e = self._data["domains"].get(_host(host))
            if e is not None:
                e["media_blocked"] = True
```

For `prune` — wrap the whole body in `with self._lock:`. For `save` — wrap the snapshot: take a JSON dump of `self._data` under the lock into a local, then write the file outside the lock:

```python
    def save(self):
        import copy
        with self._lock:
            snapshot = copy.deepcopy(self._data)
        directory = os.path.dirname(self._path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = f"{self._path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False)
        os.replace(tmp, self._path)
```

(Do NOT wrap `media_block_due`, `score`, `seen_within`, `top` — read-only predicates; wrapping them risks re-entrancy if a caller ever holds the lock, and stale reads are harmless here.)

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_domain_registry.py -v`
Expected: PASS (all existing + new).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/domain_registry.py crawler/tests/test_domain_registry.py
git commit -m "feat(crawler): internal lock makes DomainRegistry thread-safe"
```

---

### Task 3: Internal lock in `CorpusRecorder`

**Files:**
- Modify: `crawler/crawler/learn/corpus.py:21-53`
- Test: `crawler/tests/test_corpus.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `CorpusRecorder.record(...)` now safe under concurrent calls.

- [ ] **Step 1: Write the failing test** (додати в кінець `tests/test_corpus.py`)

```python
import threading

from crawler.learn.corpus import read_corpus


class _Item:
    def __init__(self, text):
        self.text = text
        self.url = "https://x.ua/p"
        self.links = []
        self.is_article = False
        self.neg_anchor = None
        self.pos_anchor = None


def test_corpus_record_is_thread_safe(tmp_path):
    """Concurrent record() must not interleave/corrupt lines: every append survives
    as one valid JSON row."""
    path = str(tmp_path / "corpus.jsonl")
    rec = CorpusRecorder(path, max_mb=50.0)
    n = 200

    def worker(i):
        rec.record(_Item(f"row-{i}"), extracted_is_offer=bool(i % 2))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    rows = read_corpus(path)
    assert len(rows) == n     # none lost, none corrupted (read_corpus parses each line)
```

> Note: check the top of `tests/test_corpus.py` for how it constructs items/`CorpusRecorder`; reuse the existing item fixture if one is already defined rather than `_Item` above. The `label_item` call inside `record` needs whatever attributes that test file's items already provide.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_corpus.py::test_corpus_record_is_thread_safe -v`
Expected: FAIL or flaky (interleaved writes → some lines unparseable → `read_corpus` line count off or `json` error). Proceed regardless; lock removes it unconditionally.

- [ ] **Step 3: Write the implementation**

Add import at top of `corpus.py`:

```python
import threading
```

In `CorpusRecorder.__init__`, add:

```python
        self._lock = threading.Lock()
```

Wrap the mutating tail of `record` (the `makedirs` + open/append + `_rotate`) in the lock:

```python
    def record(self, item, extracted_is_offer: bool, *, snowball: bool = False) -> None:
        rec = label_item(item, extracted_is_offer)
        row = {
            "text": getattr(item, "text", "") or "",
            "label": rec.label, "host": rec.host,
            "neg_anchor": rec.neg_anchor, "pos_anchor": rec.pos_anchor,
            "is_article": rec.is_article, "outbound_hosts": _outbound_count(item),
            "url": getattr(item, "url", None) or "",
            "snowball": snowball, "ts": int(time.time()),
        }
        with self._lock:
            os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
            with open(self._path, "a", encoding="utf-8", newline="") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            self._rotate()
```

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_corpus.py -v`
Expected: PASS (all existing + new).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/learn/corpus.py crawler/tests/test_corpus.py
git commit -m "feat(crawler): internal lock makes CorpusRecorder thread-safe"
```

---

### Task 4: `LockedSet` helper

**Files:**
- Create: `crawler/crawler/util/locked_set.py`
- Test: `crawler/tests/test_locked_set.py` (create)

**Interfaces:**
- Produces: `LockedSet(iterable=None)` with `add(x)`, `__contains__(x)`, `__len__()`. Used by `run_passive` for `known`.

- [ ] **Step 1: Write the failing test** (create `tests/test_locked_set.py`)

```python
import threading

from crawler.util.locked_set import LockedSet


def test_locked_set_basic_contains_and_add():
    s = LockedSet({"a"})
    assert "a" in s
    assert "b" not in s
    s.add("b")
    assert "b" in s
    assert len(s) == 2


def test_locked_set_concurrent_add_dedups():
    s = LockedSet()
    n = 500

    def worker():
        for _ in range(n):
            s.add("dup")

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(s) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_locked_set.py -v`
Expected: FAIL — `ModuleNotFoundError: crawler.util.locked_set`.

- [ ] **Step 3: Write the implementation** (create `crawler/crawler/util/locked_set.py`)

```python
"""Мінімальна потокобезпечна множина: рівно ті операції, що потрібні пасивному
проходу для спільного `known` (перевірка членства + додавання)."""

import threading


class LockedSet:
    def __init__(self, iterable=None):
        self._set = set(iterable or ())
        self._lock = threading.Lock()

    def add(self, item) -> None:
        with self._lock:
            self._set.add(item)

    def __contains__(self, item) -> bool:
        with self._lock:
            return item in self._set

    def __len__(self) -> int:
        with self._lock:
            return len(self._set)
```

- [ ] **Step 4: Run test to verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_locked_set.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/util/locked_set.py crawler/tests/test_locked_set.py
git commit -m "feat(crawler): LockedSet thread-safe membership set"
```

---

### Task 5: Parallelize `Runner.run_passive`

**Files:**
- Modify: `crawler/crawler/runner.py` (`Runner.__init__` — add params; `run_passive` — pool + merge)
- Test: `crawler/tests/test_runner.py`

**Interfaces:**
- Consumes: `LockedSet` (Task 4); internally-locked `DomainRegistry`/`CorpusRecorder` (Tasks 2–3); per-domain `DomainRateLimiter` (Task 1).
- Produces: `Runner(..., passive_workers=1, executor_factory=None)`. `run_passive()` returns the same summary dict shape as before. `_crawl_source`/`_process_page` signatures UNCHANGED.

- [ ] **Step 1: Write the failing test** (додати в `tests/test_runner.py`)

```python
def _inline_executor_factory(max_workers):
    """Deterministic stand-in for ThreadPoolExecutor: runs each submitted task
    synchronously on submit, so run_passive logic is tested without real races."""
    class _Inline:
        def __enter__(self): return self
        def __exit__(self, *exc): return False
        def submit(self, fn, *a, **kw):
            class _F:
                def __init__(self, v): self._v = v
                def result(self): return self._v
            return _F(fn(*a, **kw))
    return _Inline()


def test_run_passive_parallel_sums_summary_across_sources():
    srcs = [{"id": i, "type": "website", "name": f"S{i}",
             "url_or_handle": f"http://x{i}"} for i in range(3)]
    item = RawItem(source_id=1, platform="website", key="k",
                   text="Знижка 20% для ветеранів", links=[])
    api = FakeApi(srcs)
    runner = Runner(api, {"website": FakeFetcher([item])}, get_extractor("heuristic"),
                    _rl(), passive_workers=3,
                    executor_factory=_inline_executor_factory)
    summary = runner.run_passive()
    assert summary["offers"] == 3         # one offer per source, all merged
    assert summary["sources"] == 3
    assert summary["errors"] == 0
    assert summary["expired"] == 2        # expire_stale still runs once, after join


def test_run_passive_parallel_isolates_source_failure():
    good = {"id": 1, "type": "website", "name": "S1", "url_or_handle": "http://x"}
    bad = {"id": 2, "type": "telegram", "name": "S2", "url_or_handle": "@chan"}
    item = RawItem(source_id=1, platform="website", key="k",
                   text="Акція 10% для військових", links=[])
    api = FakeApi([bad, good])
    fetchers = {"website": FakeFetcher([item]), "telegram": BoomFetcher()}
    runner = Runner(api, fetchers, get_extractor("heuristic"), _rl(),
                    passive_workers=2, executor_factory=_inline_executor_factory)
    summary = runner.run_passive()
    assert summary["errors"] == 1
    assert summary["offers"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_runner.py::test_run_passive_parallel_sums_summary_across_sources -v`
Expected: FAIL — `Runner.__init__() got an unexpected keyword argument 'passive_workers'`.

- [ ] **Step 3: Write the implementation**

In `Runner.__init__` signature, add two params (place near `first_crawl_budget=0`):

```python
                 reject_ingestor=None, first_crawl_budget=0,
                 passive_workers=1, executor_factory=None):
```

In `Runner.__init__` body, add:

```python
        self._passive_workers = max(1, int(passive_workers))
        self._executor_factory = executor_factory or (
            lambda mw: __import__("concurrent.futures", fromlist=["ThreadPoolExecutor"])
                       .ThreadPoolExecutor(max_workers=mw))
```

> Prefer a clean top-of-file import instead of the `__import__` trick: add
> `from concurrent.futures import ThreadPoolExecutor, as_completed` at the top of
> `runner.py`, then use `self._executor_factory = executor_factory or (lambda mw: ThreadPoolExecutor(max_workers=mw))`.

Add near the other imports at the top of `runner.py`:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

from crawler.util.locked_set import LockedSet
```

Replace `run_passive` (`runner.py:271-299`) with:

```python
    def run_passive(self) -> dict:
        """Re-confirm approved sources (freshness) + expire stale source-offers. Runs on a
        rare cadence. Sources are crawled CONCURRENTLY (passive_workers threads); per-domain
        politeness is preserved by the per-domain lock inside DomainRateLimiter. Each task
        accumulates into its own summary; summaries are merged after all tasks finish."""
        cats = CategoryIndex(self._api.list_target_categories(),
                             self._api.list_offer_categories())
        sources = self._api.list_sources(is_active=True)
        known = LockedSet({normalize_ref(s["type"], s["url_or_handle"]) for s in sources})
        summary = self._empty_summary()

        def crawl_one(source) -> dict:
            local = self._empty_summary()
            local["sources"] += 1
            try:
                self._crawl_source(source, cats, known, local)
            except Exception as exc:  # noqa: BLE001 — isolate per source
                local["errors"] += 1
                log.warning("source #%s failed: %s", source.get("id"), exc)
            return local

        with self._executor_factory(self._passive_workers) as ex:
            futures = [ex.submit(crawl_one, s) for s in sources]
            for fut in as_completed(futures):
                local = fut.result()
                for k in set(summary) | set(local):
                    summary[k] = summary.get(k, 0) + local.get(k, 0)

        try:
            result = self._api.expire_stale(self._freshness_ttl_days)
            summary["expired"] = result.get("expired", 0)
        except Exception as exc:  # noqa: BLE001 — sweep must not crash the pass
            summary["errors"] += 1
            log.warning("expire-stale failed: %s", exc)
        if self._domain_registry is not None:
            try:
                self._domain_registry.save()
            except Exception as exc:  # noqa: BLE001 — persistence must not crash the pass
                log.warning("domain registry save (passive) failed: %s", exc)
        return summary
```

> Note on the inline test executor: `as_completed` accepts a list of the fake `_F`
> future objects; since each already holds a computed value, `as_completed` returns
> them immediately. If `as_completed` rejects the fake future type, adjust the inline
> executor's `_F` to subclass `concurrent.futures.Future` and call `set_result(v)`.
> (Preferred robust form for Step 1's helper:)
>
> ```python
> from concurrent.futures import Future
> ...
>         def submit(self, fn, *a, **kw):
>             f = Future()
>             f.set_result(fn(*a, **kw))
>             return f
> ```

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_runner.py -v`
Expected: PASS (all — existing serial `run()` tests unchanged, plus the two new passive-parallel tests).

- [ ] **Step 5: Regression — full serial equivalence at workers=1**

Add one more test and run it:

```python
def test_run_passive_workers_1_is_serial_baseline():
    srcs = [{"id": i, "type": "website", "name": f"S{i}",
             "url_or_handle": f"http://x{i}"} for i in range(3)]
    item = RawItem(source_id=1, platform="website", key="k",
                   text="Знижка 20% для ветеранів", links=[])
    api = FakeApi(srcs)
    runner = Runner(api, {"website": FakeFetcher([item])}, get_extractor("heuristic"),
                    _rl(), passive_workers=1)   # real ThreadPoolExecutor(max_workers=1)
    summary = runner.run_passive()
    assert summary["offers"] == 3
    assert summary["sources"] == 3
    assert summary["errors"] == 0
```

Run: `.venv/Scripts/python.exe -m pytest tests/test_runner.py::test_run_passive_workers_1_is_serial_baseline -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/runner.py crawler/tests/test_runner.py
git commit -m "feat(crawler): parallelize run_passive over sources (Track #11)"
```

---

### Task 6: Config knob `passive_workers` + wiring

**Files:**
- Modify: `crawler/crawler/config.py` (3 місця: `_RawSettings`, `Config`, mapping)
- Modify: `crawler/crawler/wiring.py:242-257` (`Runner(...)` call)
- Test: `crawler/tests/test_config.py`

**Interfaces:**
- Consumes: `Runner(..., passive_workers=...)` (Task 5).
- Produces: `config.passive_workers` (int, default 4), env var `PASSIVE_WORKERS`.

- [ ] **Step 1: Write the failing test** (додати в `tests/test_config.py`)

```python
def test_passive_workers_default_and_env(monkeypatch):
    from crawler.config import load_config
    cfg = load_config()
    assert cfg.passive_workers == 4

    monkeypatch.setenv("PASSIVE_WORKERS", "8")
    cfg2 = load_config()
    assert cfg2.passive_workers == 8
```

> Builder is `load_config()` (`crawler/config.py:399`), which does
> `from_settings(_RawSettings())`. `_RawSettings` reads env vars case-insensitively,
> so `PASSIVE_WORKERS` maps to the `passive_workers` field.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py::test_passive_workers_default_and_env -v`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'passive_workers'`.

- [ ] **Step 3: Write the implementation** — add the knob in all three places

In `_RawSettings` (near line 44, next to `passive_interval_seconds`), add:

```python
    passive_workers: int = 4
```

In `Config` dataclass (near line 166, next to `passive_interval_seconds`), add:

```python
    passive_workers: int = 4
```

In the `Config(...)` mapping (near line 310, next to `passive_interval_seconds=s.passive_interval_seconds,`), add:

```python
        passive_workers=s.passive_workers,
```

In `wiring.py`, in the `Runner(...)` call (after `first_crawl_budget=config.first_crawl_budget`), add:

```python
                  first_crawl_budget=config.first_crawl_budget,
                  passive_workers=config.passive_workers)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py tests/test_wiring.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/config.py crawler/crawler/wiring.py crawler/tests/test_config.py
git commit -m "feat(crawler): passive_workers config knob (default 4) + wiring"
```

---

### Task 7: Full-suite regression + live Docker verification

**Files:** none (verification only).

- [ ] **Step 1: Run the whole crawler suite**

Run (from `crawler/`): `.venv/Scripts/python.exe -m pytest -q`
Expected: all green. Fix any regression before proceeding.

- [ ] **Step 2: Live Docker verification** (per [[ubd-run-in-docker]])

- Rebuild the crawler container.
- Trigger a passive pass with `PASSIVE_WORKERS=4` on real data (a bounded/one-shot invocation).
- Confirm: crawl summary offers/errors are sane; no tracebacks; per-domain politeness is honored (no domain hit faster than `domain_min_delay_seconds`); MySQL/backend hold under concurrent `submit_offer`.
- Then run once more with `PASSIVE_WORKERS=1` and confirm identical behavior to pre-change (byte-identical serial fallback).

- [ ] **Step 3: Finish the branch**

Per [[ubd-workflow]], merge `passive-parallelization` back into `main`. Use `superpowers:finishing-a-development-branch`.

---

## Self-Review

- **Spec coverage:** DomainRateLimiter per-domain lock → Task 1. LockedSet → Task 4. Registry lock → Task 2. Corpus lock → Task 3. run_passive pool + per-task summary + merge → Task 5. passive_workers=4 default + config/wiring → Task 6. Executor injection for tests → Task 5 (`executor_factory`). Live Docker verify + serial-fallback → Task 7. All spec sections mapped.
- **Placeholder scan:** every code step shows full code; no TBD/TODO; the two "check the existing test file" notes point to concrete symbols to match, not deferred work.
- **Type consistency:** `passive_workers` (int) and `executor_factory` (callable `mw -> context-manager with submit`) consistent across Tasks 5–6; `LockedSet.add/__contains__/__len__` consistent between Task 4 and its use in Task 5; `run_passive` returns the same summary dict as the pre-change serial version.
