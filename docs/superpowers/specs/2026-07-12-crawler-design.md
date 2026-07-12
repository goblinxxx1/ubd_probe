# UBD Discounts — Crawler Design

**Date:** 2026-07-12
**Sub-project:** 4 of 4 (Crawler)
**Status:** Approved design, ready for implementation planning
**Branch:** `feat/crawler` (cut from `main`)

## Context

Fourth and final sub-project of the UBD platform (backend = sub-project 1, admin
panel = 2, public frontend = 3 — all merged to `main`). The crawler is a
**scheduled service** that visits registered sources (`website` / `facebook` /
`telegram` / `instagram`), extracts candidate offers, and proposes new sources —
feeding everything into the backend for human moderation.

Every offer the crawler submits lands as `created_by=crawler`,
`status=pending_review`; a moderator approves/edits it in the admin panel before
it becomes public. The crawler is therefore **best-effort**: precision matters
less than not crashing and not flooding moderators with duplicates.

## Goals

- Visit active sources on a schedule and extract candidate offers from their
  public content.
- Discover and propose new sources found while crawling.
- Talk to the backend **only** through its internal API (`X-API-Key`).
- Survive the messy realities of social platforms (rate limits, bans, CAPTCHAs,
  markup changes) without crashing the run.

## Non-Goals

- No automated account creation for any platform (against ToS, needs paid
  grey-market SMS/proxy infrastructure, requires CAPTCHA solving — all excluded).
- No paid third-party scraping services or paid LLM APIs at runtime.
- No admin-panel changes. Crawler configuration is file-based, not UI-managed.
- No approval/publishing logic — that stays in the admin panel.

## Hard Constraint: Zero-Cost Runtime

Once the developer's Claude subscription ends, the crawler must keep working with
**no ongoing spend**. Concretely:

- Extraction is **heuristic / offline** by default. No cloud LLM.
- No paid scraping services, SMS-activation services, or paid proxies are
  required for the service to run.
- Only free, install-once Python libraries are used (`httpx`, an HTML parser,
  `instaloader`, etc.).
- An **optional local LLM** (Ollama) hook exists in the extractor interface but
  is never required and never enabled by default. If ever used, it is local and
  free (costs machine resources, not money).

## Architecture Overview

```
Windows Task Scheduler / cron
        │  (runs on interval)
        ▼
  python -m crawler run   ← short-lived process, exits after one pass
        │
        ├─ api_client ──────────► backend internal API (X-API-Key)
        │     GET sources, crawl-state, bot-account state
        │     POST offers, suggested-sources, crawl-state, bot-account state
        │
        ├─ per source: fetcher (website/telegram/instagram/facebook)
        │     └─ pluggable access provider (default: direct/login; hook: paid svc)
        ├─ extractor (heuristic; hook: local_llm)
        ├─ discovery (passive always; active opt-in)
        └─ account pool (IG/FB rotation, cooldown/ban states)
```

The crawler is a **short-lived CLI**: the OS scheduler wakes it, it does one full
pass over due sources, then exits. Nothing stays resident between runs. If a run
crashes, the next scheduled run still fires.

## Backend Integration

### Existing internal API (unchanged, already in `main`)

Auth: header `X-API-Key` == `settings.crawler_api_key`.

- `GET /api/internal/sources?is_active=true` → sources to crawl.
- `POST /api/internal/offers` — `OfferCreate` + optional `source_id`; backend
  forces `created_by=crawler`, `status=pending_review`.
- `POST /api/internal/suggested-sources` — `name, type, url_or_handle,
  discovered_from_source_id, discovery_note`.

### Backend changes required by this track

The backend owns MySQL; the crawler never connects to the DB directly. This
track adds to `backend/` (new models + Alembic migration + internal endpoints):

1. **Offer dedup on the backend (correctness lives here).**
   - Add nullable `Offer.content_hash` (crawler-computed).
   - Unique constraint on `(source_id, content_hash)`. Admin-created offers leave
     `content_hash` NULL (MySQL permits multiple NULLs, so they never collide).
   - `POST /api/internal/offers`: if an offer with the same `(source_id,
     content_hash)` exists, return the existing one (idempotent, HTTP 200) instead
     of creating a duplicate. This guarantees no duplicates even if crawler-side
     state is lost.

2. **Suggested-source idempotency.**
   - `POST /api/internal/suggested-sources`: if a suggestion with the same
     `(type, url_or_handle)` already exists, return it instead of inserting a
     duplicate.

3. **Crawl state (read-optimization only, not correctness).**
   - New table `source_crawl_state`: `source_id` (FK, unique), `last_seen_key`
     (str — platform-specific cursor: last post id / timestamp), `last_crawled_at`.
   - `GET /api/internal/sources/{id}/crawl-state` → `{ last_seen_key,
     last_crawled_at }` (nulls if never crawled).
   - `POST /api/internal/sources/{id}/crawl-state` → upsert `last_seen_key`,
     set `last_crawled_at = now()`, and mirror `sources.last_crawled_at`.

