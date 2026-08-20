# Admin: return a rejected query term to candidates + drop the dead `z` column

**Date:** 2026-08-20
**Status:** Design approved
**Builds on:** [[ubd-crawler-query-miner-v2]] (support-ranking; `z` is degenerate/dead),
[[ubd-crawler-query-miner-audit-loop]] (the query_terms audit surface).

## Problem

1. **No un-reject.** A moderator can approve/reject a mined query term but cannot return a
   rejected one to the candidate list — a mistaken or later-reconsidered reject is
   permanent from the UI. The crawler hard-excludes rejected terms from mining (v2), so a
   rejected term never re-surfaces on its own.
2. **The `z` column misleads.** The audit table shows `z` (log-odds z-score). Post-v2 the
   all-pass corpus makes `z` degenerate (~1.0) and it no longer ranks or gates anything —
   ranking is by `support` (distinct business domains). Showing `z` reads like a quality
   score that does nothing. `support` is the real signal but is labelled the opaque
   «Домени».

## Goal

Let a moderator send a rejected term back to `pending`, and present only the signal that
matters, clearly named.

**Non-goals:** un-approve (removing a term from the live grid — different semantics, not
requested); any crawler change; removing the `z` field from the DB/API (kept — it may
revive if a real FAIL corpus accumulates).

## Design

### Backend

- `crud/query_term.py` — `to_pending(db, term_id) -> QueryTerm`: set `status=pending`,
  `reviewed_by=None`, `reviewed_at=None` (a clean, un-reviewed candidate again). Flips
  unconditionally, consistent with the existing `approve`/`reject` (which also don't gate
  on prior status); the UI only exposes it on rejected rows.
- `routers/admin.py` — `POST /query-terms/{term_id}/unreject` → `to_pending`, mirroring the
  approve/reject routes (same auth dependency, `QueryTermOut` response).

### Admin ([QueryTermsView.vue](admin/src/views/QueryTermsView.vue))

- **Columns:** remove the `z` column and its `#col-z` slot; rename the `support` column
  «Домени» → «Бізнес-сайтів».
- **Actions:** for `status === 'rejected'` rows, show a «Повернути в кандидати» button →
  `onUnreject(id)` → `unreject(id)` then `load()`. Pending rows keep approve/reject;
  approved rows keep the plain status label.
- `api/queryTerms.js` — add `unreject(id)` (`POST /admin/query-terms/{id}/unreject`).

### Crawler

No change. Once a term's status ≠ rejected, `GET /query-terms/rejected` stops returning it,
so the miner stops excluding it and re-surfaces it; meanwhile the row is already `pending`
and visible in the audit UI.

## Data flow

Moderator clicks «Повернути в кандидати» → `POST /unreject` → row `rejected → pending`,
reviewed fields cleared → reload shows it under the pending filter → next mining run
refreshes its z/support (upsert refreshes pending rows) and no longer excludes it.

## Impact / testing

- **Additive:** new endpoint + one crud fn; DB/API `z` field untouched (UI-only removal);
  no migration.
- **Backend tests:** `to_pending` flips rejected→pending and clears reviewed_by/at; a
  re-mine `upsert_candidates` then refreshes it (already covered behaviour).
- **Admin test:** QueryTermsView renders «Повернути в кандидати» on a rejected row and
  calls `unreject`; the `z` column is gone and support shows under «Бізнес-сайтів».
- **Docker-only rollout:** backend + admin rebuild.

## Tasks (SDD)

1. **Backend** — `to_pending` crud + `/unreject` route + test.
2. **Admin** — `unreject` api + view (drop z, rename support, rejected-row button) + test;
   `npm run build`.
