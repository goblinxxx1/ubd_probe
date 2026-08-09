# Backoff-aware crawler scheduler — design

**Date:** 2026-08-09
**Status:** approved (pending spec review)

## North star

**Everything the scheduler does serves one goal: maximize DuckDuckGo (DDG)
discovery of NEW, previously-unknown offers over time.** Re-walking already-known
domains/sources is explicitly *not* a goal — it yields no new offers. Any work
that does not increase new-offer discovery is either dropped or relegated to time
DDG cannot use anyway.

## Problem

The crawler loop is a fixed shell sleep:

```sh
while true; do python -m crawler run; sleep "$CRAWL_INTERVAL_SECONDS"; done   # 7200s
```

Two losses, both measured against the north star:

1. **Wasted DDG-available time (the big one).** An active pass runs ~1 block
   (`SEARCH_BLOCK_SIZE=15`) at `SEARCH_MIN_DELAY` (~20 s) ≈ **5 min of search**,
   then sleeps **2 h**. When DDG is *not* throttled we still use it ~**4 %** of
   the time — the fixed 2 h sleep is an artificial ceiling far below DDG's
   sustainable rate. New offers we could have found are simply not searched for.
2. **Misaligned resume after backoff.** When DDG throttles, the crawler sets a
   global backoff (`next_allowed_at`, e.g. 6 h). The fixed 2 h grid means search
   can resume anywhere up to a full interval *after* the backoff actually lifts —
   more idle DDG time.

Meanwhile the passive pass (freshness re-confirm of approved sources) is
DDG-independent and brings **no new sources**, yet if it runs during
DDG-available time it *steals* minutes from search.

## Design

Replace the dumb fixed sleep with a small **backoff-aware adaptive scheduler**
(Python, testable). The scheduler reads the search state's global-backoff clock
and decides, each iteration, *what to run* and *how long to sleep*:

```
loop:
    state = SearchState.load(SEARCH_STATE_PATH)
    if state.in_global_backoff():
        # DDG is unusable right now — do the DDG-independent passive pass here so
        # it never competes with search, then wait out the backoff precisely.
        # Gate on the passive cadence so a single long backoff (re-checked every
        # BACKOFF_MAX_SLEEP_SECONDS) doesn't re-crawl approved sources repeatedly.
        if passive_schedule is None or passive_schedule.due():
            runner.run_passive(); passive_schedule.mark()
        sleep(min(seconds_until_allowed, BACKOFF_MAX_SLEEP_SECONDS))
    elif passive_schedule is not None and passive_schedule.overdue(hard_factor):
        # Freshness safety net: if DDG has NOT backed off for a long time, passive
        # would otherwise never get a window. Once it is hard-overdue, run it once
        # even in DDG-available time (rare; prevents approved-source freshness starving).
        runner.run_passive(); passive_schedule.mark()
        sleep(ACTIVE_LOOP_DELAY_SECONDS)
    else:
        # DDG is available — spend it on new-offer discovery. Internal anti-throttle
        # (SEARCH_MIN_DELAY, per-backend cooldown, block size) paces the requests.
        runner.run_active()
        sleep(ACTIVE_LOOP_DELAY_SECONDS)   # small, keeps search flowing
```

Consequences:

- **DDG duty cycle rises from ~4 % toward the anti-throttle ceiling** → more new
  offers per unit time. We do not hammer DDG: `SEARCH_MIN_DELAY` and per-backend
  cooldowns still pace every request; the *internal* anti-throttle — not an
  arbitrary 2 h outer sleep — becomes the rate limiter and self-tunes to the
  sustainable rate.
- **Zero wasted minutes after backoff:** the loop wakes at `next_allowed_at`
  (capped by `BACKOFF_MAX_SLEEP_SECONDS` so a long backoff re-checks periodically)
  and searches immediately.
- **Passive runs only while active cannot** (inside the backoff window). It is
  not a priority and brings no new sources; it merely fills otherwise-dead time
  and never delays search. With `sources = 0` it is a near-instant no-op.

Expected trade-off (stated honestly): searching more often means the anti-throttle
will hit global backoff *more frequently*. That is fine and intended — it is the
mechanism finding the sustainable ceiling instead of us guessing a 2 h floor.

## Components / changes

1. **`crawler/scheduler.py` (new).** `run_loop(runner, state_loader, sleep, clock,
   active_delay, backoff_max_sleep)` — the loop above. All side-effecting deps
   (sleep, clock, state loader, runner) injected for unit testing. No global state.
