# Crawler active/passive split — Implementation Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development or executing-plans. Steps use `- [ ]`.

**Goal:** Active discovery runs first every loop and maximizes offers within its budget while never crawling published sources; passive source-crawl runs rarely (96h) and handles freshness/expiry.

**Architecture:** Split `Runner.run()` into `run_active()` + `run_passive()`; `run()` orchestrates (active first; passive only when a persisted `PassiveSchedule` is due). Active host-skip of source hosts becomes unconditional; the `site:` approved-partner arm is removed.

**Tech Stack:** Python, crawler pytest.

## Global Constraints
- crawler-only; backend/admin/extraction/attribution unchanged; `docker-entrypoint.sh` unchanged.
- Backward compat: `Runner(...)` without a `passive_schedule` must still run active+passive on `run()` (existing tests).
- TDD test-first; run `./.venv/Scripts/python.exe -m pytest -q` from `crawler/`.
- Deploy env: `PASSIVE_INTERVAL_SECONDS=345600` (96h), `ACTIVE_FETCH_BUDGET=150`, `CRAWL_INTERVAL_SECONDS=7200`.

---

### Task 1: PassiveSchedule (persisted due/mark)

**Files:** Create `crawler/crawler/schedule.py`; Test `crawler/tests/test_schedule.py`.

**Interfaces:** `PassiveSchedule(path, interval_seconds, now=time.time)` → `.due() -> bool`, `.mark() -> None`.

- [ ] **Step 1: failing test**
```python
import json
from crawler.schedule import PassiveSchedule

def test_due_when_no_state_file(tmp_path):
    s = PassiveSchedule(str(tmp_path/"p.json"), 100, now=lambda: 1000.0)
    assert s.due() is True

def test_not_due_within_interval_then_due_after(tmp_path):
    t = {"v": 1000.0}
    s = PassiveSchedule(str(tmp_path/"p.json"), 100, now=lambda: t["v"])
    s.mark()
    t["v"] = 1050.0
    assert s.due() is False
    t["v"] = 1101.0
    assert s.due() is True

def test_mark_persists_across_instances(tmp_path):
    p = str(tmp_path/"p.json")
    PassiveSchedule(p, 100, now=lambda: 500.0).mark()
    assert PassiveSchedule(p, 100, now=lambda: 550.0).due() is False

def test_corrupt_file_is_due(tmp_path):
    p = tmp_path/"p.json"; p.write_text("{bad", encoding="utf-8")
    assert PassiveSchedule(str(p), 100, now=lambda: 1.0).due() is True
```

- [ ] **Step 2: run → fail** (`pytest tests/test_schedule.py`).

- [ ] **Step 3: implement**
```python
import json
import time


class PassiveSchedule:
    """Persisted cadence gate for the passive pass: due() until interval elapses
    since the last mark(); state is a tiny JSON file so it survives restarts."""

    def __init__(self, path, interval_seconds, now=time.time):
        self._path = path
        self._interval = interval_seconds
        self._now = now

    def due(self) -> bool:
        last = self._load()
        return last is None or (self._now() - last) >= self._interval

    def mark(self) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump({"last_passive_at": self._now()}, fh)
        except OSError:
            pass  # best-effort; a missed mark just means passive runs again next loop

    def _load(self):
        try:
            with open(self._path, encoding="utf-8") as fh:
                v = json.load(fh).get("last_passive_at")
                return float(v) if v is not None else None
        except (OSError, ValueError):
            return None
```

- [ ] **Step 4: run → pass.**

- [ ] **Step 5: commit** `git commit -m "feat(crawler): PassiveSchedule — persisted cadence gate for the passive pass"`

---

### Task 2: Split Runner.run() into run_active() + run_passive() + orchestration

**Files:** Modify `crawler/crawler/runner.py`; Test `crawler/tests/test_runner.py`.

**Interfaces:**
- `Runner(..., passive_schedule=None, now=time.time)` (new kwargs).
- `run_active() -> dict`, `run_passive() -> dict`, `run() -> dict` (orchestrates).

