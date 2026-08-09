# Backoff-aware crawler scheduler — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the crawler's fixed `sleep 7200s` loop with an adaptive, backoff-aware scheduler that searches DDG near-continuously while it is available and relegates the DDG-independent passive pass to backoff windows — maximizing discovery of new offers per unit time.

**Architecture:** A small pure decision function `step()` picks which pass to run and how long to sleep from the search state's global-backoff clock; `run_loop()` drives it forever, reloading state each iteration. The existing `Runner.run_active()` / `Runner.run_passive()` are called directly — the Runner is NOT modified. Entrypoint dispatches to a new `crawler loop` command when `CRAWL_INTERVAL_SECONDS > 0`.

**Tech Stack:** Python 3.12, pydantic-settings (existing config), pytest. No new dependencies.

## Global Constraints

- No new third-party dependencies.
- One-shot `crawler run` (`CRAWL_INTERVAL_SECONDS=0`) behavior must stay byte-unchanged (CI/tests/demo path).
- `Runner`, `run_active`, `run_passive`, and search/anti-throttle internals are OUT OF SCOPE — do not modify them.
- All new time/sleep/clock dependencies must be injectable for unit tests (follow the existing `now=time.time` / `clock=time.time` pattern).
- Config fields are declared in THREE places in `crawler/crawler/config.py`: `_RawSettings`, `Config`, and the `load_config()` mapping.
- Host test runner (Windows): `crawler/.venv/Scripts/python.exe -m pytest`. Run from the `crawler/` directory.

---

### Task 1: `SearchState.seconds_until_allowed()` accessor

**Files:**
- Modify: `crawler/crawler/discovery/search_state.py` (after `in_global_backoff`, ~line 97)
- Test: `crawler/tests/test_search_state.py` (append)

**Interfaces:**
- Consumes: existing `SearchState._data["next_allowed_at"]`, `self._clock`.
- Produces: `SearchState.seconds_until_allowed() -> float` (clamped ≥ 0.0).

- [ ] **Step 1: Write the failing test**

Append to `crawler/tests/test_search_state.py`:

```python
def test_seconds_until_allowed_future_then_past():
    clk = [1000.0]
    st = SearchState("x", data={"next_allowed_at": 1300.0}, clock=lambda: clk[0])
    assert st.seconds_until_allowed() == 300.0
    clk[0] = 1400.0
    assert st.seconds_until_allowed() == 0.0   # clamped, never negative
```

