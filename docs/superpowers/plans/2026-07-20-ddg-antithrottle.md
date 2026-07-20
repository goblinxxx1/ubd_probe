# DDG Anti-Throttle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the crawler's active search (DuckDuckGo via `ddgs`) from getting the single outbound IP rate-limited, by rotating one endpoint per query, tripping per-backend circuit-breakers, caching keyword results, pacing slowly, and backing off globally.

**Architecture:** Three cooperating pieces in `crawler/crawler/discovery/`: `SearchState` (one atomic JSON file holding per-backend cooldown, keyword cache, rotation cursor, global backoff), `RotatingDdgProvider` (one backend per keyword, round-robin, skips cooled backends), and `SearchCache` (TTL decorator, cache hit = no network). `build_search_provider` wires `SearchCache(RotatingDdgProvider(...))`. `ActiveDiscovery`, `SearxngProvider`, `classify_candidate`, `_normalize_url` are unchanged.

**Tech Stack:** Python 3.12, `ddgs` 9.14.4, `pydantic-settings`, `pytest`. No new dependencies.

## Global Constraints

- Language for any user-facing text/comments follows existing code (English comments, Ukrainian keywords in `.env`). Discussion with the user is Ukrainian, code stays as-is.
- Single IP only — **no proxies, no Tor** in this track.
- Scope is active-search anti-throttling only. Do **not** touch backend, admin, public, freshness, promotion, or seed-catalog.
- Backend pool is exactly `google,startpage,duckduckgo,yahoo,brave` (decision locked).
- Tests must never hit the real network: inject `ddgs_factory`, `sleep`, `clock`/`rand`, and a `tmp_path` state file.
- Run tests from `crawler/`: `./.venv/Scripts/python.exe -m pytest -q`. Whole suite is green at 139 tests today and must stay green.
- Every mutating `SearchState` method writes the file atomically (`tmp` + `os.replace`). Read-only methods (`cache_get`, `is_healthy`, `in_global_backoff`, `cursor`) never write.

---

### Task 1: `SearchState` — persistent JSON state

**Files:**
- Create: `crawler/crawler/discovery/search_state.py`
- Test: `crawler/tests/test_search_state.py`

**Interfaces:**
- Consumes: `crawler.models.SourceCandidate` (`name`, `type`, `url_or_handle`, `discovered_from_source_id`, `discovery_note`).
- Produces:
  - `SearchState.load(path, clock=time.time) -> SearchState`
  - `SearchState(path, data=None, clock=time.time)`
  - `.cursor -> int` (property, read-only), `.set_cursor(value: int) -> None`
  - `.is_healthy(backend: str) -> bool`
  - `.record_success(backend: str) -> None`
  - `.record_block(backend: str, base: float, cap: float, jitter: float, rand) -> float` (returns applied cooldown seconds)
  - `.in_global_backoff() -> bool`
  - `.set_global_backoff(seconds: float) -> None`
  - `.cache_get(keyword: str, ttl_seconds: float) -> list[SourceCandidate] | None`
  - `.cache_put(keyword: str, candidates: list[SourceCandidate]) -> None`

- [ ] **Step 1: Write the failing tests**

Create `crawler/tests/test_search_state.py`:

