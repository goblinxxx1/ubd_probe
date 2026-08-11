# Feed cursor consume-then-commit — DEFERRED sibling plan

**Status:** DEFERRED (analysis only — no code change). Sibling of the merged
`2026-08-10-search-harvest-completion.md` track.

## Context

The search-harvest-completion track (merged `5a20228`) fixed the SEVERE orphaning: a
DDG-searched candidate that didn't fit the fetch budget was cached "fresh" for the full
168h TTL and never harvested — permanently lost (the dental-clinic symptom). Fixed via
drain-first + a per-phrase `harvested` flag + `stop_index`.

The audit also flagged three discovery **feeds** (P4/P5): `brand_feed`, `osm_feed`, and
`aggregator_feed`. Each advances a **coverage cursor** — a scan position over a domain
list — when it PRODUCES candidates (`(cursor + per_pass) % size`), before harvest, inside
`candidates()`, so the window moves past this pass's domains regardless of whether harvest
consumed them.

**Two other emitters look similar but are NOT in this family — do not "fix" them:**
- `site_query` planner: its `site_cursor` is a **term-phase** cursor
  (`(cursor + 1) % len(terms)`, 7 intent forms), not a scan position over candidates. The
  domains it queries are re-selected fresh each pass from `registry.top()` (`runner.py`),
  so no domain is held by the cursor and none can be orphaned. Rotating the term every pass
  is the *intended* behaviour (phrasing diversity for the same domains) — gating it on
  harvest would be a regression. Excluded.
- `domain_feed`: has **no cursor at all** — it re-selects `registry.top(per_pass, …)` by
  score each pass (`domain_feed.py`), with a revisit-cooldown for rotation. Nothing to
  commit. Excluded.

## Why this is DEFERRED, not fixed now

1. **Feeds recycle by design — bounded deferral, no permanent loss.** The feed cursor is a
   *scan position* over a domain list, wrapping modulo `size`. A candidate not harvested
   this pass is re-scanned on the next full cycle: **brand ~3 passes** (48 seeds ÷ 20),
   **aggregator up to ~25 passes** (cap 500 ÷ 20), **osm up to ~75 passes** (cap
   `osm_feed_max_domains` = **1500** ÷ 20 — the *upper bound*; the real cycle is the number
   of domains actually enumerated, which is smaller and, with OSM currently returning 406,
   effectively frozen at whatever last succeeded). This is *bounded deferral*, not the 168h
   permanent loss the search path had. It's further softened by `run_active` interleaving
   all feeds round-robin (`zip_longest`) before harvest, so the fetch budget is spread
   across feeds each pass and every feed gets partial coverage every pass — no single feed's
   tail is systematically starved.

   **Adjacent note (aggregator, currently inert):** `AggregatorDomainStore.add` evicts the
   oldest hosts from the front on cap overflow AND does not adjust the cursor for the shift
   (`aggregator_feed.py`) — in principle a host could be skipped/evicted before harvest.
   But the only writer of that store (`harvest.py` `_process_page`, gated on
   `is_blocked_host(ctx.host)`) is **unreachable** under the current blocklist=no-fetch gate
   (`harvest.py:61-62` skips blocklisted candidates before fetch), so the store never grows,
   eviction never fires, and there is no loss today. Flag this only if the aggregator ingest
   path is ever re-enabled; it is orthogonal to the cursor-consume-commit refactor either
   way.
2. **Lossy window→candidate mapping.** A window of `per_pass` domains yields FEWER
   candidates (brand with no resolved domain, `known`/host-skip). The cursor tracks
   *domains scanned*, not *candidates produced*. A naive "advance by candidates consumed"
   mismatches units and would RE-SCAN skipped/domainless entries — degrading coverage.
3. **Correct fix is a real refactor.** Doing it right means: tag each feed candidate with
   its window position, and after harvest advance the cursor past every window slot that
   either produced no candidate (done) or produced a consumed candidate (done), stopping
   at the first slot whose candidate was produced-but-not-consumed. That touches the
   `candidates()`/cursor interface of the 3 coverage-cursor feed classes (brand/osm/
   aggregator — NOT site_query, NOT domain_feed; see Context) + `run_active` + wiring +
   tests. Higher risk, low severity — warrants checkpointed review, not an autonomous
   overnight change.

## Correct design (for when this is picked up)

Reuse the search track's primitive (`origin_key` + harvest `stop_index`):

1. Each of the 3 feeds tags its candidates: `origin_key = "feed:brand"` / `"feed:osm"` /
   `"feed:aggregator"`, and records the window slot each candidate came from
   (e.g. `origin_slot: int`). Slot indices are valid **only within the pass that produced
   them** — for aggregator the host list can mutate between passes (`add`/evict), so
   `commit` MUST run in the same pass the candidates were emitted (it does: harvest →
   commit are sequential in `run_active`). (No `feed:site` — see Context.)
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
so this consume-commit refactor is a coverage-latency tightening, not a data-loss fix. Pick
up under review when convenient.

The aggregator evict-before-harvest path (point 1 above) is **inert** today (its ingest is
gated off by blocklist=no-fetch) and is **separate** from this refactor regardless; revisit
it only if the aggregator ingest is re-enabled.