(If `SearchState` is not already imported at the top of the file, add `from crawler.discovery.search_state import SearchState`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `crawler/.venv/Scripts/python.exe -m pytest tests/test_search_state.py::test_seconds_until_allowed_future_then_past -v`
Expected: FAIL with `AttributeError: 'SearchState' object has no attribute 'seconds_until_allowed'`

- [ ] **Step 3: Write minimal implementation**

In `crawler/crawler/discovery/search_state.py`, directly below the `in_global_backoff` method:

```python
    def seconds_until_allowed(self) -> float:
        return max(0.0, self._data.get("next_allowed_at", 0.0) - self._clock())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `crawler/.venv/Scripts/python.exe -m pytest tests/test_search_state.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/search_state.py crawler/tests/test_search_state.py
git commit -m "feat(crawler): SearchState.seconds_until_allowed() accessor"
```

---

### Task 2: `PassiveSchedule.overdue(hard_factor)` accessor

**Files:**
- Modify: `crawler/crawler/schedule.py`
- Test: `crawler/tests/test_schedule.py` (append)

**Interfaces:**
- Consumes: existing `PassiveSchedule._load()`, `self._now`, `self._interval`.
- Produces: `PassiveSchedule.overdue(hard_factor: float) -> bool`. Never-marked (`last is None`) → `False` (a fresh schedule is NOT hard-overdue; backoff windows pick it up).

- [ ] **Step 1: Write the failing test**

Append to `crawler/tests/test_schedule.py`:

```python
def test_overdue_hard_factor(tmp_path):
    from crawler.schedule import PassiveSchedule
    p = tmp_path / "passive.json"
    clk = [1000.0]
    sched = PassiveSchedule(str(p), interval_seconds=100, now=lambda: clk[0])
    assert sched.overdue(3.0) is False      # never marked -> not hard-overdue
    sched.mark()                            # last_passive_at = 1000
    clk[0] = 1000 + 299                     # 299 < 3*100
    assert sched.overdue(3.0) is False
    clk[0] = 1000 + 300                     # 300 == 3*100
    assert sched.overdue(3.0) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `crawler/.venv/Scripts/python.exe -m pytest tests/test_schedule.py::test_overdue_hard_factor -v`
Expected: FAIL with `AttributeError: 'PassiveSchedule' object has no attribute 'overdue'`

- [ ] **Step 3: Write minimal implementation**

In `crawler/crawler/schedule.py`, add a method to `PassiveSchedule` (below `due`):

```python
    def overdue(self, hard_factor: float) -> bool:
        last = self._load()
        return last is not None and (self._now() - last) >= self._interval * hard_factor
```

- [ ] **Step 4: Run test to verify it passes**

Run: `crawler/.venv/Scripts/python.exe -m pytest tests/test_schedule.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/schedule.py crawler/tests/test_schedule.py
git commit -m "feat(crawler): PassiveSchedule.overdue(hard_factor) freshness safety net"
```

---

### Task 3: Scheduler config fields

**Files:**
- Modify: `crawler/crawler/config.py` (`_RawSettings`, `Config`, `load_config`)
- Test: `crawler/tests/test_config.py` (append)

**Interfaces:**
- Produces: `Config.active_loop_delay_seconds: float = 60.0`, `Config.backoff_max_sleep_seconds: float = 1800.0`, `Config.passive_hard_overdue_factor: float = 3.0`.

- [ ] **Step 1: Write the failing test**

Append to `crawler/tests/test_config.py`:

```python
def test_scheduler_config_defaults():
    from crawler.config import load_config
    c = load_config()
    assert c.active_loop_delay_seconds == 60.0
    assert c.backoff_max_sleep_seconds == 1800.0
    assert c.passive_hard_overdue_factor == 3.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `crawler/.venv/Scripts/python.exe -m pytest tests/test_config.py::test_scheduler_config_defaults -v`
Expected: FAIL with `AttributeError: 'Config' object has no attribute 'active_loop_delay_seconds'`

- [ ] **Step 3: Write minimal implementation**

In `crawler/crawler/config.py`, add the three fields in ALL THREE places.

In `class _RawSettings(BaseSettings)` (near the passive fields):

```python
    active_loop_delay_seconds: float = 60.0
    backoff_max_sleep_seconds: float = 1800.0
    passive_hard_overdue_factor: float = 3.0
```

In `class Config` (the dataclass, same names/types/defaults):

```python
    active_loop_delay_seconds: float = 60.0
    backoff_max_sleep_seconds: float = 1800.0
    passive_hard_overdue_factor: float = 3.0
```

In the `return Config(...)` mapping inside `load_config()`:

```python
        active_loop_delay_seconds=s.active_loop_delay_seconds,
        backoff_max_sleep_seconds=s.backoff_max_sleep_seconds,
        passive_hard_overdue_factor=s.passive_hard_overdue_factor,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `crawler/.venv/Scripts/python.exe -m pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/config.py crawler/tests/test_config.py
git commit -m "feat(crawler): scheduler config (active_loop_delay/backoff_max_sleep/hard_overdue)"
```

---

### Task 4: Scheduler `step()` + `run_loop()`

**Files:**
- Create: `crawler/crawler/scheduler.py`
- Test: `crawler/tests/test_scheduler.py`

**Interfaces:**
- Consumes: `runner.run_active()`, `runner.run_passive()`; `state.in_global_backoff()`, `state.seconds_until_allowed()` (Task 1); `passive_schedule.due()/mark()/overdue()` (Task 2).
- Produces:
  - `scheduler.MIN_ACTIVE_DELAY: float = 5.0`
  - `scheduler.step(runner, state, passive_schedule, *, active_delay, backoff_max_sleep, hard_factor) -> float`
  - `scheduler.run_loop(runner, state_loader, passive_schedule, *, active_delay, backoff_max_sleep, hard_factor, sleep=time.sleep, iterations=None) -> None`

- [ ] **Step 1: Write the failing tests**

Create `crawler/tests/test_scheduler.py`:

```python
from crawler.scheduler import step, run_loop, MIN_ACTIVE_DELAY


class _Runner:
    def __init__(self):
        self.calls = []
    def run_active(self):
        self.calls.append("active")
    def run_passive(self):
        self.calls.append("passive")


class _State:
    def __init__(self, backed_off, secs=0.0):
        self._b, self._s = backed_off, secs
    def in_global_backoff(self):
        return self._b
    def seconds_until_allowed(self):
        return self._s


class _Passive:
    def __init__(self, due=False, overdue=False):
        self._due, self._overdue, self.marked = due, overdue, 0
    def due(self):
        return self._due
    def overdue(self, f):
        return self._overdue
    def mark(self):
        self.marked += 1


def _kw(**over):
    base = dict(active_delay=60, backoff_max_sleep=1800, hard_factor=3)
    base.update(over)
    return base


def test_not_backed_off_runs_active():
    r = _Runner()
    assert step(r, _State(False), _Passive(), **_kw()) == 60
    assert r.calls == ["active"]


def test_active_delay_floor():
    r = _Runner()
    assert step(r, _State(False), _Passive(), **_kw(active_delay=0)) == MIN_ACTIVE_DELAY


def test_backed_off_passive_due_runs_passive_sleeps_to_T():
    r, p = _Runner(), _Passive(due=True)
    assert step(r, _State(True, secs=500), p, **_kw()) == 500
    assert r.calls == ["passive"] and p.marked == 1


def test_backed_off_passive_not_due_sleeps_capped_no_pass():
    r = _Runner()
    assert step(r, _State(True, secs=9999), _Passive(due=False), **_kw()) == 1800
    assert r.calls == []


def test_hard_overdue_runs_passive_in_active_window():
    r, p = _Runner(), _Passive(overdue=True)
    assert step(r, _State(False), p, **_kw()) == 60
    assert r.calls == ["passive"] and p.marked == 1


def test_state_none_runs_active():
    r = _Runner()
    step(r, None, _Passive(), **_kw())
    assert r.calls == ["active"]


def test_run_loop_bounded_iterations():
    r, slept = _Runner(), []
    states = iter([_State(True, 100), _State(False)])
    run_loop(r, lambda: next(states), _Passive(due=True),
             sleep=slept.append, iterations=2, **_kw())
    assert r.calls == ["passive", "active"] and slept == [100, 60]


def test_run_loop_survives_pass_error():
    class Boom:
        def run_active(self):
            raise RuntimeError("boom")
        def run_passive(self):
            pass
    slept = []
    run_loop(Boom(), lambda: _State(False), _Passive(),
             sleep=slept.append, iterations=1, **_kw())
    assert slept == [60]   # error swallowed, slept active_delay
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `crawler/.venv/Scripts/python.exe -m pytest tests/test_scheduler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'crawler.scheduler'`

- [ ] **Step 3: Write minimal implementation**

Create `crawler/crawler/scheduler.py`:

```python
import logging
import time

log = logging.getLogger(__name__)

MIN_ACTIVE_DELAY = 5.0   # floor so an instantly-returning active pass can't busy-loop


def step(runner, state, passive_schedule, *, active_delay, backoff_max_sleep, hard_factor):
    """One scheduling decision: run exactly one pass, return the sleep (seconds).

    - Global backoff active: DDG is unusable, so run the DDG-independent passive pass
      (only if its cadence is due) and sleep until the backoff lifts (capped).
    - Otherwise: run the DDG active pass (new-offer discovery). Passive runs in
      DDG-available time ONLY as a freshness safety net when it is hard-overdue.
    """
    if state is not None and state.in_global_backoff():
        if passive_schedule is None or passive_schedule.due():
            runner.run_passive()
            if passive_schedule is not None:
                passive_schedule.mark()
        return min(state.seconds_until_allowed(), backoff_max_sleep)
    if passive_schedule is not None and passive_schedule.overdue(hard_factor):
        runner.run_passive()
        passive_schedule.mark()
        return max(active_delay, MIN_ACTIVE_DELAY)
    runner.run_active()
    return max(active_delay, MIN_ACTIVE_DELAY)


def run_loop(runner, state_loader, passive_schedule, *, active_delay, backoff_max_sleep,
             hard_factor, sleep=time.sleep, iterations=None):
    """Drive step() forever (or `iterations` times in tests), reloading search state each
    pass so a freshly-persisted next_allowed_at is always seen. A failing pass is logged
    and skipped — it must never kill the loop."""
    n = 0
    while iterations is None or n < iterations:
        try:
            state = state_loader()
            secs = step(runner, state, passive_schedule, active_delay=active_delay,
                        backoff_max_sleep=backoff_max_sleep, hard_factor=hard_factor)
        except Exception as exc:  # noqa: BLE001 — a bad pass must not kill the loop
            log.warning("scheduler iteration failed: %s", exc)
            secs = max(active_delay, MIN_ACTIVE_DELAY)
        log.info("scheduler: sleeping %.0fs", secs)
        sleep(secs)
        n += 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `crawler/.venv/Scripts/python.exe -m pytest tests/test_scheduler.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/scheduler.py crawler/tests/test_scheduler.py
git commit -m "feat(crawler): adaptive backoff-aware scheduler (step + run_loop)"
```

---

### Task 5: CLI `loop` command + entrypoint dispatch + docs

**Files:**
- Modify: `crawler/crawler/__main__.py`
- Modify: `crawler/docker-entrypoint.sh`
- Modify: `crawler/.env.example`
- Modify: `RUN.md`
- Test: `crawler/tests/test_main.py` (create)

**Interfaces:**
- Consumes: `build_runner` (wiring), `SearchState.load`, `PassiveSchedule`, `run_loop` (Task 4), `load_config`.
- Produces: `crawler loop` CLI command that builds the runner, a disk-reloading `state_loader`, and drives `run_loop`.

- [ ] **Step 1: Write the failing test**

Create `crawler/tests/test_main.py`:

```python
from crawler import __main__ as m


def test_loop_command_dispatches_run_loop(monkeypatch):
    called = {}
    monkeypatch.setattr(m, "build_runner", lambda cfg: "RUNNER")
    monkeypatch.setattr(m, "run_loop", lambda *a, **k: called.setdefault("ran", (a, k)))
    rc = m.main(["loop"])
    assert rc == 0
    assert "ran" in called


def test_run_command_still_one_shot(monkeypatch):
    seen = {}
    class _R:
        def run(self):
            seen["run"] = True
            return {"offers": 0}
    monkeypatch.setattr(m, "build_runner", lambda cfg: _R())
    assert m.main(["run"]) == 0
    assert seen.get("run") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `crawler/.venv/Scripts/python.exe -m pytest tests/test_main.py -v`
Expected: FAIL — `test_loop_command_dispatches_run_loop` errors because `run_loop`/`loop` choice do not exist yet (argparse rejects `"loop"`).

- [ ] **Step 3: Write minimal implementation**

Replace the imports + body of `crawler/crawler/__main__.py` with:

```python
import argparse
import logging
import sys

from crawler.config import load_config
from crawler.discovery.search_state import SearchState
from crawler.schedule import PassiveSchedule
from crawler.scheduler import run_loop
from crawler.wiring import build_runner


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="crawler")
    parser.add_argument("command", choices=["run", "loop"], help="what to do")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("crawler")

    if args.command == "run":
        config = load_config()
        runner = build_runner(config)
        summary = runner.run()
        log.info("done: %s", summary)
        return 0

    if args.command == "loop":
        config = load_config()
        runner = build_runner(config)
        passive = PassiveSchedule(config.passive_state_path, config.passive_interval_seconds)

        def _load_state():
            return SearchState.load(config.search_state_path) if config.active_discovery else None

        log.info("scheduler: adaptive loop — active while DDG free, passive in backoff windows")
        run_loop(runner, _load_state, passive,
                 active_delay=config.active_loop_delay_seconds,
                 backoff_max_sleep=config.backoff_max_sleep_seconds,
                 hard_factor=config.passive_hard_overdue_factor)
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `crawler/.venv/Scripts/python.exe -m pytest tests/test_main.py -v`
Expected: PASS