4. **Bot-account pool state (metadata only — NO credentials in DB).**
   - New table `bot_account`: `platform` (instagram/facebook), `username`,
     `state` (active/cooldown/banned), `cooldown_until` (nullable),
     `last_used_at`, `note`. Unique `(platform, username)`.
   - `GET /api/internal/bot-accounts?platform=...` → pool state.
   - `POST /api/internal/bot-accounts/{platform}/{username}/state` → upsert
     `state` / `cooldown_until`. (Row auto-created on first report so the crawler
     can register accounts it finds in its config.)
   - **Passwords/session files live only in the crawler's file config**, keyed by
     `username`. The DB stores only rotation metadata so ban/cooldown state
     survives between short-lived runs.

Exact request/response schemas are finalized during planning; the above is the
committed shape.

## Crawler Service Structure

Standalone service in `crawler/`, its own venv and `pyproject.toml`, mirroring the
`backend/` convention. Tests run fully offline.

```
crawler/
  pyproject.toml, .env.example, README.md, register-task.ps1
  crawler/
    __main__.py        # entrypoint: `python -m crawler run`
    config.py          # load .env: API url, X-API-Key, accounts, proxies,
                       #   rate-limit, extractor choice, active-discovery flag
    api_client.py      # internal API client (sources, offers, suggested,
                       #   crawl-state, bot-accounts) with X-API-Key
    runner.py          # orchestrates one pass over due sources
    fetchers/
      base.py          # Fetcher interface: fetch(source, state) -> list[RawItem]
      website.py       # HTTP + HTML parse
      telegram.py      # t.me/s/<handle> (no creds); optional MTProto hook
      instagram.py     # instaloader via account pool; degrade to no-login
      facebook.py      # login via account pool; degrade to no-login (og:meta)
    accounts/pool.py   # bot-account pool: state, auto-rotation, cooldown
    extract/
      base.py          # Extractor interface: extract(RawItem) -> OfferCandidate|None
      heuristic.py     # keyword + regex extraction (default)
      # local_llm.py   # hook only — NOT implemented this track
    discovery/
      passive.py       # extract source candidates from crawled content (always)
      active.py        # keyword search on platforms (opt-in, throttled)
    dedup.py           # content_hash: sha256 of normalized (lowercased,
                       #   whitespace-collapsed) offer title+provider+body text
    ratelimit.py       # per-platform throttle + polite delays
    models.py          # dataclasses: RawItem, OfferCandidate, SourceCandidate
  tests/               # pytest; mock HTTP / instaloader / api_client
```

## Fetchers (per-platform access)

All fetchers implement one interface (`fetch(source, state) -> list[RawItem]`) and
return normalized `RawItem`s (raw text + metadata + a stable per-item key for the
`last_seen` cursor). Access is **pluggable per platform** so the backing method can
change (direct/login now; paid service later) without touching extraction or
discovery.

- **website** — `httpx` GET + HTML parse. Respect `robots.txt`, set a real
  User-Agent, follow the site's own listing/article structure. Fully real.
- **telegram** — read `https://t.me/s/<handle>` HTML for public channels (no
  credentials). Optional MTProto (Telethon, free `api_id`) hook for groups. Real.
- **instagram** — `instaloader` authenticated with a bot account from the pool;
  **degrade to no-login** (public `og:` metadata) when the pool is exhausted.
- **facebook** — authenticated read via a pool bot account; **degrade to no-login**
  (public `og:` metadata) when the pool is exhausted.

**Resilience:** any fetcher that hits a ban / checkpoint / CAPTCHA / parse failure
returns "nothing new" and logs it — it never throws up the stack. One failing
platform never blocks the others or aborts the run.

## Bot-Account Pool (IG/FB)

- Accounts are **real**, created manually by a human (one-time), listed in the
  crawler's file config with credentials. **No auto-creation, no fakes.**
- The pool tracks each account's state: `active` / `cooldown` / `banned`,
  persisted in the backend (`bot_account` table) so it survives between runs.
- On ban/checkpoint detection → mark `banned`, auto-rotate to the next live
  account **without code changes**. `cooldown` (soft rate-limit) expires
  automatically after `cooldown_until`.
- When the whole pool for a platform is unavailable → that platform **degrades to
  no-login** for the pass and logs it; other platforms proceed. Next scheduled run
  re-checks (cooled-down accounts may be active again).
- Growing the pool = add credentials to config (code unchanged). The infra
  supports a pool of any size from day one, even if it starts with 0–2 accounts.

## Extraction

Pluggable `Extractor` interface; one implementation shipped this track:

