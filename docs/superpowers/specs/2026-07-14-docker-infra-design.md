# UBD Discounts — Application Docker Infrastructure Design

**Date:** 2026-07-14
**Scope:** Cross-cutting infrastructure (not a numbered sub-project)
**Status:** Approved design, ready for implementation planning
**Branch:** to be cut from `main`

## Context

All four UBD sub-projects (backend, admin panel, public frontend, crawler) are
complete and merged to `main`. There is a standing agreement that **all UBD
services must run in Docker containers, not as host processes**. No Docker
artifacts exist in the repository yet — the only container today is an external,
shared `mysql-container` (defined outside the repo in `D:\MySQL`, shared with an
unrelated `streamtower` project). This spec defines the greenfield Docker
infrastructure that lets a developer bring the whole application up with
`docker compose up` and see it working end-to-end.

## Goals

- One `docker compose up` brings up the core application (db + backend + both
  SPAs) in a **production-like** shape: static SPA builds served by nginx, uvicorn
  behind them, an isolated database.
- The database is **owned by this compose** (own service + named volume), not the
  external shared `mysql-container`.
- The crawler is runnable in Docker both as a **one-shot** pass ("show me it
  works") and as a **scheduled loop**, but is gated behind a compose profile so it
  never runs on a plain `up`.
- A **deterministic, offline demo path** proves the crawler works end-to-end: a
  fixture website → crawler pass → `pending_review` offer visible in admin →
  approved → visible in public.
- Application code is not modified (the one addition is a demo-seed script).

## Non-Goals

- **Search-based active discovery** (DuckDuckGo/SearXNG provider) — explicitly a
  separate future feature. `ActiveDiscovery.search_provider` stays `None` here.
- **Dev / hot-reload mode** (vite dev servers, `uvicorn --reload`, source volume
  mounts) — may be added later as an override; not in this scope.
- **Deployment / orchestration** (k8s, cloud, TLS, real domains) — local
  prod-like preview only.
- **Running the test suites in Docker** — tests continue to run in host venvs
  against the existing `mysql-container` (see `ubd-dev-environment`). Only the
  `ubd` runtime schema is provisioned in this compose.
- Reusing or touching the external `mysql-container` / `streamtower` setup.

## Architecture

### Service topology (`docker-compose.yml`, repo root)

| Service   | Image / build                              | Host port | Profile   | Role |
|-----------|--------------------------------------------|-----------|-----------|------|
| `db`      | `mysql:8.0`                                | — (internal 3306 only) | default | Owned DB, named volume `ubd-db-data`, healthcheck |
| `backend` | `backend/Dockerfile` (`python:3.12-slim`)  | `${BACKEND_PORT:-8000}` | default | FastAPI/uvicorn; migrate + seed on start |
| `public`  | `public/Dockerfile` (node build → nginx)   | `${PUBLIC_PORT:-8080}` | default | Public SPA + `/api` proxy → backend |
| `admin`   | `admin/Dockerfile` (node build → nginx)    | `${ADMIN_PORT:-8081}` | default | Admin SPA + `/api` proxy → backend |
| `fixture` | `nginx:alpine` + static HTML               | — (internal) | `crawler` | Deterministic test website with one offer |
| `crawler` | `crawler/Dockerfile` (`python:3.12-slim`)  | — | `crawler` | `python -m crawler run`; one-shot or loop |

- **Port 3306 is never published** to the host, avoiding a clash with the running
  `mysql-container`. Host-facing ports are configurable via `.env`.
- Services communicate over the default compose network by service name
  (`backend`, `db`, `fixture`). SPAs reach the API via nginx proxying `/api` →
  `backend:8000`; both SPAs already default `baseURL` to relative `/api`.
- `backend` `depends_on: db` with `condition: service_healthy`. `crawler`
  `depends_on` both `backend` and `fixture`. `fixture` is a standalone static
  nginx with no dependencies.

### Images

**backend** — `python:3.12-slim`, `pip install .` from `backend/`, then
`docker-entrypoint.sh`:
1. wait for db (healthcheck gates this, plus a short retry loop as belt-and-braces),
2. `alembic upgrade head`,
3. `python -m app.seed` (idempotent: admin user + categories),
4. `exec uvicorn app.main:app --host 0.0.0.0 --port 8000`.

Configuration is passed purely through environment variables (pydantic-settings
reads them): `DATABASE_URL=mysql+pymysql://root:${MYSQL_ROOT_PASSWORD}@db:3306/ubd`,
`JWT_SECRET`, `CRAWLER_API_KEY`, `SEED_ADMIN_EMAIL`, `SEED_ADMIN_PASSWORD`.

**public / admin** — multi-stage:
- stage 1 `node:20`: `npm ci` + `npm run build` → `dist/`.
- stage 2 `nginx:alpine`: copy `dist/`, add a per-service `nginx.conf` that
  serves static assets, does SPA history fallback to `index.html`, and proxies
  `location /api/ { proxy_pass http://backend:8000; }`.

**crawler** — `python:3.12-slim`, `pip install .` from `crawler/` (pulls
`httpx`, `instaloader`, etc.). `docker-entrypoint.sh` reads `CRAWL_INTERVAL_SECONDS`:
- `0` (default) → single `python -m crawler run` then exit (one-shot).
- `>0` → `while true; do python -m crawler run; sleep $CRAWL_INTERVAL_SECONDS; done`.

Config via env (`INTERNAL_API_URL=http://backend:8000`, `CRAWLER_API_KEY`,
`EXTRACTOR=heuristic`, `ACTIVE_DISCOVERY=false`). The crawler package reads config
from the environment; no `crawler/.env` file is baked into the image.

**fixture** — `nginx:alpine` serving a single static `index.html` containing a
realistic Ukrainian discount offer (title, veteran-targeted description, a
percentage, valid-from/until dates) shaped so the heuristic extractor reliably
produces one candidate offer.

### Deterministic demo flow (proves the crawler works)

1. `docker compose up -d` — core app starts; backend migrates + seeds.
2. `docker compose --profile crawler run --rm backend python -m app.demo_seed` —
   new idempotent script `backend/app/demo_seed.py` inserts a `website` source
   pointing at `http://fixture/` (only if absent).
3. `docker compose --profile crawler run --rm crawler` — one crawler pass fetches
   the fixture, extracts the offer, POSTs it to the backend as
   `created_by=crawler`, `status=pending_review`.
4. Admin panel (`:8081`, `admin@example.com` / `admin12345`) shows the pending
   offer in the moderation queue → moderator approves it.
5. Public frontend (`:8080`) now shows the approved offer.

`fixture` + `demo_seed` + `crawler` are all under the `crawler` profile, so a
plain `docker compose up` never reaches external networks or scrapes anything.

### Configuration and secrets

- Root **`.env`** (gitignored), read by compose:
  `MYSQL_ROOT_PASSWORD`, `JWT_SECRET`, `CRAWLER_API_KEY`, `SEED_ADMIN_EMAIL`,
  `SEED_ADMIN_PASSWORD`, `CRAWL_INTERVAL_SECONDS`, `BACKEND_PORT`, `PUBLIC_PORT`,
  `ADMIN_PORT`.
- Committed **`.env.example`** with safe local defaults and inline notes.
- A `.dockerignore` per build context excludes `.venv`, `node_modules`,
  `__pycache__`, `dist`, `.env`, `.pytest_cache`.

## File layout (new files)

```
docker-compose.yml
.env.example
backend/Dockerfile
backend/.dockerignore
backend/docker-entrypoint.sh
backend/app/demo_seed.py
public/Dockerfile
public/.dockerignore
public/nginx.conf
admin/Dockerfile
admin/.dockerignore
admin/nginx.conf
crawler/Dockerfile
crawler/.dockerignore
crawler/docker-entrypoint.sh
docker/fixture/index.html          # served by the fixture nginx
docker/fixture/nginx.conf          # optional; default nginx config is usually enough
README-docker.md                   # how to run (or a section appended to README.md)
```

The only application-source change is the addition of `backend/app/demo_seed.py`.

## Error handling & edge cases

- **DB not ready:** backend entrypoint relies on the compose healthcheck plus a
  bounded retry loop around `alembic upgrade` so a slow first-boot MySQL doesn't
  crash the backend.
- **Re-runs are idempotent:** `alembic upgrade head`, `app.seed`, and
  `app.demo_seed` can all run repeatedly with no duplication.
- **Port clash with `mysql-container`:** avoided by not publishing 3306; other
  host ports are override-able via `.env`.
- **Named volume persistence:** DB data survives `docker compose down`; a full
  reset is `docker compose down -v`.
- **Crawler safety:** default `CRAWL_INTERVAL_SECONDS=0` (one-shot) and the
  profile gate mean the crawler never runs unattended unless explicitly asked;
  the demo path only ever touches the internal `fixture`.

## Testing & verification

- **Build:** `docker compose build` succeeds for all default services; crawler
  profile builds too.
- **Core up:** `docker compose up -d`; `curl http://localhost:8000/api/health`
  returns `{"status":"ok"}`; public and admin load in a browser; admin login
  works with the seeded credentials.
- **End-to-end crawler demo:** run the deterministic demo flow above and confirm a
  pending offer appears in admin, then a public offer after approval.
- **Isolation:** confirm the compose stack does not touch or require the external
  `mysql-container` (stop it during verification if needed).
- No new automated unit tests are required for pure infra files; `demo_seed.py`
  gets a small idempotency test alongside the existing `test_seed.py`.

## Open decisions (defaulted, override at planning time)

- Host ports default to 8000 / 8080 / 8081.
- Crawler default mode is one-shot (`CRAWL_INTERVAL_SECONDS=0`).
- Docker run instructions live in a `README-docker.md` (vs. appending to the root
  `README.md`) — either is fine.
