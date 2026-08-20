# Query-term audit surface (backend + admin + crawler) — Track A1

**Date:** 2026-08-20
**Status:** Design approved
**Program:** close the self-learning loop (A2 miner precision ✅ → **A1 audit surface**).
See [[ubd-crawler-query-miner-audience-bug]].

## Problem

The miner now surfaces real service terms (A2), but there is **no admin place** to approve
them — the audit queue is a crawler file audited only via CLI. Without a moderator-facing
approve/reject surface, approved terms never reach the grid and the loop stays open.

## Goal

A moderator audits mined query terms in the admin (approve → grid, reject → dropped), and
the crawler picks up approved terms on a ~6h cadence (no restart). Mirror the existing,
working **host-candidates** audit (crawler → backend → admin → crawler) exactly.

## Design — mirror host-candidates end to end

### Backend (mirror `blocked_hosts`)

- **Enum** `QueryTermStatus` (pending/approved/rejected) — mirror `BlockedHostStatus`.
- **Model** `QueryTerm` (`query_terms` table): `id`, `term` (String(255) unique), `status`,
  `z` (Float), `support` (Int), `reviewed_by` (Int?), `reviewed_at` (DateTime?),
  `created_at` (server_default now).
- **Migration** (Alembic): create `query_terms`.
- **Schemas**: `QueryTermCandidate` (term, z, support), `QueryTermsSubmit` (candidates:
  list[QueryTermCandidate]), `QueryTermOut` (from_attributes).
- **CRUD** `query_term_crud`: `upsert_candidates(db, items)` (bulk: refresh z/support while
  pending, insert new pending, leave approved/rejected untouched — mirror
  `upsert_candidate`), `list_terms(db, status)`, `approve(db, id, reviewed_by)`,
  `reject(db, id, reviewed_by)`, `list_approved_terms(db) -> list[str]`.
- **admin.py**: `GET /query-terms?status=`, `POST /query-terms/{id}/approve`,
  `POST /query-terms/{id}/reject` (mirror host-candidate admin endpoints).
- **internal.py**: `POST /query-terms` (bulk submit → `upsert_candidates`),
  `GET /query-terms/approved` → `list_approved_terms` (list[str], mirror `/blocked-hosts`).

### Crawler

- **api_client**: `submit_query_candidates(items: list[dict]) -> None` (POST
  `/query-terms`); `list_approved_query_terms() -> list[str]` (GET `/query-terms/approved`).
- **Miner submit**: in `learn_and_reload_grid` (24h learn tick), after `bootstrap`
  mines candidates, read them and `api.submit_query_candidates(...)` so they appear in the
  admin. (Keep the local candidates file — legacy/CLI.)
- **Grid integration**: `query_lexicon` gains an `_approved` tuple +
  `reload_backend_terms(terms: list[str])`; `compose_service_terms` appends `_approved`
  (after seed + categories + mined). `build_query_grid` stays file-based; the crawler
  refreshes `_approved` separately (below).
- **6h refresh tick** (the immediacy requirement, paced): a new scheduler tick
  `refresh` / `refresh_interval_seconds` (config `query_terms_refresh_interval_seconds`,
  default 21600 = 6h). It calls `runner.refresh_grid_from_approved(config)`:
  `query_lexicon.reload_backend_terms(api.list_approved_query_terms())` then
  `search_pass.set_grid(build_query_grid(config))` — live grid swap (grid_cursor preserved
  modulo new length). Best-effort, never raises. Also runs once at startup.
- **wiring/`__main__`**: build the `refresh` callback and pass it + interval to the
  scheduler, mirroring the `learn` tick wiring.

### Admin (mirror `HostCandidatesView`)

- `api/queryTerms.js` (list/approve/reject), `views/QueryTermsView.vue` (table of term / z /
  support / status + Approve/Reject buttons — mirror `HostCandidatesView`), router entry
  `query-terms`, nav link in `AdminLayout` ("Терміни пошуку").

## Data flow (closed loop)

```
miner (A2, axis-veto) → candidates → api.submit_query_candidates → backend query_terms(pending)
                                                                          │
moderator (admin QueryTermsView) approve ────────────────────────────────┤
                                                                          ▼
crawler 6h refresh: list_approved_query_terms → query_lexicon._approved → build_query_grid → set_grid
```

## Blast radius

- Backend: new model/enum/schemas/crud/migration + 5 endpoints — all additive, mirror an
  existing table; no change to existing tables or offer flow.
- Crawler: 2 api methods, a `query_lexicon._approved` source, a `refresh` tick, one submit
  call in the learn tick, one config. The grid only GAINS approved terms; empty approved =
  byte-equivalent to today.
- Admin: one new view + route + nav + api — mirror an existing view.

## Risks

1. **Backend unreachable during refresh** → `list_approved_query_terms` fails → keep the
   previous `_approved` (best-effort, logged). Low.
2. **A wrong approved term bloats the grid** → the moderator approved it; reversible by
   rejecting (a later refresh drops it since it is no longer `approved`). Low.
3. **Migration** must be applied before the crawler POSTs candidates — rollout order below.

## Testing

- Backend: `query_term_crud` upsert (new/refresh-pending/keep-approved), approve/reject,
  `list_approved_terms`; endpoint tests (admin list/approve/reject, internal submit/approved)
  — mirror the blocked-host tests.
- Crawler: `query_lexicon.reload_backend_terms` + `compose_service_terms` includes approved;
  `refresh_grid_from_approved` calls set_grid with the approved terms; api_client methods;
  learn tick submits candidates (fake api records the payload).
- Admin: component test of `QueryTermsView` approve/reject if the suite has view tests;
  else rely on the build + manual smoke.

## Rollout (ordered)

1. Backend: migration `alembic upgrade head`, rebuild+restart backend.
2. Crawler: rebuild+restart (starts submitting candidates on the learn tick; refreshes
   approved every 6h).
3. Admin: `npm run build`, rebuild+restart admin.
4. Verify: trigger the miner → candidates appear in `GET /query-terms?status=pending` and in
   the admin view; approve one → within ≤6h it appears in `build_query_grid` output.