- [ ] **Step 5: Update the Docker entrypoint**

Replace `crawler/docker-entrypoint.sh` with (the loop now lives in Python, not the shell):

```sh
#!/bin/sh
set -e

INTERVAL="${CRAWL_INTERVAL_SECONDS:-0}"
if [ "$INTERVAL" -gt 0 ] 2>/dev/null; then
  echo "[crawler] adaptive scheduler loop (CRAWL_INTERVAL_SECONDS=$INTERVAL enables loop mode)"
  exec python -m crawler loop
else
  echo "[crawler] single one-shot pass"
  exec python -m crawler run
fi
```

- [ ] **Step 6: Document the new knobs**

Append to `crawler/.env.example` (after the passive/active-split block):

```dotenv
# --- Adaptive scheduler (loop mode; CRAWL_INTERVAL_SECONDS>0 in the root .env enables it) ---
# Base delay between active passes while DDG is available. Small = DDG is searched
# near-continuously; the internal anti-throttle (SEARCH_MIN_DELAY, per-backend cooldown)
# paces the actual requests. This is NOT the old fixed 2h interval.
ACTIVE_LOOP_DELAY_SECONDS=60
# Cap on a single sleep during global backoff, so a long backoff re-checks periodically.
BACKOFF_MAX_SLEEP_SECONDS=1800
# Freshness safety net: run the passive pass once in DDG-available time if it is overdue
# by this many times its interval (covers the rare case where DDG never backs off).
PASSIVE_HARD_OVERDUE_FACTOR=3
```

