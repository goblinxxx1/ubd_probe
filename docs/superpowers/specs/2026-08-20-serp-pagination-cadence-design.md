# Crawler: SERP pagination + query cadence — Track 3

**Date:** 2026-08-20
**Status:** Design approved
**Program:** deepen active discovery. Builds on the query grid + due-walking
([[ubd-crawler-news-exclusion]] B3c) and the just-built query-miner v2
([[ubd-crawler-query-miner-v2]]). Research: [[ubd-crawler-active-discovery-backlog]].

## Problem

Active search fetches only the **top-N results of page 1** for every grid phrase and
never goes deeper: `providers.py:103` calls `DDGS().text(keyword, max_results=N, ...)`
(SearXNG: `params={"q":kw,"format":"json"}`), both page 1. Each revisit of a phrase
re-fetches the same top-N. So discovery breadth grows (more phrases via v2) but **depth
per phrase is capped at page 1** — businesses ranked on SERP pages 2–3 for a productive
query are never found.

The machinery is page-agnostic end to end: providers are `__call__(keyword)`, and the
cache / freshness / rotation are keyed by the phrase string only
(`SearchState.cache`, `is_fresh(phrase)`, `grid_cursor`).

## Goal

Let a **productive** phrase page deeper on successive visits (page 2, 3, …) while a
**dry** phrase stops early — so budget flows to queries that actually surface new
businesses, not to SERP sludge. Candidates still go to the existing harvest → moderation
path; nothing about ranking or the audit gate changes.

**Non-goals:** changing the grid composition (that is v2), the harvest/extractor, or the
moderation queue. Retrieval depth only.

## Key decisions (approved)

- **Yield signal = search-time new-candidate count.** After fetching `(phrase, page)`,
  count the *distinct new* candidates (classified, not already in `known`). This is
  exactly what `ActiveDiscovery.run` already computes when it dedups against `known`/`seen`
  (`active.py:31`). No downstream harvest-yield threading (avoids the search→harvest lag).
- **Stop rule = two consecutive dry pages.** One dry page is **not** enough to stop — we
  probe one more page and only stop if it too is dry ("go one past empty, confirm nothing,
  then stop"). Guards against a single thin SERP page ending a still-productive query.
- **`page_cap = 3`** (config default) — upper safety bound on depth per phrase. The
  two-dry rule already trims dead phrases; the cap only bounds rare very-productive ones.
- **Approach A — page-aware through the existing chain** (reuses backoff/health/cache),
  not a separate deep-scan pass (which would duplicate rotation/backoff).

Grounding: `ddgs 9.15.0` `.text()` accepts `page: int = 1` ("The page of results to
return") — verified by static inspection; SearXNG accepts `pageno`.

## Design (Approach A)

Five bounded units, each independently testable.

### 1. Providers — a `page` parameter

- `DdgTextProvider.__call__(keyword, page=1)` → `ddgs.text(keyword, max_results=N,
  backend=..., page=page)`.
- `SearxngProvider.__call__(keyword, page=1)` → `params["pageno"] = page`.
- `SearchCache.__call__(keyword, page=1)` → cache keyed by `(keyword, page)`.
- `page=1` default ⇒ byte-identical to today for any caller that omits it.

### 2. `SearchState` — page cursor + cadence policy (pure, unit-tested)

- **Cache/freshness key** becomes `_key(keyword, page) = "{phrase}#p{page}"`. Back-compat:
  a legacy key without `#p…` is treated as page 1 (so the existing on-disk cache is not
  invalidated). `is_fresh`, `cache_get`, `cache_put`, `unharvested` take a page.
- **New map** `phrase_pages: {phrase_key: {"page": int, "dry": int}}` (added to `_EMPTY`
  with `setdefault` load-migration, like the existing cursors). `current_page(phrase)`
  returns the stored page (default 1).
- **`record_page_result(phrase, page, new_count, page_cap)`** — the whole policy in one
  place:
  - `new_count > 0`  → `dry=0`; `next = page+1` if `page < page_cap` else `1` (reset/re-scan
    at the ceiling).
  - `new_count == 0` → `dry += 1`; if `dry < 2` → `next = page+1` (bounded by `page_cap`:
    at the cap, stop instead of probing past it); if `dry >= 2` → **stop**: `next = 1`,
    `dry = 0`. On stop the phrase stays freshness-fresh, so the due-walk revisits it from
    page 1 only after the TTL.

### 3. `ActiveDiscovery.run(keywords, known, pages=None)`

Thread the page: `self._provider(kw, (pages or {}).get(kw, 1))`. `pages=None` ⇒ every kw
at page 1 (back-compat). Dedup against `known`/`seen` unchanged.

### 4. `search_pass` — orchestration

- `_collect_due` picks due phrases where freshness is checked at each phrase's
  **current page** (`is_fresh(phrase, current_page(phrase))`); the batch carries each
  phrase's page (a `{phrase: page}` map).
- After the providers run, group `out` by `origin_key` (= phrase, already set from the
  provider's `discovery_note`), count distinct new refs (not in `known`) per phrase, and
  call `state.record_page_result(phrase, page, new_count, page_cap)` — **only on success**
  (mirrors the existing advance-on-success; a throttled pass re-scans the same
  `(phrase, page)` next time).
- `origin_key` is set to the full `(phrase, page)` cache key so `mark_harvested` marks the
  exact page entry (verify the `mark_harvested` caller during implementation and adjust the
  key it receives).

### 5. `page_cap` config

`active_search_page_cap: int = 3` (both settings blocks + the mapping), threaded to
`search_pass`.

## Interaction with v2 / the grid

The due-walk touches `block_size` distinct phrases per pass, each at its current page.
A productive phrase climbs +1 page per full grid rotation (slow depth on the large v2
grid); `page_cap` bounds it. `set_grid`'s modulo-wrap and the phrase-keyed cache stay
correct across grid changes (v2's constraints, already recorded). No change to
`grid_cursor` semantics.

## Impact / blast radius

- **Byte-eq when OFF:** all new params default to page 1 / `pages=None`; a phrase only
  advances when a real new-candidate signal arrives, so with mocked/empty search the
  behavior and existing tests are unchanged (verify).
- **Cache migration:** legacy phrase-only keys read as page 1 — no wipe. New writes use the
  `#p` key.
- **Providers:** DDG `page=` and SearXNG `pageno=` are additive kwargs; SearXNG stays an
  independent provider (survives DDG backoff).
- **UKR-only:** no lexical content; retrieval plumbing only.

## Rollout

Docker-only, crawler rebuild. No backend change, no migration (state is the crawler's
local JSON; the new `phrase_pages` key self-seeds via `setdefault`).

## Tasks (SDD)

1. **Providers** — `page` param on `DdgTextProvider`, `SearxngProvider`, `SearchCache`;
   ddgs `page=` / searxng `pageno=`; tests (page arg forwarded, cache keyed by page).
2. **SearchState** — `_key(keyword, page)` + legacy back-compat; `phrase_pages` map;
   `current_page`; `record_page_result` policy; page-aware `is_fresh/cache_get/cache_put/
   unharvested`; tests for every policy branch + legacy-key read.
3. **ActiveDiscovery.run** — `pages` param threaded to the provider; test.
4. **search_pass** — due-walk at current page, per-phrase new-count from `origin_key`,
   `record_page_result` on success, full `(phrase,page)` origin/harvest key; tests incl. an
   e2e mock provider paginating 1→2→stop.
5. **config** — `active_search_page_cap=3`; wiring; test. Verify byte-eq OFF + full suite.
