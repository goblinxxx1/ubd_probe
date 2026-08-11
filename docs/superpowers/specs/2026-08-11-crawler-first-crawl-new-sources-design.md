# Prompt first-crawl of never-crawled sources — design

**Status:** APPROVED (design). Track: crawler + backend. Branch: `feat/first-crawl-new-sources`.

## Problem

A newly-approved website source waits up to a full passive cycle (96h) for its first crawl,
so its already-present discount never becomes an offer until then. Confirmed live:
`edclinic.com.ua` is an active source (#15, 36h old) with a visible "−15% for UBD", but has
**zero** offers because it has **never been crawled** — `source_crawl_state` has no row for it.

Root cause: active discovery **host-skips** approved sources (by design — passive owns them),
and the passive pass runs only every 96h; it last ran before `edclinic` was added and is not
due for ~50h. The extractor works fine — a read-only probe on `edclinic`'s page emits
`percent/15` under the production gate — the only missing step is the crawl. This affects **all
~27 currently-seeded sources** (none has a crawl-state row yet).

Lowering the passive interval is a blunt fix (×4 fetch/queue/active-preemption cost across all
sources, and still waits a full interval). The targeted fix: crawl **never-crawled** sources
promptly, independent of the global passive cadence.

## Goal

Within one active pass (minutes–hours, and **during DDG backoff** too), first-crawl up to a
bounded number of active website sources that have no crawl-state row, via the existing passive
deep-walk path, so their offers reach moderation promptly. Self-draining: once crawled, a source
gets a crawl-state row and drops out. No change to the passive cadence, active discovery, or the
DDG anti-throttle machinery.

## Design

### Components and boundaries

1. **Backend — `GET /api/internal/sources/uncrawled?limit=N`** (read-only). Returns active
   `type='website'` sources with **no** `source_crawl_state` row (LEFT JOIN … IS NULL),
   `ORDER BY id` (stable — oldest first), `LIMIT N`. Same row shape as `list_sources` items
   (`id`, `type`, `name`, `url_or_handle`) so the crawler can feed them straight into its
   existing crawl path. No writes.

2. **Crawler `ApiClient.list_uncrawled_sources(limit) -> list[dict]`** — GET the endpoint.

3. **Crawler `Runner.run_first_crawl(budget) -> dict`** — fetch up to `budget` uncrawled
   sources and crawl each via the **existing** `_crawl_source` (website → `_crawl_website_deep`
   walker path), which submits offers and, on success, calls `set_crawl_state` (→ the source
   gets a crawl-state row and drops out of "uncrawled" next pass). Per-source isolation like
   `run_passive`. Returns the standard summary dict.

4. **Wiring into `run_active`** — call `run_first_crawl(config.first_crawl_budget)` as its own
   best-effort block inside `run_active`, **unconditionally** (not gated by `ddg_allowed`),
   because it is DDG-independent — so it fires on every active pass, including the
   backoff passes (`ddg_allowed=False`). Its summary folds into the pass summary.

5. **Config** — `first_crawl_budget: int = 10` (tunable knob). `0` disables the trigger.

### Data flow

`run_active` → `run_first_crawl(N)` → `list_uncrawled_sources(N)` → for each source
`_crawl_source(...)` → deep-walk fetch → extractor → `create_offer` (existing dedup) → on
success `set_crawl_state` marks it crawled. Next pass the endpoint no longer returns it.

### Safety guards (from the design review of "won't break anything")

- **No retry loop on failure.** If a source's crawl raises before `_crawl_source` marks it,
  `run_first_crawl` catches it (per-source), increments `errors`, **and marks the source
  attempted** via `set_crawl_state(source_id, None)` — so a chronically-failing site drops out
  of "uncrawled" instead of consuming the budget every pass. `None` is safe here: a never-
  crawled source had no `last_seen_key` to lose, and the next 96h passive cycle re-crawls it
  fresh. The mark-attempted call happens **only on the exception path** — on success
  `_crawl_source` already wrote the real `last_seen_key`, so it is never overwritten with `None`.
- **Bounded work.** `budget` caps sources per pass (default 10). During a backlog (27 now)
  passes are heavier (~5 min) for a few passes until drained, then the endpoint returns empty
  and the step is a cheap no-op. The scheduler sleeps *after* a pass, so heavy passes simply
  lower the loop cadence during a backlog — self-limiting, not harmful.
- **No duplicate offers.** Reuses `create_offer` (content_hash / article_url_canonical / source
  dedup). A later passive re-crawl of the same source just bumps `last_seen`.
- **No active-discovery interference.** First-crawl targets already-approved (host-skipped)
  sources; they are never added to the active candidate pool.
- **Politeness unchanged.** Same `_crawl_website_deep` per-domain rate limit (3s) and
  `domain_page_cap` (10) as passive.
- **No file/state race.** Crawl-state goes through the backend API, not the crawler JSON files.
- **`expire_stale` untouched.** The 30-day expiry sweep stays in `run_passive`.

### Scope

Website sources only (the demonstrated gap; the deep-walk path is website-specific). Non-website
new sources (telegram/IG/FB) still get their first crawl via the normal passive cycle — a
possible follow-up, deliberately out of scope here.

## Testing

- **Backend:** `uncrawled` endpoint returns active website sources with no crawl-state row,
  respects `limit`, `ORDER BY id`, and **excludes** crawled / inactive / non-website sources.
- **Crawler:** `list_uncrawled_sources(limit)` calls the endpoint with the limit.
- **Runner:** `run_first_crawl(budget)` crawls up to `budget` uncrawled sources through
  `_crawl_source` (offers submitted); a source whose crawl raises is marked attempted
  (`set_crawl_state(id, None)`) and does not stop the others; `budget=0` / empty list is a no-op.
- **Runner integration:** `run_active` invokes `run_first_crawl` regardless of `ddg_allowed`
  (fires during backoff), best-effort (its failure does not crash the pass).

## Out of scope (YAGNI)

Passive-cadence change; crawl-on-approval push from backend; non-website first-crawl; any change
to DDG anti-throttle/backoff, dedup, or the extractor.