```python
import json

from crawler.discovery.search_state import SearchState
from crawler.models import SourceCandidate


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def _state(tmp_path, clock):
    return SearchState(str(tmp_path / "state.json"), clock=clock)


def test_fresh_backend_is_healthy(tmp_path):
    st = _state(tmp_path, Clock())
    assert st.is_healthy("google") is True


def test_record_block_sets_exponential_cooldown(tmp_path):
    clk = Clock(1000.0)
    st = _state(tmp_path, clk)
    d1 = st.record_block("google", base=300.0, cap=21600.0, jitter=0.0, rand=lambda: 0.0)
    assert d1 == 300.0                       # base * 2^0
    assert st.is_healthy("google") is False
    d2 = st.record_block("google", base=300.0, cap=21600.0, jitter=0.0, rand=lambda: 0.0)
    assert d2 == 600.0                        # base * 2^1
    clk.t = 1000.0 + 600.0
    assert st.is_healthy("google") is True    # cooldown elapsed


def test_record_block_caps_cooldown(tmp_path):
    st = _state(tmp_path, Clock())
    d = None
    for _ in range(20):
        d = st.record_block("g", base=300.0, cap=1000.0, jitter=0.0, rand=lambda: 0.0)
    assert d == 1000.0


def test_record_success_resets(tmp_path):
    st = _state(tmp_path, Clock())
    st.record_block("google", base=300.0, cap=21600.0, jitter=0.0, rand=lambda: 0.0)
    st.record_success("google")
    assert st.is_healthy("google") is True


def test_cursor_roundtrip(tmp_path):
    st = _state(tmp_path, Clock())
    assert st.cursor == 0
    st.set_cursor(3)
    assert st.cursor == 3


def test_global_backoff(tmp_path):
    clk = Clock(1000.0)
    st = _state(tmp_path, clk)
    assert st.in_global_backoff() is False
    st.set_global_backoff(60.0)
    assert st.in_global_backoff() is True
    clk.t = 1061.0
    assert st.in_global_backoff() is False


def test_cache_put_get_within_ttl(tmp_path):
    st = _state(tmp_path, Clock())
    cands = [SourceCandidate(name="Shop", type="website", url_or_handle="https://a.example/x")]
    st.cache_put("Знижки УБД", cands)
    got = st.cache_get("  знижки убд  ", ttl_seconds=100.0)   # normalized key
    assert got is not None
    assert [(c.type, c.url_or_handle) for c in got] == [("website", "https://a.example/x")]
    assert got[0].discovery_note == "ddg-cache: знижки убд"


def test_cache_miss_after_ttl(tmp_path):
    clk = Clock(1000.0)
    st = _state(tmp_path, clk)
    st.cache_put("kw", [SourceCandidate(name="x", type="website", url_or_handle="https://a/x")])
    clk.t = 1101.0
    assert st.cache_get("kw", ttl_seconds=100.0) is None


def test_persistence_roundtrip_and_atomic_file(tmp_path):
    path = str(tmp_path / "state.json")
    st = SearchState(path, clock=Clock())
    st.set_cursor(2)
    st.record_block("brave", base=10.0, cap=100.0, jitter=0.0, rand=lambda: 0.0)
    st.cache_put("kw", [SourceCandidate(name="x", type="website", url_or_handle="https://a/x")])
    reloaded = SearchState.load(path, clock=Clock())
    assert reloaded.cursor == 2
    assert reloaded.is_healthy("brave") is False
    assert reloaded.cache_get("kw", ttl_seconds=1e9) is not None
    with open(path, encoding="utf-8") as f:
        assert "cache" in json.load(f)


def test_load_missing_or_corrupt_starts_clean(tmp_path):
    missing = SearchState.load(str(tmp_path / "nope.json"), clock=Clock())
    assert missing.cursor == 0
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    st = SearchState.load(str(bad), clock=Clock())
    assert st.cursor == 0
    assert st.is_healthy("x") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_search_state.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'crawler.discovery.search_state'`

- [ ] **Step 3: Write the implementation**

Create `crawler/crawler/discovery/search_state.py`:

```python
import json
import logging
import os
import time

from crawler.models import SourceCandidate

log = logging.getLogger(__name__)

_EMPTY = {"version": 1, "cursor": 0, "next_allowed_at": 0.0, "backends": {}, "cache": {}}


class SearchState:
    """Persistent JSON state for anti-throttled search: per-backend cooldown,
    keyword cache, rotation cursor, and global backoff. Mutations write atomically."""

    def __init__(self, path: str, data: dict | None = None, clock=time.time):
        self._path = path
        self._clock = clock
        self._data = data if data is not None else json.loads(json.dumps(_EMPTY))

    @classmethod
    def load(cls, path: str, clock=time.time) -> "SearchState":
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for k, default in _EMPTY.items():
                data.setdefault(k, default)
        except (OSError, ValueError) as exc:
            log.warning("search state load failed (%s); starting clean", exc)
            data = None
        return cls(path, data=data, clock=clock)

    # --- rotation cursor ---
    @property
    def cursor(self) -> int:
        return int(self._data["cursor"])

    def set_cursor(self, value: int) -> None:
        self._data["cursor"] = int(value)
        self._save()

    # --- backend health ---
    def is_healthy(self, backend: str) -> bool:
        b = self._data["backends"].get(backend)
        if not b:
            return True
        return self._clock() >= b.get("cooldown_until", 0.0)

    def record_success(self, backend: str) -> None:
        self._data["backends"][backend] = {"fails": 0, "cooldown_until": 0.0}
        self._save()

    def record_block(self, backend: str, base: float, cap: float, jitter: float, rand) -> float:
        b = self._data["backends"].get(backend) or {"fails": 0, "cooldown_until": 0.0}
        fails = int(b.get("fails", 0)) + 1
        delay = min(base * (2 ** (fails - 1)), cap) * (1 + rand() * jitter)
        self._data["backends"][backend] = {"fails": fails, "cooldown_until": self._clock() + delay}
        self._save()
        return delay

    # --- global backoff ---
    def in_global_backoff(self) -> bool:
        return self._clock() < self._data.get("next_allowed_at", 0.0)

    def set_global_backoff(self, seconds: float) -> None:
        self._data["next_allowed_at"] = self._clock() + seconds
        self._save()

    # --- keyword cache ---
    def cache_get(self, keyword: str, ttl_seconds: float) -> list[SourceCandidate] | None:
        entry = self._data["cache"].get(self._key(keyword))
        if not entry or self._clock() - entry.get("ts", 0.0) >= ttl_seconds:
            return None
        return [SourceCandidate(name=c["name"], type=c["type"], url_or_handle=c["url_or_handle"],
                                discovered_from_source_id=None,
                                discovery_note=f"ddg-cache: {self._key(keyword)}")
                for c in entry.get("candidates", [])]

    def cache_put(self, keyword: str, candidates: list[SourceCandidate]) -> None:
        self._data["cache"][self._key(keyword)] = {
            "ts": self._clock(),
            "candidates": [{"name": c.name, "type": c.type, "url_or_handle": c.url_or_handle}
                           for c in candidates],
        }
        self._save()

    @staticmethod
    def _key(keyword: str) -> str:
        return keyword.strip().casefold()

    def _save(self) -> None:
        directory = os.path.dirname(self._path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = f"{self._path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False)
        os.replace(tmp, self._path)
```