- **`heuristic` (default, offline, deterministic):**
  - Offer triggers: Ukrainian keyword dictionary (знижка, акція, −%, безкоштовно,
    для військових/ветеранів/УБД, промокод, …). Non-offer content is dropped.
  - `discount_type` / `discount_value` via regex: `-20%` / «знижка 20%» → percent;
    «500 грн» / «-500₴» → fixed; «безкоштовно» / free → free.
  - Dates `valid_from` / `valid_until` via regex («до 31.12», «з 1 по 15 липня»).
  - `provider` defaults to the source's name.
  - Categories mapped from keywords onto existing backend categories
    (`target_category_ids` / `offer_category_ids`) fetched from the backend.
  - Ambiguous fields left empty — the moderator completes them (all offers are
    `pending_review` anyway).
- **`local_llm` (Ollama):** interface hook only. **Not implemented this track.**
  Documented so it can be added later (heuristic prefilter → local LLM on
  candidates) without reworking anything. Never a runtime dependency.

## Discovery (proposing new sources)

Two levels, both submit to `POST /api/internal/suggested-sources` with a
`discovery_note` (where it was found) and `discovered_from_source_id`.

- **Level 1 — passive (always on):** while crawling existing sources, extract
  mentions/links to other accounts/channels (`@handle`, `t.me/…`,
  `instagram.com/…`, `facebook.com/…`, external links). Filter against existing
  `sources`; backend idempotency drops re-suggestions. Zero-cost, safe, no extra
  requests.
- **Level 2 — active search (opt-in, default OFF):** keyword search on platforms
  where authorized access exists (Telegram via MTProto; IG/FB via the login pool).
  Throttled: hard per-run request budget, low frequency (not every run), same
  rate-limiter/cooldown. **Not for website** (would mean scraping search engines).
  Enabled explicitly via config; carries non-zero ban risk, so off until the
  operator turns it on.

## Dedup & Crawler State

- **Correctness:** backend enforces offer dedup via `(source_id, content_hash)`
  and suggested-source idempotency via `(type, url_or_handle)`. Re-submitting is
  safe and idempotent.
- **Optimization:** `last_seen_key` per source (in `source_crawl_state`) lets the
  crawler skip already-seen items and avoid re-reading old content. Losing it only
  costs redundant reads, never duplicates.
- Per pass, per source: load crawl-state once → fetch new items → extract → submit
  offers + suggestions → write back `last_seen_key` + `last_crawled_at`.

## Scheduling

- Crawler is a CLI: `python -m crawler run` does one pass and exits.
- The OS scheduler owns the timer: **Windows Task Scheduler** (dev/now) or `cron`
  (prod). A shipped `register-task.ps1` registers the scheduled task (interval +
  venv python path + entrypoint) so "runs on schedule" works out of the box.
- Manual invocation is available for testing/debugging but is not the run mode.
- Rationale over an in-process daemon: survives crashes (next run still fires),
  nothing resident between runs, trivially testable.

## Configuration

File-based, in `crawler/.env` (gitignored), documented in `.env.example`:

- `INTERNAL_API_URL`, `CRAWLER_API_KEY`
- Bot accounts (per platform: username + password/session), optional proxies
- Rate-limit / politeness settings (delays, per-run budgets)
- `EXTRACTOR` = `heuristic` (default)
- `ACTIVE_DISCOVERY` = off (default)

## Error Handling & Resilience

- Per-source isolation: a failure crawling one source is logged and skipped; the
  pass continues.
- Per-platform isolation: bans/exhausted pools degrade or skip that platform only.
- Fetchers never raise up the stack — they return "nothing new" + log.
- Network/API errors to the backend are retried with backoff a bounded number of
  times, then that unit is skipped.
- Structured logging throughout (per-source counts, rotation events, degradations)
  so runs are auditable without external tooling.

## Testing

- `pytest`, fully offline. No live network, no real MySQL, no real platforms.
- Fetchers tested against saved HTML/response fixtures.
- `instaloader` / MTProto / `httpx` mocked.
- `api_client` tested against a mocked internal API.
- Heuristic extractor tested on Ukrainian offer/non-offer fixtures (discount
  type/value/date parsing, category mapping).
- Account-pool rotation/cooldown/ban logic unit-tested.
- Dedup (`content_hash`) determinism unit-tested.

## Security Considerations

- Bot-account credentials live only in the gitignored file config, never in the
  DB and never in the repo. The DB holds only rotation metadata keyed by username.
- `X-API-Key` is the sole backend credential the crawler holds.
- No CAPTCHA solving, no account creation, no grey-market services — by design.

## What This Track Touches

- **New:** `crawler/` service (+ its venv, tests, Task Scheduler script).
- **Modified:** `backend/` — new models (`source_crawl_state`, `bot_account`),
  `Offer.content_hash` + constraint, Alembic migration, new internal endpoints,
  idempotency on offers/suggested-sources, backend tests.
- **Untouched:** `admin/`, `public/`.

## Future / Out of Scope (documented, not built)

- `local_llm` (Ollama) extractor implementation.
- Paid access providers (Apify/HikerAPI) behind the existing fetcher provider hook.
- Turning on active (Level 2) discovery in production.
- MTProto Telegram adapter for groups (hook noted; `t.me/s/` covers channels now).
```
