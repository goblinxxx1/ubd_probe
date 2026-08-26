# Judge Re-Queue Sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** The relevance judge autonomously cleans the moderation queue: offers that entered `pending_review` WITHOUT a judge verdict (fail-open on judge timeout/unavailability) get re-judged when the judge is healthy, and junk is soft-rejected into the EXISTING rejected tab — no new human queue, and the human's pending queue shrinks.

**Architecture:** The "unjudged" signal already exists — a `pending_review`, crawler-created offer whose `content_hash` is ABSENT from the crawler's local verdict cache (`/data/judge_cache.json`). A periodic crawler tick (in the existing scheduler loop, gated on judge health) lists such offers from the backend, reconstructs the judge candidate from the offer's own fields (title/description/discount/article_url — same shape the judge used at creation), calls `judge.verdict`, and: genuine → cache the verdict; not genuine → soft-reject via a new internal endpoint with a reason. Reject is REVERSIBLE (rejected tab, admin can restore) and marked "відхилив суддя" (`reviewed_by IS NULL` + `rejection_reason` set). First run sweeps the existing junk (e.g. offers 429/438/439).

**Tech Stack:** Backend FastAPI/SQLAlchemy/Alembic (MySQL), crawler Python (httpx judge + JSON verdict cache), admin Vue3.

## Global Constraints
- **Autonomy invariant** ([[ubd-crawler-autonomy-invariant]]): fully automatic, free (local Qwen judge only), no human in the runtime loop. This feature REDUCES human work (auto-cleans queue); it must NEVER create a new required human queue.
- **Human override coexists / reversible:** judge-reject is SOFT (status=rejected, restorable), never hard-delete. Marked distinctly from admin rejects so a human can audit/restore a false auto-reject.
- **Only crawler-created, pending_review, unjudged** offers are eligible. NEVER re-judge/auto-reject admin-created offers, already-approved/published offers, or offers already in the verdict cache.
- **Judge-health gated:** the sweep runs only when the judge is enabled AND reachable; on `JudgeUnavailable` it stops the sweep (does not reject anything that pass) — never reject on a judge error (that would be the inverse bug).
- Ukrainian for new comments/log/admin text; no Russian. No new deps.
- Tests: backend `./.venv/Scripts/python.exe -m pytest -q` from `backend/` (MySQL `ubd_test`); crawler from `crawler/`; admin `npm run build` + vitest from `admin/`.
- Reversible-reject reuses the existing `set_status(..., OfferStatus.rejected, ...)` soft-reject mechanism; do not invent a parallel status.

---

## File Structure
- **Backend**: `models/offer.py` (+`rejection_reason`), an Alembic migration, `crud/offer.py` (`judge_reject`, `list_pending_unjudged_for_crawler`), `routers/internal.py` (GET pending-unjudged list + POST judge-reject), `schemas/offer.py` (lean internal DTO with content_hash), tests.
- **Crawler**: `api_client.py` (2 methods), NEW `crawler/discovery/rejudge.py` (RejudgeSweep), `runner.py` + `scheduler.py` + `wiring.py` (wire the tick), `config.py` (budget/interval knobs), tests.
- **Admin**: the offers/rejected view — show `rejection_reason` + a "Відхилив суддя" badge when `reviewed_by` is null and reason is set.

---

## Task 1: Backend — `rejection_reason` column + judge-reject + pending-unjudged query

**Files:** `backend/app/models/offer.py`, new `backend/alembic/versions/*_offer_rejection_reason.py`, `backend/app/crud/offer.py`, `backend/tests/` (offer crud/admin tests).

**Interfaces:**
- `offers.rejection_reason: str | None` (nullable varchar(255)).
- `crud.offer.judge_reject(db, offer_id: int, reason: str) -> Offer` — sets `status=rejected`, `reviewed_by=None`, `rejection_reason=reason`; only if the offer is currently `pending_review` and `created_by` is a crawler kind (else raise/skip — do not touch admin-reviewed or published offers).
- `crud.offer.list_pending_unjudged_for_crawler(db, limit: int) -> list[Offer]` — `status=pending_review` AND `created_by IN (crawler, crawler_suggestion)`, ordered oldest-first, capped at `limit`.

