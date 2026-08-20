# Query-Term Audit Surface Implementation Plan (Track A1)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Checkbox (`- [ ]`) steps.

**Goal:** A moderator approves/rejects mined query terms in the admin; the crawler submits candidates and picks up approved terms on a ~6h tick — closing the self-learning loop.

**Architecture:** Mirror the existing `blocked_hosts` (host-candidates) audit end to end: backend `query_terms` table + endpoints, crawler submit + 6h approved-load + live grid rebuild, admin `QueryTermsView`.

**Tech Stack:** FastAPI/SQLAlchemy/Alembic (backend), Python (crawler), Vue3 (admin); MySQL.

## Global Constraints

- Ukrainian-only; no Russian in code/tests/UI copy.
- **Mirror `blocked_hosts` exactly** — model `app/models/blocked_host.py`, crud `app/crud/blocked_host.py`, schemas `app/schemas/blocked_host.py`, admin endpoints `app/routers/admin.py` (`/host-candidates`), internal `app/routers/internal.py` (`/host-candidates`, `/blocked-hosts`), admin `views/HostCandidatesView.vue` + `api/hostCandidates.js` + router + `AdminLayout` nav.
- Backend tests: from `backend/`, `TEST_DATABASE_URL="mysql+pymysql://root:my-secret-pw@localhost:3306/ubd_test"` + `./.venv/Scripts/python.exe -m pytest`. (mysql-container must be up.)
- Crawler tests: from `crawler/`, `./.venv/Scripts/python.exe -m pytest`.
- Additive only: empty approved-terms ⇒ grid byte-equivalent to today.

---

## Task 1: Backend — `query_terms` model + enum + schemas + migration + CRUD

**Files:** create `app/models/query_term.py`, `app/schemas/query_term.py`, `app/crud/query_term.py`, `alembic/versions/<rev>_query_terms.py`; edit `app/models/enums.py` (`QueryTermStatus`), `app/models/__init__.py` (register). Test `backend/tests/test_query_terms.py`.

- Enum `QueryTermStatus(str, enum.Enum)`: pending/approved/rejected (mirror `BlockedHostStatus`).
- Model `QueryTerm`: `id` PK, `term` String(255) unique not null, `status` Enum default pending, `z` Float default 0.0, `support` Int default 0, `reviewed_by` Int?, `created_at` server_default now, `reviewed_at` DateTime?.
- Schemas: `QueryTermCandidate(term:str, z:float=0.0, support:int=0)`, `QueryTermsSubmit(candidates: list[QueryTermCandidate])`, `QueryTermOut(from_attributes; id, term, status, z, support, created_at, reviewed_at)`.
- CRUD `query_term_crud`:
  - `upsert_candidates(db, items: list[QueryTermCandidate]) -> int`: for each, term=strip().lower(); if exists & pending → refresh z/support; if absent → insert pending; approved/rejected untouched. Return count upserted.
  - `get(db, id)`, `list_terms(db, status=None)` (order_by created_at desc), `_review`, `approve(db,id,by)`, `reject(db,id,by)`, `list_approved_terms(db) -> list[str]`.
- Migration: create `query_terms` (columns as model, unique on term). Mirror an existing create-table migration.

- [ ] Write `test_query_terms.py`: upsert new→pending; re-upsert pending refreshes z; approve→status approved & reviewed set; `list_approved_terms` returns approved term strings; re-upsert of an approved term does NOT revert it.
- [ ] Run → fail (module missing). Implement model/enum/schemas/crud + migration. Run → pass.
- [ ] Apply migration to test DB is automatic (conftest create_all). Commit.

---

## Task 2: Backend — endpoints (admin + internal)

**Files:** edit `app/routers/admin.py`, `app/routers/internal.py`. Test `backend/tests/test_query_terms_admin.py`.

- admin.py (mirror host-candidate endpoints): `GET /query-terms?status=` → `list_terms`; `POST /query-terms/{id}/approve` → `approve`; `POST /query-terms/{id}/reject` → `reject`. Response `QueryTermOut`. Auth `get_current_admin`.
- internal.py: `POST /query-terms` (body `QueryTermsSubmit`) → `upsert_candidates`, return `{"upserted": n}`; `GET /query-terms/approved` → `list_approved_terms` (list[str]).

- [ ] Write `test_query_terms_admin.py` (mirror `test_blocked_hosts_admin.py`): submit candidates via internal → list pending via admin → approve one → `/query-terms/approved` returns it; reject another → not approved.
- [ ] Run → fail. Implement endpoints. Run → pass. Commit.