In `RUN.md`, replace the `### На розкладі (щоб ходив сам)` Docker note so it reads:

```markdown
### На розкладі (щоб ходив сам)

```bash
# Docker: адаптивний цикл (CRAWL_INTERVAL_SECONDS>0 у .env вмикає loop-режим)
#   .env:  CRAWL_INTERVAL_SECONDS=7200
docker compose --profile crawler up -d crawler
```

Loop-режим (`crawler loop`) сам керує ритмом: поки DDG доступний — активний пошук
майже безперервно (пауза `ACTIVE_LOOP_DELAY_SECONDS`, темп тримає внутрішній
анти-throttle); під глобальним DDG-бекофом — спить рівно до `next_allowed_at`
(кап `BACKOFF_MAX_SLEEP_SECONDS`) і в цей час робить лише DDG-незалежний пасив.
`CRAWL_INTERVAL_SECONDS>0` лише вмикає цикл; тривалості задають три змінні вище.
```

- [ ] **Step 7: Run the full crawler test suite**

Run: `crawler/.venv/Scripts/python.exe -m pytest -q`
Expected: PASS (all existing + new tests green)

- [ ] **Step 8: Commit**

```bash
git add crawler/crawler/__main__.py crawler/docker-entrypoint.sh crawler/.env.example RUN.md crawler/tests/test_main.py
git commit -m "feat(crawler): 'loop' command + adaptive scheduler entrypoint + docs"
```