- [ ] **Step 1: Failing tests** — write backend tests: (a) `judge_reject` flips a pending crawler offer to rejected with `reviewed_by IS NULL` and the reason stored, and refuses (no-op/raise) a published or admin-created offer; (b) `list_pending_unjudged_for_crawler` returns only pending crawler offers, oldest-first, respects limit. Read `backend/tests/` for the fixture style (session, factory) and mirror it.
- [ ] **Step 2: Run — RED** (`./.venv/Scripts/python.exe -m pytest -q -k "judge_reject or pending_unjudged"`), expect failures (attr/func missing).
- [ ] **Step 3: Implement** — add the model column; generate/write the Alembic migration (follow the repo's existing migration head-chain style, `add_column`/`drop_column`, nullable, no data migration needed); add the two crud functions. `judge_reject` must guard `created_by`/`status`.
- [ ] **Step 4: Run — GREEN** + full backend suite.
- [ ] **Step 5: Commit** `feat(backend): offer.rejection_reason + judge_reject + pending-unjudged query`.

---

## Task 2: Backend — internal endpoints (X-API-Key)

**Files:** `backend/app/routers/internal.py`, `backend/app/schemas/offer.py`, tests.

**Interfaces:**
- `GET /api/internal/offers/pending-unjudged?limit=N` → `list[PendingUnjudgedOut]` where `PendingUnjudgedOut = {id, title, description, discount_type, discount_value, article_url, content_hash}`. Uses `list_pending_unjudged_for_crawler`.
- `POST /api/internal/offers/{offer_id}/judge-reject` body `{reason: str}` → `OfferOut`. Uses `judge_reject`. Guarded by the router's existing `require_api_key`.

- [ ] **Step 1: Failing tests** — internal-router tests: the GET returns the lean DTO incl. `content_hash` for a pending crawler offer and omits published/admin ones; the POST soft-rejects and stores the reason; both require the API key (401 without). Mirror existing `internal.py` test style.
- [ ] **Step 2: RED.**
- [ ] **Step 3: Implement** the DTO + two endpoints on the internal router (reuse `require_api_key` dependency already applied there).
- [ ] **Step 4: GREEN** + full backend suite.
- [ ] **Step 5: Commit** `feat(backend): internal pending-unjudged list + judge-reject endpoints`.

---

## Task 3: Crawler — ApiClient methods

**Files:** `crawler/crawler/api_client.py`, `crawler/tests/`.

**Interfaces:**
- `list_pending_unjudged(limit: int) -> list[dict]` (GET the internal endpoint; returns the DTO dicts).
- `judge_reject_offer(offer_id: int, reason: str) -> None` (POST judge-reject). Best-effort/raises consistent with sibling methods.

- [ ] **Step 1: Failing tests** — mirror existing ApiClient tests (they stub httpx / a fake transport). Assert the two methods hit the right URLs/verbs with the API key and parse the list.
- [ ] **Step 2: RED → Step 3: Implement (follow the existing ApiClient method pattern incl. X-API-Key header) → Step 4: GREEN + full crawler suite.**
- [ ] **Step 5: Commit** `feat(crawler): ApiClient pending-unjudged + judge-reject`.

---

## Task 4: Crawler — RejudgeSweep (core logic)

**Files:** NEW `crawler/crawler/discovery/rejudge.py`, `crawler/tests/test_rejudge.py`.

**Interfaces:**
- `class RejudgeSweep: __init__(self, api, judge, cache, *, budget: int = 30)`.
- `run(self) -> dict` — lists up to `budget` pending-unjudged offers; for each, SKIP if `content_hash` already in `cache` (already judged); else reconstruct a candidate (`types.SimpleNamespace(title, body=description, discount_type, discount_value, article_url)`) and call `judge.verdict(cand)`:
  - on `JudgeUnavailable` → STOP the whole sweep immediately (return partial; never reject on unavailability);
  - on `JudgeError` (per-candidate timeout/parse) → skip this candidate (leave it for a later sweep), continue;
  - verdict genuine AND page_scoped → `cache.put(content_hash, verdict)` (so it won't be reconsidered);
  - else → `api.judge_reject_offer(id, reason=f"суддя: {verdict.reason}")` AND `cache.put(...)` (record the reject verdict too, so a re-list won't re-hit it).
  Returns counts `{scanned, kept, rejected, skipped}`.

- [ ] **Step 1: Failing tests** — with a fake `api` (canned pending list incl. one junk + one genuine + one already-cached) and a fake `judge` (returns genuine for one, not-genuine for the junk, raises JudgeUnavailable to prove the sweep stops): assert the junk is rejected with a `суддя:`-prefixed reason, the genuine one is cached-not-rejected, the already-cached one is skipped (judge not called), and a JudgeUnavailable stops the sweep with nothing wrongly rejected. Use the real `VerdictCache` + `Verdict`.
- [ ] **Step 2: RED → Step 3: Implement `rejudge.py` → Step 4: GREEN + full crawler suite.**
- [ ] **Step 5: Commit** `feat(crawler): RejudgeSweep — re-judge unjudged pending offers, soft-reject junk`.

---

## Task 5: Crawler — wire the sweep into the loop (health-gated, budgeted)

**Files:** `crawler/crawler/runner.py`, `crawler/crawler/scheduler.py`, `crawler/crawler/wiring.py`, `crawler/crawler/config.py`, tests.

**Interfaces:**
- Config: `rejudge_enabled: bool = True`, `rejudge_interval_seconds: int = 3600`, `rejudge_budget: int = 30` (Task-6-style config triple).
- `Runner.rejudge_tick(config)` — best-effort, never raises; constructs/uses a `RejudgeSweep` with the runner's judge+cache+api; runs only when `config.judge_enabled and config.rejudge_enabled`. The scheduler invokes it on its own interval (mirror how `learn_and_reload_grid` is wired via the scheduler `learn`/interval callback — add a parallel periodic hook, or fold into the existing learn tick if that is cleaner; READ scheduler.py + runner.py to choose and justify). Log a one-line summary `rejudge: scanned=… kept=… rejected=…`.

- [ ] **Step 1: Failing test** — a wiring/runner test: `rejudge_tick` calls `RejudgeSweep.run` when enabled and is a no-op when `rejudge_enabled=False` or `judge_enabled=False`; the scheduler fires it on its interval. Mirror the existing `learn_and_reload_grid`/scheduler test.
- [ ] **Step 2: RED → Step 3: Implement (config triple + tick + scheduler wiring + wiring construction) → Step 4: GREEN + full crawler suite.**
- [ ] **Step 5: Commit** `feat(crawler): schedule periodic judge re-queue sweep (health-gated, budgeted)`.

---

## Task 6: Admin — "Відхилив суддя" transparency

**Files:** admin offers/rejected view + its API mapping; vitest.

**Interfaces:** in the rejected list/detail, when `reviewed_by` is null and `rejection_reason` is set, show a "Відхилив суддя" badge and the reason text. Reuses the existing rejected tab — NO new list/route.

- [ ] **Step 1:** confirm the admin offer DTO surfaces `reviewed_by`/`rejection_reason` (add to the admin offer schema if missing — small backend addition, keep in this task). READ the existing rejected-tab component.
- [ ] **Step 2:** add the badge + reason rendering; a focused vitest that a judge-rejected row (reviewed_by null + reason) shows the badge and an admin-rejected row does not.
- [ ] **Step 3:** `npm run build` clean.
- [ ] **Step 4: Commit** `feat(admin): show "Відхилив суддя" badge + reason in rejected tab`.

---

## Task 7: Deploy + first-run sweep verification

- [ ] **Step 1:** rebuild backend+crawler+admin; `docker compose up -d` (+ `--force-recreate crawler`); `docker compose exec -T backend alembic upgrade head` (rejection_reason column).
- [ ] **Step 2:** trigger/await the first rejudge tick; grep crawler logs for `rejudge: scanned=… rejected=…`.
- [ ] **Step 3:** verify offers 429/438/439 (and other unjudged junk) moved to `status=rejected` with `reviewed_by IS NULL` and a `суддя:` reason (SQL check), and are OUT of the pending queue; a known-genuine pending offer stayed pending and is now cached. Record the before/after pending count (self-reported evidence).

## Self-Review
- Autonomy: no new human queue (rejects into existing rejected tab); pending shrinks. ✅
- Safety: only crawler-created pending unjudged offers; judge-unavailable STOPS the sweep (never rejects on error); soft + reversible + marked. ✅
- Signal reuse: verdict-cache-absence = unjudged; no new offer state/migration for the signal (only `rejection_reason` for the marker/reason). ✅
- Types consistent across tasks: `judge_reject`, `list_pending_unjudged_for_crawler`, `PendingUnjudgedOut{...,content_hash}`, `list_pending_unjudged`, `judge_reject_offer`, `RejudgeSweep.run()->{scanned,kept,rejected,skipped}`.