Note on cache growth: keys are normalized keywords from a fixed, curated list (~40), so the cache dict is naturally bounded — no pruning needed (YAGNI; deviates intentionally from the spec's optional prune note).

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_search_state.py`
Expected: PASS (10 passed)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/search_state.py crawler/tests/test_search_state.py
git commit -m "feat(crawler): SearchState persistent JSON for anti-throttled search"
```

---

### Task 2: Config surface for anti-throttle knobs

**Files:**
- Modify: `crawler/crawler/config.py` (`_RawSettings`, `Config`, `load_config`)
- Modify: `crawler/.env.example`
- Test: `crawler/tests/test_config.py` (append)

**Interfaces:**
- Produces on `Config`: `search_backends: list[str]`, `search_state_path: str`, `search_cache_ttl_hours: int`, `search_jitter: float`, `search_backend_cooldown_base_seconds: float`, `search_backend_cooldown_cap_seconds: float`, `search_global_backoff_hours: float`; and changes default `search_min_delay` to `45.0`.

- [ ] **Step 1: Write the failing test**

Append to `crawler/tests/test_config.py`:

```python
def test_search_antithrottle_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)      # no .env -> defaults apply
    cfg = load_config()
    assert cfg.search_backends == ["google", "startpage", "duckduckgo", "yahoo", "brave"]
    assert cfg.search_state_path == "/data/search_state.json"
    assert cfg.search_cache_ttl_hours == 168
    assert cfg.search_min_delay == 45.0
    assert cfg.search_jitter == 0.5
    assert cfg.search_backend_cooldown_base_seconds == 300.0
    assert cfg.search_backend_cooldown_cap_seconds == 21600.0
    assert cfg.search_global_backoff_hours == 6.0


def test_search_backends_env_override(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SEARCH_BACKENDS", "google, brave")
    assert load_config().search_backends == ["google", "brave"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_config.py`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'search_backends'`

- [ ] **Step 3: Implement the config changes**

In `crawler/crawler/config.py`, inside `_RawSettings`, change `search_min_delay` default and add new fields (place after the existing `search_min_delay` line):

```python
    search_min_delay: float = 45.0
    search_backends: str = "google,startpage,duckduckgo,yahoo,brave"
    search_state_path: str = "/data/search_state.json"
    search_cache_ttl_hours: int = 168
    search_jitter: float = 0.5
    search_backend_cooldown_base_seconds: float = 300.0
    search_backend_cooldown_cap_seconds: float = 21600.0
    search_global_backoff_hours: float = 6.0
```

In the `Config` dataclass, change `search_min_delay` default to `45.0` and add fields after it:

```python
    search_min_delay: float = 45.0
    search_backends: list[str] = field(default_factory=list)
    search_state_path: str = "/data/search_state.json"
    search_cache_ttl_hours: int = 168
    search_jitter: float = 0.5
    search_backend_cooldown_base_seconds: float = 300.0
    search_backend_cooldown_cap_seconds: float = 21600.0
    search_global_backoff_hours: float = 6.0
```

In `load_config()`, add to the `Config(...)` construction (after `search_min_delay=s.search_min_delay,`):

```python
        search_backends=_split_csv(s.search_backends),
        search_state_path=s.search_state_path,
        search_cache_ttl_hours=s.search_cache_ttl_hours,
        search_jitter=s.search_jitter,
        search_backend_cooldown_base_seconds=s.search_backend_cooldown_base_seconds,
        search_backend_cooldown_cap_seconds=s.search_backend_cooldown_cap_seconds,
        search_global_backoff_hours=s.search_global_backoff_hours,
```

- [ ] **Step 4: Update `crawler/.env.example`**

Replace the `SEARCH_MIN_DELAY=4` line and add the anti-throttle block. Change line:

```
SEARCH_MIN_DELAY=4
```

to:

```
# Base delay (seconds) between real search network calls; long on purpose — speed
# is not important, avoiding IP blocks is. Cache hits do not sleep.
SEARCH_MIN_DELAY=45
# --- Anti-throttle (single IP, no proxies) ---
# Backend rotation pool: one endpoint per query, round-robin. UA-relevant web
# engines only (2x Google, 2x Bing, Brave). Dropped mojeek/wikipedia/grokipedia/yandex.
SEARCH_BACKENDS=google,startpage,duckduckgo,yahoo,brave
# Persistent state file (cooldown + keyword cache + rotation cursor + global backoff).
# Put on a Docker volume so it survives container restarts.
SEARCH_STATE_PATH=/data/search_state.json
SEARCH_CACHE_TTL_HOURS=168
SEARCH_JITTER=0.5
SEARCH_BACKEND_COOLDOWN_BASE_SECONDS=300
SEARCH_BACKEND_COOLDOWN_CAP_SECONDS=21600
SEARCH_GLOBAL_BACKOFF_HOURS=6
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_config.py`
Expected: PASS (all config tests)

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/config.py crawler/.env.example crawler/tests/test_config.py
git commit -m "feat(crawler): config knobs for search anti-throttle"
```

---

### Task 3: `RotatingDdgProvider` — one backend per query + circuit-breaker

**Files:**
- Modify: `crawler/crawler/discovery/providers.py` (remove `DDG_BACKENDS` and `DuckDuckGoProvider`; add `RotatingDdgProvider`; keep `_normalize_url`, `classify_candidate`, `SearxngProvider`)
- Create: `crawler/tests/test_rotating_provider.py`
- Modify: `crawler/tests/test_providers.py` (migrate off `DuckDuckGoProvider`)
- Modify: `crawler/tests/test_provider_typeclass.py` (migrate off `DuckDuckGoProvider`)

**Interfaces:**
- Consumes: `SearchState` (Task 1); `classify_candidate`; `crawler.models.SourceCandidate`.
- Produces:
  - `RotatingDdgProvider(pool, state, results_per_keyword=7, min_delay=45.0, jitter=0.5, cooldown_base=300.0, cooldown_cap=21600.0, global_backoff_seconds=21600.0, ddgs_factory=DDGS, sleep=time.sleep, rand=random.random)`
  - `__call__(keyword: str) -> list[SourceCandidate]`

- [ ] **Step 1: Write the failing tests**

Create `crawler/tests/test_rotating_provider.py`:

```python
from crawler.discovery.providers import RotatingDdgProvider
from crawler.discovery.search_state import SearchState

POOL = ["google", "startpage", "duckduckgo", "yahoo", "brave"]


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


class RecordingDDGS:
    """Returns fixed results and records which backend was requested."""
    def __init__(self, results, log):
        self._results = results
        self._log = log

    def text(self, query, max_results=7, backend=None):
        self._log.append(backend)
        return self._results


def _provider(tmp_path, clock, factory, **over):
    st = SearchState(str(tmp_path / "state.json"), clock=clock)
    kw = dict(pool=POOL, state=st, results_per_keyword=7, min_delay=1.0, jitter=0.0,
              cooldown_base=300.0, cooldown_cap=21600.0, global_backoff_seconds=3600.0,
              ddgs_factory=factory, sleep=lambda _s: None, rand=lambda: 0.0)
    kw.update(over)
    return RotatingDdgProvider(**kw), st


def test_rotation_uses_one_backend_per_query_round_robin(tmp_path):
    log = []
    factory = lambda: RecordingDDGS([{"title": "S", "href": "https://a.example/x"}], log)
    p, _ = _provider(tmp_path, Clock(), factory)
    for _ in range(6):
        p("kw")
    assert log == ["google", "startpage", "duckduckgo", "yahoo", "brave", "google"]


def test_classifies_results_with_backend_note(tmp_path):
    log = []
    factory = lambda: RecordingDDGS([{"title": "Shop", "href": "https://a.example/x"}], log)
    p, _ = _provider(tmp_path, Clock(), factory)
    cands = p("знижки")
    assert cands[0].type == "website"
    assert cands[0].url_or_handle == "https://a.example/x"
    assert cands[0].discovery_note == "ddg:google: знижки"


def test_blocked_backend_falls_through_to_next(tmp_path):
    log = []

    class Flaky:
        def text(self, query, max_results=7, backend=None):
            log.append(backend)
            if backend == "google":
                raise RuntimeError("429")
            return [{"title": "S", "href": "https://a.example/x"}]

    p, st = _provider(tmp_path, Clock(), lambda: Flaky())
    cands = p("kw")
    assert log == ["google", "startpage"]          # google failed, startpage served
    assert cands[0].url_or_handle == "https://a.example/x"
    assert st.is_healthy("google") is False         # google cooled
    assert st.is_healthy("startpage") is True


def test_all_cooled_sets_global_backoff_and_returns_empty(tmp_path):
    class Boom:
        def text(self, query, max_results=7, backend=None):
            raise RuntimeError("banned")

    # tiny pool so two attempts exhaust it
    p, st = _provider(tmp_path, Clock(), lambda: Boom(), pool=["google", "brave"])
    assert p("kw") == []
    assert st.is_healthy("google") is False
    assert st.is_healthy("brave") is False
    assert p("kw2") == []                            # already in global backoff
    assert st.in_global_backoff() is True


def test_global_backoff_short_circuits_without_network(tmp_path):
    log = []
    factory = lambda: RecordingDDGS([{"title": "S", "href": "https://a/x"}], log)
    p, st = _provider(tmp_path, Clock(), factory)
    st.set_global_backoff(3600.0)
    assert p("kw") == []
    assert log == []                                 # no ddgs call


def test_sleep_uses_min_delay_and_jitter(tmp_path):
    slept = []
    log = []
    factory = lambda: RecordingDDGS([], log)
    p, _ = _provider(tmp_path, Clock(), factory, min_delay=10.0, jitter=0.5,
                     sleep=lambda s: slept.append(s), rand=lambda: 1.0)
    p("kw")
    assert slept == [15.0]                            # 10 * (1 + 1.0*0.5)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_rotating_provider.py`
Expected: FAIL — `ImportError: cannot import name 'RotatingDdgProvider'`

- [ ] **Step 3: Implement `RotatingDdgProvider` and remove the old provider**

In `crawler/crawler/discovery/providers.py`:

Add imports at the top (after existing imports):

```python
import random

from crawler.discovery.search_state import SearchState
```

Delete the `DDG_BACKENDS` constant (the comment block + assignment) and the entire `DuckDuckGoProvider` class. Add this class in their place:

```python
class RotatingDdgProvider:
    """Callable (keyword) -> list[SourceCandidate].

    Queries ONE backend per keyword, round-robin across `pool`, skipping backends
    in cooldown. A failing backend is cooled (exponential backoff) and the keyword
    falls through to the next healthy one. When no backend is healthy, sets a global
    backoff and returns []. Best-effort: never raises for a single keyword.
    """

    def __init__(self, pool, state: SearchState, results_per_keyword: int = 7,
                 min_delay: float = 45.0, jitter: float = 0.5, cooldown_base: float = 300.0,
                 cooldown_cap: float = 21600.0, global_backoff_seconds: float = 21600.0,
                 ddgs_factory=DDGS, sleep=time.sleep, rand=random.random):
        self._pool = list(pool)
        self._state = state
        self._n = results_per_keyword
        self._delay = min_delay
        self._jitter = jitter
        self._base = cooldown_base
        self._cap = cooldown_cap
        self._global_backoff = global_backoff_seconds
        self._ddgs_factory = ddgs_factory
        self._sleep = sleep
        self._rand = rand

    def __call__(self, keyword: str) -> list[SourceCandidate]:
        if self._state.in_global_backoff():
            return []
        for _ in range(2):  # at most two healthy backends per keyword
            backend = self._take_next_healthy()
            if backend is None:
                self._state.set_global_backoff(self._global_backoff)
                return []
            self._sleep(self._delay * (1 + self._rand() * self._jitter))
            try:
                results = self._ddgs_factory().text(keyword, max_results=self._n, backend=backend)
            except Exception as exc:  # noqa: BLE001 — search is best-effort
                log.warning("ddg backend %s failed for %r: %s", backend, keyword, exc)
                self._state.record_block(backend, self._base, self._cap, self._jitter, self._rand)
                continue
            self._state.record_success(backend)
            return self._classify(results, backend, keyword)
        return []

    def _take_next_healthy(self) -> str | None:
        n = len(self._pool)
        if n == 0:
            return None
        start = self._state.cursor % n
        for offset in range(n):
            idx = (start + offset) % n
            backend = self._pool[idx]
            if self._state.is_healthy(backend):
                self._state.set_cursor((idx + 1) % n)
                return backend
        return None

    def _classify(self, results, backend: str, keyword: str) -> list[SourceCandidate]:
        out: list[SourceCandidate] = []
        for r in results or []:
            classified = classify_candidate(r.get("href", ""))
            if classified is None:
                continue
            type_, url_or_handle = classified
            out.append(SourceCandidate(
                name=r.get("title") or url_or_handle, type=type_, url_or_handle=url_or_handle,
                discovered_from_source_id=None, discovery_note=f"ddg:{backend}: {keyword}"))
        return out
```

- [ ] **Step 4: Migrate `crawler/tests/test_providers.py`**

Replace the whole file with (keeps `_normalize_url` tests, swaps provider tests to `RotatingDdgProvider`):

```python
from crawler.discovery.providers import RotatingDdgProvider, _normalize_url
from crawler.discovery.search_state import SearchState

POOL = ["google", "startpage", "duckduckgo", "yahoo", "brave"]


class FakeDDGS:
    def __init__(self, results):
        self._results = results

    def text(self, query, max_results=7, **kwargs):
        return self._results


class CapturingDDGS:
    def __init__(self):
        self.kwargs = None

    def text(self, query, **kwargs):
        self.kwargs = kwargs
        return []


def _provider(tmp_path, factory):
    st = SearchState(str(tmp_path / "state.json"), clock=lambda: 1000.0)
    return RotatingDdgProvider(pool=POOL, state=st, results_per_keyword=3, min_delay=0,
                               jitter=0.0, ddgs_factory=factory, sleep=lambda _s: None,
                               rand=lambda: 0.0)


def test_normalize_url_strips_utm_fragment_trailing_and_lowercases_host():
    assert _normalize_url("HTTPS://Shop.Example.com/deal/?utm_source=x#frag") \
        == "https://shop.example.com/deal"
    assert _normalize_url("https://ex.com/") == "https://ex.com"


def test_normalize_url_rejects_junk():
    assert _normalize_url("not a url") is None
    assert _normalize_url("") is None


def test_provider_maps_results_to_website_candidates(tmp_path):
    p = _provider(tmp_path, lambda: FakeDDGS([
        {"title": "Кафе знижки", "href": "https://cafe.example/veterans?utm_medium=x", "body": "b"},
        {"title": "Shop", "href": "https://shop.example/", "body": "b"},
    ]))
    cands = p("знижки ветеранам")
    assert [c.url_or_handle for c in cands] == \
        ["https://cafe.example/veterans", "https://shop.example"]
    assert all(c.type == "website" for c in cands)
    assert cands[0].discovery_note == "ddg:google: знижки ветеранам"
    assert cands[0].name == "Кафе знижки"


def test_provider_queries_single_backend_from_pool(tmp_path):
    fake = CapturingDDGS()
    p = _provider(tmp_path, lambda: fake)
    p("kw")
    assert fake.kwargs.get("backend") in POOL
    assert "," not in fake.kwargs.get("backend")     # one endpoint, not the whole list


def test_provider_is_best_effort_on_error(tmp_path):
    class Boom:
        def text(self, *a, **k):
            raise RuntimeError("banned")
    p = _provider(tmp_path, lambda: Boom())
    assert p("kw") == []
```

- [ ] **Step 5: Migrate `crawler/tests/test_provider_typeclass.py`**

Replace the top import and the DDG test; leave the SearXNG test intact. New file content:

```python
import httpx

from crawler.discovery.providers import RotatingDdgProvider, SearxngProvider
from crawler.discovery.search_state import SearchState


class FakeDDGS:
    def __init__(self, results):
        self._results = results

    def text(self, query, max_results=7, **kwargs):
        return self._results


def test_ddg_provider_classifies_and_skips_junk(tmp_path):
    results = [
        {"title": "Site", "href": "https://shop.example/deal", "body": "b"},
        {"title": "TG", "href": "https://t.me/veteranychat", "body": "b"},
        {"title": "IG post", "href": "https://instagram.com/p/AbC", "body": "b"},
        {"title": "IG prof", "href": "https://instagram.com/veteranshop", "body": "b"},
    ]
    st = SearchState(str(tmp_path / "state.json"), clock=lambda: 1000.0)
    p = RotatingDdgProvider(pool=["google"], state=st, results_per_keyword=10, min_delay=0,
                            jitter=0.0, ddgs_factory=lambda: FakeDDGS(results),
                            sleep=lambda _s: None, rand=lambda: 0.0)
    cands = p("kw")
    got = {(c.type, c.url_or_handle) for c in cands}
    assert ("website", "https://shop.example/deal") in got
    assert ("telegram", "https://t.me/veteranychat") in got
    assert ("instagram", "https://instagram.com/veteranshop") in got
    assert all("instagram.com/p/" not in c.url_or_handle for c in cands)
    assert len(cands) == 3


def _searx_factory(handler):
    return lambda: httpx.Client(transport=httpx.MockTransport(handler))


def test_searxng_provider_classifies_and_skips_junk():
    def handler(req):
        return httpx.Response(200, json={"results": [
            {"url": "https://shop.example/deal", "title": "Site"},
            {"url": "https://t.me/vetchan", "title": "TG"},
            {"url": "https://facebook.com/share/x", "title": "FB share"},
        ]})
    p = SearxngProvider("http://searxng:8080", results_per_keyword=10, min_delay=0,
                        client_factory=_searx_factory(handler), sleep=lambda _s: None)
    cands = p("kw")
    got = {(c.type, c.url_or_handle) for c in cands}
    assert ("website", "https://shop.example/deal") in got
    assert ("telegram", "https://t.me/vetchan") in got
    assert all("facebook.com/share" not in c.url_or_handle for c in cands)
    assert len(cands) == 2
```

- [ ] **Step 6: Run the affected tests**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_rotating_provider.py tests/test_providers.py tests/test_provider_typeclass.py`
Expected: PASS (all)

- [ ] **Step 7: Commit**

```bash
git add crawler/crawler/discovery/providers.py crawler/tests/test_rotating_provider.py crawler/tests/test_providers.py crawler/tests/test_provider_typeclass.py
git commit -m "feat(crawler): RotatingDdgProvider with per-backend circuit-breaker"
```

---

### Task 4: `SearchCache` — TTL decorator

**Files:**
- Modify: `crawler/crawler/discovery/providers.py` (add `SearchCache`)
- Create: `crawler/tests/test_search_cache.py`

**Interfaces:**
- Consumes: `SearchState` (Task 1).
- Produces:
  - `SearchCache(inner, state, ttl_seconds)`
  - `__call__(keyword: str) -> list[SourceCandidate]`

- [ ] **Step 1: Write the failing tests**

Create `crawler/tests/test_search_cache.py`:

```python
from crawler.discovery.providers import SearchCache
from crawler.discovery.search_state import SearchState
from crawler.models import SourceCandidate


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def _cand(url="https://a.example/x"):
    return [SourceCandidate(name="S", type="website", url_or_handle=url)]


def _cache(tmp_path, clock, inner, ttl=100.0):
    st = SearchState(str(tmp_path / "state.json"), clock=clock)
    return SearchCache(inner, st, ttl_seconds=ttl), st


def test_cache_miss_calls_inner_and_stores(tmp_path):
    calls = []

    def inner(kw):
        calls.append(kw)
        return _cand()

    cache, _ = _cache(tmp_path, Clock(), inner)
    out = cache("kw")
    assert [c.url_or_handle for c in out] == ["https://a.example/x"]
    assert calls == ["kw"]


def test_cache_hit_skips_inner(tmp_path):
    calls = []

    def inner(kw):
        calls.append(kw)
        return _cand()

    cache, _ = _cache(tmp_path, Clock(), inner)
    cache("kw")
    cache("kw")                       # second call within TTL
    assert calls == ["kw"]            # inner called only once


def test_cache_expiry_requeries(tmp_path):
    calls = []
    clk = Clock(1000.0)

    def inner(kw):
        calls.append(kw)
        return _cand()

    cache, _ = _cache(tmp_path, clk, inner, ttl=100.0)
    cache("kw")
    clk.t = 1101.0
    cache("kw")
    assert calls == ["kw", "kw"]


def test_empty_result_is_cached(tmp_path):
    calls = []

    def inner(kw):
        calls.append(kw)
        return []

    cache, _ = _cache(tmp_path, Clock(), inner)
    assert cache("kw") == []
    assert cache("kw") == []
    assert calls == ["kw"]           # empty cached, inner not called again


def test_backoff_tripped_during_call_not_cached(tmp_path):
    calls = []

    def inner(kw):
        calls.append(kw)
        st.set_global_backoff(3600.0)   # inner trips global backoff, returns degraded []
        return []

    cache, st = _cache(tmp_path, Clock(), lambda kw: inner(kw))
    assert cache("kw") == []
    # not cached: next non-backoff call would re-query. Simulate backoff cleared:
    st.set_global_backoff(-3600.0)      # move next_allowed_at into the past
    cache("kw")
    assert calls == ["kw", "kw"]


def test_in_backoff_returns_empty_without_inner(tmp_path):
    calls = []
    cache, st = _cache(tmp_path, Clock(), lambda kw: calls.append(kw) or [])
    st.set_global_backoff(3600.0)
    assert cache("kw") == []
    assert calls == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_search_cache.py`
Expected: FAIL — `ImportError: cannot import name 'SearchCache'`

- [ ] **Step 3: Implement `SearchCache`**

Add to `crawler/crawler/discovery/providers.py` (after `RotatingDdgProvider`):

```python
class SearchCache:
    """TTL decorator over a search provider. Cache hit = no network, no sleep.
    Does not cache a result produced while global backoff is (or becomes) active."""

    def __init__(self, inner, state: SearchState, ttl_seconds: float):
        self._inner = inner
        self._state = state
        self._ttl = ttl_seconds

    def __call__(self, keyword: str) -> list[SourceCandidate]:
        cached = self._state.cache_get(keyword, self._ttl)
        if cached is not None:
            return cached
        if self._state.in_global_backoff():
            return []
        results = self._inner(keyword)
        if self._state.in_global_backoff():   # inner just tripped backoff — degraded empty
            return []
        self._state.cache_put(keyword, results)
        return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_search_cache.py`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/providers.py crawler/tests/test_search_cache.py
git commit -m "feat(crawler): SearchCache TTL decorator for keyword results"
```

---

### Task 5: Wire `build_search_provider`

**Files:**
- Modify: `crawler/crawler/discovery/providers.py` (`build_search_provider`)
- Modify: `crawler/tests/test_build_provider.py`

**Interfaces:**
- Consumes: `Config` fields from Task 2; `RotatingDdgProvider`, `SearchCache`, `SearchState`, `SearxngProvider`.
- Produces: `build_search_provider(config) -> Callable[[str], list[SourceCandidate]] | None` returning `SearchCache(RotatingDdgProvider(...))` for the `duckduckgo` provider.

- [ ] **Step 1: Update the failing test**

Replace `crawler/tests/test_build_provider.py` with:

```python
from types import SimpleNamespace

from crawler.discovery.providers import build_search_provider


def _cfg(tmp_path, **over):
    base = dict(
        search_providers=["duckduckgo"], search_results_per_keyword=3, search_min_delay=0,
        search_backends=["google", "brave"], search_state_path=str(tmp_path / "state.json"),
        search_cache_ttl_hours=168, search_jitter=0.5,
        search_backend_cooldown_base_seconds=300.0, search_backend_cooldown_cap_seconds=21600.0,
        search_global_backoff_hours=6.0, searxng_url="http://searxng:8080",
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_build_returns_callable_for_known_provider(tmp_path):
    p = build_search_provider(_cfg(tmp_path))
    assert callable(p)


def test_build_returns_none_when_no_known_providers(tmp_path):
    assert build_search_provider(_cfg(tmp_path, search_providers=[])) is None
    assert build_search_provider(_cfg(tmp_path, search_providers=["unknown"])) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_build_provider.py`
Expected: FAIL — `AttributeError`/`TypeError` from the old `build_search_provider` not knowing the new fields, or a construction error.

- [ ] **Step 3: Implement the wiring**

Replace the body of `build_search_provider` in `crawler/crawler/discovery/providers.py` with:

```python
def build_search_provider(config):
    """Combine enabled search providers into one callable, or None."""
    providers = []
    state = None
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
            providers.append(SearchCache(rotating, state,
                                         config.search_cache_ttl_hours * 3600))
        elif name == "searxng":
            providers.append(SearxngProvider(
                base_url=config.searxng_url,
                results_per_keyword=config.search_results_per_keyword,
                min_delay=config.search_min_delay))
        else:
            log.warning("unknown search provider %r, ignoring", name)
    if not providers:
        return None

    def combined(keyword):
        out = []
        for p in providers:
            out.extend(p(keyword))
        return out

    return combined
```

- [ ] **Step 4: Run the full crawler suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — whole suite green (previously 139; now higher with new tests). No network access.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/providers.py crawler/tests/test_build_provider.py
git commit -m "feat(crawler): wire SearchCache(RotatingDdgProvider) in build_search_provider"
```

---

### Task 6: Docker state volume + docs

**Files:**
- Modify: `docker-compose.yml` (crawler service volume + top-level `volumes`)
- Modify: `README-docker.md` (note the state volume)
- Modify: `RUN.md` (note the search state file)

**Interfaces:** none (infra + docs only).

- [ ] **Step 1: Add the crawler state volume to `docker-compose.yml`**

In the `crawler:` service, add a `volumes:` block (place it just before the `environment:` key, after `depends_on:`):

```yaml
    volumes:
      - ubd-crawler-state:/data
```

In the `crawler:` `environment:` block, add:

```yaml
      SEARCH_STATE_PATH: /data/search_state.json
```

In the top-level `volumes:` section at the bottom, add `ubd-crawler-state:` beside `ubd-db-data:`:

```yaml
volumes:
  ubd-db-data:
  ubd-crawler-state:
```

- [ ] **Step 2: Verify compose config parses**

Run: `docker compose config >/dev/null && echo OK`
Expected: `OK` (no YAML/compose errors). If Docker is unavailable in the environment, skip with a note and rely on review.

- [ ] **Step 3: Document the state volume**

In `README-docker.md`, add a short paragraph near the crawler section:

```markdown
The crawler persists anti-throttle state (per-backend cooldown, keyword cache,
rotation cursor, global backoff) to `/data/search_state.json` on the
`ubd-crawler-state` volume, so blocked-backend cooldowns and cached keyword
results survive container restarts. Override the path with `SEARCH_STATE_PATH`.
```

In `RUN.md`, add one line to the active-search section:

```markdown
- Активний пошук ходить по **одному** бекенду на запит із пулу `SEARCH_BACKENDS`
  (`google,startpage,duckduckgo,yahoo,brave`), з ротацією, per-backend cooldown,
  кешем keyword'ів (`SEARCH_CACHE_TTL_HOURS`) і глобальним backoff — стан у
  `SEARCH_STATE_PATH`. Мета — не блокуватись по IP; швидкість вторинна.
```

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml README-docker.md RUN.md
git commit -m "chore(docker): persist crawler search state on a volume + docs"
```

---

## Self-Review

**1. Spec coverage:**
- Backend rotation pool (one endpoint/query, round-robin) → Task 3 (`RotatingDdgProvider._take_next_healthy`), pool from config Task 2.
- Per-backend circuit-breaker (exp backoff, cap, reset on success) → Task 1 (`record_block`/`record_success`) + Task 3.
- Persistent keyword cache with TTL, empty cached, casefold key → Task 1 (`cache_*`) + Task 4 (`SearchCache`).
- Single atomic JSON state file, load-clean-on-corrupt, flush on mutation only → Task 1.
- Pacing (min_delay + jitter, only on network) → Task 3 (`test_sleep_uses_min_delay_and_jitter`), config Task 2.
- Global backoff (all cooled → skip network this + future runs) → Task 3 + Task 1 (`set/in_global_backoff`).
- Remove `DDG_BACKENDS` / all-at-once → Task 3.
- Config surface + `.env.example` + raised `search_min_delay` → Task 2.
- Docker persistence + docs → Task 6.
- SearXNG untouched → verified (Tasks 3/5 leave `SearxngProvider` and its branch intact).
- Out of scope (freshness/promotion/seed/proxies/region) → none added. ✔

**2. Placeholder scan:** No TBD/TODO; every code step shows full code. ✔

**3. Type consistency:** `RotatingDdgProvider(pool, state, ...)`, `SearchCache(inner, state, ttl_seconds)`, `SearchState.load(path, clock)`, `record_block(backend, base, cap, jitter, rand)`, `cache_get(keyword, ttl_seconds)` — names/signatures identical across Tasks 1, 3, 4, 5 and their tests. `discovery_note` formats: live `ddg:{backend}: {keyword}`, cached `ddg-cache: {keyword}` — used consistently. ✔

**Deviations from spec (intentional):** (a) global-backoff "abort run" is realized as the provider returning `[]` cheaply (self-managed via `SearchState`) instead of raising `AllBackendsCooling` to a wrapper — same no-network outcome, keeps `ActiveDiscovery` untouched; (b) no cache pruning — keyword set is bounded so the cache can't grow unbounded.