---

### Task 6: Build image + live smoke test

**Files:** none (integration).

- [ ] **Step 1: Rebuild the crawler image**

Run: `docker compose --profile crawler build crawler`
Expected: build succeeds.

- [ ] **Step 2: Recreate the crawler with the new entrypoint**

Run: `docker compose --profile crawler up -d crawler`
Expected: container `Up`.

- [ ] **Step 3: Verify the adaptive loop is live**

Run: `docker logs --tail 20 ubd_probe-crawler-1`
Expected: shows `[crawler] adaptive scheduler loop ...` and a `scheduler: adaptive loop ...` line. Under the current global backoff it then logs `crawl summary` for a passive (no-op with `sources=0`) pass and `scheduler: sleeping <=1800s`. After `next_allowed_at` it switches to active passes.

- [ ] **Step 4: Confirm one-shot path is unbroken**

Run: `docker compose --profile crawler run --rm crawler`
Expected: a single `done: {...}` summary, process exits (no loop).

- [ ] **Step 5: Commit (only if any fix was needed in steps 1–4)**

```bash
git add -A
git commit -m "chore(crawler): scheduler smoke-test fixes"
```

---

## Self-review notes

- **Spec coverage:** adaptive loop (Task 4/5), sleep-to-`next_allowed_at` (Task 1+4), passive-in-backoff + due-gate + hard-overdue net (Task 2+4), config knobs (Task 3), CLI `loop` + entrypoint (Task 5), one-shot unchanged (Task 5 test + Task 6 step 4), tests (every task). All present.
- **No Runner changes:** `run_active`/`run_passive` reused as-is — out-of-scope constraint honored.
- **Type consistency:** `step`/`run_loop` keyword args (`active_delay`, `backoff_max_sleep`, `hard_factor`) identical across scheduler code, tests, and the `__main__` call site; config field names identical across `_RawSettings`/`Config`/`load_config`/`.env.example`.