---

## Task 3: Crawler — api_client + grid integration + 6h refresh + miner submit

**Files:** edit `crawler/crawler/api_client.py`, `crawler/crawler/discovery/query_lexicon.py`, `crawler/crawler/runner.py`, `crawler/crawler/scheduler.py`, `crawler/crawler/__main__.py`, `crawler/crawler/config.py`. Tests: `crawler/tests/test_query_lexicon.py`, `test_scheduler.py`, `test_runner_*` / `test_api_client` as present.

- `api_client`: `submit_query_candidates(self, items: list[dict]) -> None` (POST `/api/internal/query-terms` `{"candidates": items}`); `list_approved_query_terms(self) -> list[str]` (GET `/api/internal/query-terms/approved`).
- `query_lexicon`: add module `_approved: tuple = ()`; `reload_backend_terms(terms)` sets `_approved` (dedup casefold vs cats/mined); `learned_services()` and `compose_service_terms` append `_approved` (after seed+cats+mined, deduped).
- `runner.refresh_grid_from_approved(config)`: if `_search_pass` is None → return; `query_lexicon.reload_backend_terms(self._api.list_approved_query_terms())`; `self._search_pass.set_grid(build_query_grid(config))`. Best-effort (try/except log).
- `runner.learn_and_reload_grid`: after `bootstrap(...)`, read the candidates file and `self._api.submit_query_candidates([...])` (best-effort).
- `scheduler.run_loop`: add `refresh=None, refresh_interval_seconds=0` — invoke on first iteration and every interval (mirror the learn tick).
- `__main__`: build `_refresh = lambda: runner.refresh_grid_from_approved(config)`; pass `refresh=_refresh, refresh_interval_seconds=config.query_terms_refresh_interval_seconds`.
- `config`: `query_terms_refresh_interval_seconds: int = 21600` (3 places).

- [ ] Tests: `reload_backend_terms(["імплантація"])` → `compose_service_terms` includes it; empty → unchanged; `refresh_grid_from_approved` with a fake api+search_pass calls `set_grid`; scheduler invokes `refresh` on first tick and after interval; config default 21600.
- [ ] Run → fail → implement → pass. Full crawler suite green. Commit.

---

## Task 4: Admin — QueryTermsView + api + router + nav

**Files:** create `admin/src/api/queryTerms.js`, `admin/src/views/QueryTermsView.vue`; edit `admin/src/router/index.js`, `admin/src/layouts/AdminLayout.vue`.

- `api/queryTerms.js`: `list(params)`, `approve(id)`, `reject(id)` → `/admin/query-terms...` (mirror `hostCandidates.js`).
- `QueryTermsView.vue`: mirror `HostCandidatesView.vue` — a table of term / z / support / status with Approve & Reject buttons; status filter; loads `list({status:'pending'})`.
- Router: import + `{ path: "query-terms", name: "query-terms", component: QueryTermsView }`.
- Nav: `AdminLayout` link `{ name: 'query-terms' }` label "Терміни пошуку".

- [ ] Implement mirroring HostCandidatesView. `cd admin && npm run build` → passes (no type/scoped-Less errors). Commit.

---

## Task 5: Rollout (ordered)

- [ ] Backend: `docker compose exec backend alembic upgrade head`; `docker compose build backend && docker compose up -d backend`.
- [ ] Crawler: `docker compose build crawler && docker compose up -d crawler`.
- [ ] Admin: `docker compose build admin && docker compose up -d admin`.
- [ ] Verify loop: `docker compose exec crawler python -c "from crawler.learn.run_query_miner import run_query_miner; from crawler.config import load_config; ..."` to mine + submit; `GET /api/internal/query-terms/approved` and `/admin/query-terms?status=pending`; approve one in admin; confirm it appears in `build_query_grid` output after refresh.

---

## Self-Review

Spec coverage: backend table/endpoints (T1,T2), crawler submit+load+6h+grid (T3), admin view (T4), rollout+verify (T5). Mirror of a proven pattern → low risk; additive; empty-approved = byte-equivalent. Placeholder scan: none (task bodies name the exact mirror source). Type consistency: `QueryTermStatus`, `QueryTerm`, `query_term_crud.list_approved_terms -> list[str]`, `api.list_approved_query_terms() -> list[str]`, `query_lexicon.reload_backend_terms(list[str])` consistent across tasks.