- [ ] **Step 1: failing tests** (add to test_runner.py; reuse its existing fakes)
```python
def test_run_active_does_not_crawl_sources(...):
    # a website source present; run_active must NOT call get_crawl_state/fetch for it
    # (assert the passive per-source path is untouched: e.g., crawl_state getter not called)
    ...
    summary = runner.run_active()
    assert api.crawl_state_calls == 0

def test_run_passive_crawls_sources_and_expires(...):
    summary = runner.run_passive()
    assert api.crawl_state_calls >= 1
    assert api.expire_called is True

def test_run_active_first_then_passive_when_due(...):
    order = []
    # monkeypatch/instrument run_active & run_passive to append to order
    runner.run()
    assert order == ["active", "passive"]

def test_passive_skipped_when_not_due(...):
    sched = PassiveSchedule(path, 10_000, now=lambda: T)  # marked, not due
    sched.mark()
    runner = Runner(..., passive_schedule=sched)
    runner.run()
    assert api.crawl_state_calls == 0   # passive did not run

def test_run_without_schedule_runs_both(...):  # backward compat
    runner = Runner(...)  # passive_schedule=None
    runner.run()
    assert api.crawl_state_calls >= 1 and api.expire_called is True
```
(Adapt fakes: ensure the FakeApi counts `get_crawl_state` calls and records `expire_stale`.)

- [ ] **Step 2: run → fail.**

- [ ] **Step 3: implement** — refactor `runner.py`:
  - Add ctor kwargs `passive_schedule=None`, `now=time.time`; store them.
  - Extract current per-source loop into `run_passive()`:
    ```python
    def run_passive(self) -> dict:
        cats = CategoryIndex(self._api.list_target_categories(), self._api.list_offer_categories())
        sources = self._api.list_sources(is_active=True)
        known = {normalize_ref(s["type"], s["url_or_handle"]) for s in sources}
        summary = {"sources": 0, "offers": 0, "suggestions": 0, "expired": 0, "errors": 0}
        for source in sources:
            summary["sources"] += 1
            try:
                self._crawl_source(source, cats, known, summary)
            except Exception as exc:  # noqa: BLE001
                summary["errors"] += 1
                log.warning("source #%s failed: %s", source.get("id"), exc)
        try:
            result = self._api.expire_stale(self._freshness_ttl_days)
            summary["expired"] = result.get("expired", 0)
        except Exception as exc:  # noqa: BLE001
            summary["errors"] += 1
            log.warning("expire-stale failed: %s", exc)
        return summary
    ```
  - Extract the active-discovery block into `run_active()`:
    ```python
    def run_active(self) -> dict:
        cats = CategoryIndex(self._api.list_target_categories(), self._api.list_offer_categories())
        sources = self._api.list_sources(is_active=True)
        known = {normalize_ref(s["type"], s["url_or_handle"]) for s in sources}
        summary = {"sources": 0, "offers": 0, "suggestions": 0, "expired": 0, "errors": 0}
        if self._harvester is None:
            return summary
        try:
            # Active never crawls a host that is already an active source (passive owns it).
            # Unconditional (not gated on domain-rating): guarantees published sources are skipped.
            known_hosts = {_host(s["url_or_handle"]) for s in sources if s["type"] == "website"}
            feeds = []
            if self._domain_feed is not None:
                feeds.append(self._domain_feed.candidates(known_hosts))
            if self._search_pass is not None:
                feeds.append(self._search_pass.run(known))
            if self._brand_feed is not None:
                feeds.append(self._brand_feed.candidates(known))
            if self._osm_feed is not None:
                feeds.append(self._osm_feed.candidates(known))
            if self._aggregator_feed is not None:
                feeds.append(self._aggregator_feed.candidates(known))
            candidates = [c for group in zip_longest(*feeds) for c in group if c is not None]
            # site: only for productive-but-not-yet-approved domains (registry.top excludes
            # known_hosts). No approved-partner arm — passive re-confirms approved sources.
            if (self._site_planner is not None and self._site_state is not None
                    and self._discovery is not None and self._domain_registry is not None):
                cur = self._site_state.site_cursor
                reg = self._domain_registry.top(self._site_query_budget, known_hosts)
                site_queries, new_cur = self._site_planner.next_batch(reg, self._site_query_budget, cur)
                if site_queries:
                    site_cands = self._discovery.run(site_queries, known)
                    for c in site_cands:
                        c.bypass_host_skip = True
                    candidates += site_cands
                    self._site_state.set_site_cursor(new_cur)
            if candidates:
                self._harvester.harvest(candidates, cats, known, summary, known_hosts=known_hosts)
        except Exception as exc:  # noqa: BLE001
            summary["errors"] += 1
            log.warning("active discovery / brand-feed harvest failed: %s", exc)
        finally:
            if self._domain_registry is not None:
                try:
                    self._domain_registry.prune(self._evict_min, self._evict_ttl)
                    self._domain_registry.save()
                except Exception as exc:  # noqa: BLE001
                    log.warning("domain registry persist failed: %s", exc)
        return summary
    ```
  - New `run()`:
    ```python
    def run(self) -> dict:
        summary = self.run_active()
        if self._passive_schedule is None or self._passive_schedule.due():
            p = self.run_passive()
            for k in summary:
                summary[k] = summary.get(k, 0) + p.get(k, 0)
            if self._passive_schedule is not None:
                self._passive_schedule.mark()
        log.info("crawl summary: %s", summary)
        return summary
    ```
  - Remove `approved_cursor` usage from the site: block (kept in `SearchState` for compat; just no longer read/advanced here).
  - Keep `_crawl_source`, `_crawl_website_deep`, `_process_page`, `_fetch_for` unchanged.

