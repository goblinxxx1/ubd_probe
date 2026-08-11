# DDG-independent discovery survives global backoff — design

**Status:** APPROVED (design). Track: crawler. Branch: `feat/ddg-independent-during-backoff`.

## Problem

The adaptive scheduler skips **all** of `run_active()` while DDG is in global backoff
(`scheduler.py:17-22`: `if state.in_global_backoff(): run_passive(); return`). But
`run_active()` does far more than DDG search — most of it is DDG-**independent**:

- the **drain** of cached-but-unharvested search candidates (`SearchPass.run` step 1,
  `state.unharvested(ttl)`) — pure local cache re-surfacing, **zero network**;
- the **four DDG-independent feeds** — `domain_feed`, `brand_feed`, `osm_feed`,
  `aggregator_feed` — built specifically as a DDG-independent domain inflow (tracks 26/28);
- `harvest()` + `_mark_consumed_search_phrases`.

Only two legs actually touch DDG: the due-walk **search** (`SearchPass.run` step 2) and the
`site:` query arm.

**Consequence (observed live 2026-08-11):** DDG sat in a ~5h global backoff, so `run_active`
never ran, so the drain never fired — 13 dentistry orphan-cache entries (manually reset to
`harvested=False` earlier this session) stayed unconsumed for the full backoff, and the
DDG-independent feeds were starved too. Nothing is *lost* (cursor is frozen, drain re-tries),
but all active discovery is stalled behind a gate that most of it does not depend on.

## Goal

While DDG is in global backoff, `run_active()` still performs **everything DDG-independent**
(drain + all 4 feeds + harvest + mark-consumed); it skips **only** the DDG legs (due-walk
search + `site:`). When backoff lifts, the DDG legs resume automatically. No change to the
anti-throttle machinery, the backoff itself, or the passive cadence.

## Design (approach A: `ddg_allowed` flag + split `SearchPass`)

Rejected alternatives: (B) Runner reads `state.in_global_backoff()` internally — couples the
runner to search-state, hides the decision, harder to test; (C) a separate
`run_ddg_independent()` that duplicates feed logic — drift/duplication risk.

### Components and boundaries

1. **`SearchPass`** — extract the drain into a reusable method; keep `run()` otherwise as-is:
   - `drain() -> list[SourceCandidate]` — current step 1 (`unharvested(ttl)`), gated on
     `ttl > 0`; **zero network**; does NOT touch `grid_cursor`.
   - `run(known)` — **unchanged** behaviour and signature; its step-1 block now simply calls
     `drain()` (the due-walk search stays inline in `run()`). A standalone `search()` is
     deliberately NOT added — it would be dead code (nothing calls the search leg alone), and
     keeping the search inside `run()` makes the non-backoff path byte-identical: `run_active`
     appends one combined feed entry, same `zip_longest` interleave as today.

2. **`Runner.run_active(ddg_allowed: bool = True)`**:
   - **always:** the four feeds (`domain`/`brand`/`osm`/`aggregator`) + `harvest(...) ->
     stop_index` + `_mark_consumed_search_phrases`, and the search-pass contribution.
   - **search-pass contribution:** `run(known)` (full drain+due-walk search) when
     `ddg_allowed`, else `drain()` only.
   - **only when `ddg_allowed`:** the `site:` query arm.
   - Default `True` = current behaviour (back-compat for `run()` / tests / one-shot).

3. **`scheduler.step`** — the global-backoff branch calls `run_active(ddg_allowed=False)`
   (still also `run_passive()` if its cadence is due, then sleeps until backoff lifts,
   capped). The other two branches are unchanged: "passive hard-overdue" runs passive; the
   normal branch runs `run_active(ddg_allowed=True)`.

### Data flow (unchanged)

Both drain- and search-produced candidates carry `origin_key`; they are concatenated into the
one `candidates` list, interleaved with feed candidates (`zip_longest`), and passed to
`harvest(...) -> stop_index`. `_mark_consumed_search_phrases` marks a phrase `harvested=True`
only when **all** its candidates sit at positions `< stop_index`. So under backoff the drain
steadily works down the unharvested backlog and marks consumed phrases, **without advancing
the search cursor** (no successful search happened) — exactly the desired decoupling.

### Error handling (unchanged)

`run_active` keeps its `try/except` (discovery must not crash the pass); feeds stay
best-effort. The split adds no new failure surface — `drain()` is pure local I/O over
already-loaded state.

## Testing (TDD)

- `SearchPass.drain()` returns unharvested candidates and makes **no** provider call
  (`ttl<=0` => empty); `run(known)` keeps its existing due-walk/cursor behaviour (covered by
  existing tests) and still drains-then-searches.
- `Runner.run_active(ddg_allowed=False)`: `search` and the `site:` arm are **not** invoked;
  `drain` + all four feeds + `harvest` + `mark_consumed` **are**.
- `Runner.run_active()` default (`ddg_allowed=True`): unchanged full behaviour.
- `scheduler.step` under global backoff calls `run_active(ddg_allowed=False)` (and passive
  when due); not-in-backoff calls `run_active(ddg_allowed=True)`.

## Out of scope (YAGNI)

DDG anti-throttle / backoff logic itself; the passive cadence; the feed-cursor consume-commit
refactor (separate DEFERRED plan); the environmental DDG degradation (not our target).
