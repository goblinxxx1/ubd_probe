# Feed cursor consume-then-commit — DEFERRED sibling plan

**Status:** DEFERRED (analysis only — no code change). Sibling of the merged
`2026-08-10-search-harvest-completion.md` track.

## Context

The search-harvest-completion track (merged `5a20228`) fixed the SEVERE orphaning: a
DDG-searched candidate that didn't fit the fetch budget was cached "fresh" for the full
168h TTL and never harvested — permanently lost (the dental-clinic symptom). Fixed via
drain-first + a per-phrase `harvested` flag + `stop_index`.

The audit also flagged the discovery **feeds** (P4/P5): `brand_feed`, `osm_feed`,
`aggregator_feed`, and the `site_query` planner advance their cursor when they PRODUCE
candidates (`(cursor + per_pass) % size`), before harvest, in `run_active`.

## Why this is DEFERRED, not fixed now

1. **Feeds recycle by design — no permanent loss.** The feed cursor is a *scan position*
   over a domain list, wrapping modulo `size`. A candidate not harvested this pass is
   re-scanned on the next full cycle (brand: ~3 passes; osm/aggregator: longer but
   bounded). This is *bounded deferral*, not the 168h permanent loss the search path had.
2. **Lossy window→candidate mapping.** A window of `per_pass` domains yields FEWER
   candidates (brand with no resolved domain, `known`/host-skip). The cursor tracks
   *domains scanned*, not *candidates produced*. A naive "advance by candidates consumed"
   mismatches units and would RE-SCAN skipped/domainless entries — degrading coverage.
3. **Correct fix is a real refactor.** Doing it right means: tag each feed candidate with
   its window position, and after harvest advance the cursor past every window slot that
   either produced no candidate (done) or produced a consumed candidate (done), stopping
   at the first slot whose candidate was produced-but-not-consumed. That touches the
   `candidates()`/cursor interface of 3 feed classes + the site planner + `run_active` +
   wiring + tests. Higher risk, low severity — warrants checkpointed review, not an
   autonomous overnight change.

## Correct design (for when this is picked up)

Reuse the search track's primitive (`origin_key` + harvest `stop_index`):

1. Each feed tags its candidates: `origin_key = "feed:brand"` / `"feed:osm"` /
   `"feed:aggregator"` / `"feed:site"`, and records the window slot each candidate came
   from (e.g. `origin_slot: int`).
2. `candidates()` STOPS auto-advancing the cursor; add `commit(consumed_slots: set[int])`.
3. `run_active`, after `harvest(...) -> stop_index`, for each feed computes the window
   slots whose candidates are at positions `< stop_index` (consumed) PLUS the slots that
   produced no candidate (done), and calls `feed.commit(...)` to advance the cursor past
   the leading run of done slots — stopping at the first not-done slot.
4. Tests per feed: a window where harvest cuts mid-window leaves the cursor at the first
   unconsumed slot; a fully-consumed window advances by the whole window; a
   domainless-only window advances fully.

## Severity / priority

LOW. The severe, symptom-causing orphaning (search) is fixed and deployed. Feeds recycle,
so this is a coverage-latency tightening, not a data-loss fix. Pick up under review when
convenient.