- [ ] **Step 4: run tests** — new + existing `test_runner.py`/`test_runner_discovery.py` green (backward compat via schedule=None).

- [ ] **Step 5: commit** `git commit -m "feat(crawler): split run into run_active/run_passive; active skips published sources; site: registry-only"`

---

### Task 3: Config knobs + wiring

**Files:** Modify `crawler/crawler/config.py`, `crawler/crawler/wiring.py`; Test `crawler/tests/test_config.py`, `crawler/tests/test_wiring.py`.

**Interfaces:** config gains `passive_interval_seconds` (default 172800) and `passive_state_path` (default "/data/passive_state.json"); wiring builds `PassiveSchedule` and passes it + `now` to `Runner`.

- [ ] **Step 1: failing tests**
```python
# test_config.py
def test_passive_defaults():
    s = _RawSettings()
    assert s.passive_interval_seconds == 172800
    assert s.passive_state_path == "/data/passive_state.json"
```
```python
# test_wiring.py — Runner receives a PassiveSchedule
def test_build_runner_wires_passive_schedule(monkeypatch, tmp_path):
    ...
    runner = w.build_runner(cfg)
    from crawler.schedule import PassiveSchedule
    assert isinstance(runner._passive_schedule, PassiveSchedule)
```
(Follow the existing `_RawSettings`/`Config`/`build_runner` patterns; set `passive_state_path` to a tmp path in the wiring test if it constructs the schedule eagerly.)

- [ ] **Step 2: run → fail.**

- [ ] **Step 3: implement**
  - `config.py`: add both fields to the raw settings class(es) and the `Config` dataclass + `load_config` passthrough (mirror `freshness_ttl_days`).
  - `wiring.py`: after building the runner deps, construct `PassiveSchedule(config.passive_state_path, config.passive_interval_seconds)` and pass `passive_schedule=` (and `now` default) into `Runner(...)`.

- [ ] **Step 4: run tests** — config + wiring green.

- [ ] **Step 5: full suite** `./.venv/Scripts/python.exe -m pytest -q` — all green.

- [ ] **Step 6: commit** `git commit -m "feat(crawler): config passive_interval/passive_state_path + wire PassiveSchedule into Runner"`

---

## Self-Review notes
- Spec §"Розділення" → Task 2; §"Оркестрація" → Task 2 (run) + Task 1 (schedule); §"Активний оминає" → Task 2 (unconditional known_hosts + site: registry-only); §"Конфіг" → Task 3.
- Backward compat: `run()` with `passive_schedule=None` runs both (Task 2 test).
- No placeholders; code shown per step.
- Names consistent: `run_active`/`run_passive`/`PassiveSchedule`/`passive_schedule`/`passive_interval_seconds`/`passive_state_path`.
- Deploy: canonical crawler rebuild + env (PASSIVE_INTERVAL_SECONDS=345600, ACTIVE_FETCH_BUDGET=150, CRAWL_INTERVAL_SECONDS=7200); update memory.