2. **`SearchState.seconds_until_allowed() -> float` (new accessor).** Returns
   `max(0.0, next_allowed_at - clock())`. Pairs with existing `in_global_backoff()`
   ([search_state.py:96](../../../crawler/crawler/discovery/search_state.py)).
3. **`Runner` — call `run_active()` / `run_passive()` directly.** They already exist
   ([runner.py:79](../../../crawler/crawler/runner.py), `:145`). The scheduler chooses
   which to call based on backoff, replacing `run()`'s unconditional "active-first +
   passive-if-due" orchestration for the *loop* path. `run()` itself stays for the
   one-shot path (see below).
4. **CLI + entrypoint dispatch.** Add `python -m crawler loop`. `docker-entrypoint.sh`
   calls it when `CRAWL_INTERVAL_SECONDS > 0`; the one-shot `crawler run` path is
   unchanged (`CRAWL_INTERVAL_SECONDS = 0` → single full `run()`, for CI/tests/demo).
5. **`PassiveSchedule.overdue(hard_factor) -> bool` (new accessor).** True when the
   time since last `mark()` exceeds `hard_factor ×` the passive cadence — the freshness
   safety net for when DDG rarely backs off. Complements the existing `due()`/`mark()`.

## Config (crawler/.env)

| Var | Meaning | Default |
|---|---|---|
| `CRAWL_INTERVAL_SECONDS` | `>0` enables the loop (loop vs one-shot switch) | 0 (compose sets it) |
| `ACTIVE_LOOP_DELAY_SECONDS` | base delay between active passes when DDG is available; floor prevents tight-spin when a pass returns instantly (all phrases cache-fresh) | 60 |
| `BACKOFF_MAX_SLEEP_SECONDS` | cap on a single backoff sleep so long backoffs re-check/re-run passive periodically | 1800 |

## Edge cases / correctness

- **One-shot unchanged.** `crawler run` still does one full `run()` (active +
  passive-if-due). Only the loop path uses the scheduler. Back-compat preserved.
- **Self-correcting transitions.** If an active pass *triggers* a fresh backoff
  mid-loop, the next iteration observes `in_global_backoff()` and switches to
  passive + sleep-to-`T`. When the backoff clears, the next iteration runs active.
- **No tight spin.** `ACTIVE_LOOP_DELAY_SECONDS` has a small floor so an
  instantly-returning active pass (no due phrases) cannot busy-loop the CPU.
- **`sources = 0`.** `run_passive()` is a fast no-op; the backoff window simply
  sleeps. Correct with zero approved sources (the current state).
- **Passive cadence vs backoff frequency.** Passive is gated by `due()` inside the
  backoff window, so a long backoff (re-checked every `BACKOFF_MAX_SLEEP_SECONDS`)
  does not re-crawl approved sources on every wake. Conversely, if DDG rarely backs
  off, `overdue(hard_factor)` lets passive run once in DDG-available time so approved
  sources are not starved of re-confirmation and wrongly expired.
- **State reload each iteration** so an out-of-band change to `next_allowed_at`
  (written by the active pass's provider calls) is always seen fresh.

## Testing

Unit tests (inject fake `clock`, `sleep`-recorder, stub `runner`, in-memory `SearchState`):

- **Backed off →** scheduler calls `run_passive()` (not `run_active`) and sleeps
  `min(seconds_until_allowed, BACKOFF_MAX_SLEEP_SECONDS)`.
- **Not backed off →** scheduler calls `run_active()` and sleeps
  `ACTIVE_LOOP_DELAY_SECONDS`.
- **Passive gating →** backed off + passive not due → `run_passive` NOT called;
  backed off + passive due → called once then `mark()`. Not backed off + passive
  hard-overdue → `run_passive` called once even with DDG available.
- **Transition →** backed-off iteration followed by cleared-backoff iteration runs
  passive then active, in that order.
- **`seconds_until_allowed()`** returns clamped remaining seconds; `0.0` when past.
- **Back-compat →** one-shot `run()` behavior byte-unchanged (existing runner tests
  still green; `run_active` / `run_passive` untouched internally).

## Out of scope (explicit)

- No change to what an active pass *contains* (feeds, `site:`, harvester) or to
  the anti-throttle internals — only *when/how often* passes run.
- No change-detection work for discovered offers (backend `create_offer` branch 3b
  stays skip+bump). Composition-change detection remains an approved-source concern.
- No promotion of known-domain re-walking to a scheduled priority.
