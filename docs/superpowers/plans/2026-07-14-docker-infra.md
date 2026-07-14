# Application Docker Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the whole UBD application up with `docker compose up` in a production-like shape, with a gated, deterministic crawler demo that proves end-to-end data flow.

**Architecture:** One root `docker-compose.yml`. Core services (own MySQL, FastAPI/uvicorn backend, two nginx-served Vue SPAs) start on a plain `up`. A `crawler` compose profile adds an offline fixture website + the crawler (one-shot or scheduled loop). Backend migrates and seeds on start; a demo-seed script wires the fixture source so a single crawler pass yields a `pending_review` offer visible in admin.

**Tech Stack:** Docker Compose, `mysql:8.0`, `python:3.12-slim` (FastAPI/uvicorn/alembic, httpx/instaloader), `node:20-alpine` (Vite build) → `nginx:alpine`.

## Global Constraints

- **Do not modify application code** except adding `backend/app/demo_seed.py`. Infra files only otherwise.
- **Do not publish MySQL port 3306** to the host (avoids clash with the external `mysql-container`).
- **Do not reuse/touch** the external `mysql-container` or `streamtower` setup — this compose owns its own `db` service + named volume `ubd-db-data`.
- **Crawler is profile-gated** (`profiles: ["crawler"]`) — a plain `docker compose up` must never start the crawler or fixture, and must never reach external networks.
- **Search-based active discovery is OUT of scope** — `ACTIVE_DISCOVERY=false`, no search provider.
- **Shell scripts must use LF line endings** (enforced via `.gitattributes`) — CRLF breaks `#!/bin/sh` inside Linux containers.
- Host ports via `.env`: `BACKEND_PORT=8000`, `PUBLIC_PORT=8080`, `ADMIN_PORT=8081`.
- Backend/crawler configuration is passed **only through environment variables** (pydantic-settings reads them); no `.env` file is baked into any image.
- **Note on "tests":** most tasks here produce infra files with no meaningful unit test. Their verification is `docker compose build` / `up` / `curl` with expected output — treated as the task's test cycle. Only Task 5 (`demo_seed.py`) is real Python TDD.
- Run all `docker compose` commands from the repo root (`D:\ubd_probe`).

---

### Task 1: Compose skeleton — `db` service, env, git hygiene

**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `.gitattributes`
- Modify: `.gitignore`

**Interfaces:**
- Produces: compose network + `db` service reachable in-network as host `db:3306`, schema `ubd`, root password from `${MYSQL_ROOT_PASSWORD}`; named volume `ubd-db-data`; a `db` healthcheck later tasks gate on with `condition: service_healthy`.

- [ ] **Step 1: Create `.gitattributes`** (guarantee LF for shell scripts)

```gitattributes
* text=auto
*.sh text eol=lf
docker-entrypoint.sh text eol=lf
```

- [ ] **Step 2: Append Docker entries to `.gitignore`**

Add these lines to the existing `.gitignore`:

```gitignore
# Docker
.env
```

(`.env.example` stays tracked; the real `.env` is ignored.)

- [ ] **Step 3: Create `.env.example`**

```dotenv
# Copy to .env and adjust. `.env` is gitignored.

# Database (never published to host; internal to the compose network)
MYSQL_ROOT_PASSWORD=my-secret-pw

# Backend
JWT_SECRET=dev-jwt-secret-change-me-0123456789abcdef-please-rotate
CRAWLER_API_KEY=dev-crawler-api-key-change-me-0123456789abcdef
SEED_ADMIN_EMAIL=admin@example.com
SEED_ADMIN_PASSWORD=admin12345

# Crawler: 0 = single one-shot pass then exit; >0 = loop every N seconds
CRAWL_INTERVAL_SECONDS=0

# Host ports
BACKEND_PORT=8000
PUBLIC_PORT=8080
ADMIN_PORT=8081
```

- [ ] **Step 4: Create `docker-compose.yml` with just the `db` service**

```yaml
services:
  db:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      MYSQL_DATABASE: ubd
    volumes:
      - ubd-db-data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-uroot", "-p${MYSQL_ROOT_PASSWORD}", "--silent"]
      interval: 5s
      timeout: 5s
      retries: 20
    # NOTE: 3306 intentionally NOT published (clashes with external mysql-container)

volumes:
  ubd-db-data:
```

- [ ] **Step 5: Verify compose is valid and db comes up healthy**

```bash
cp .env.example .env   # if no .env yet
docker compose config >/dev/null && echo "CONFIG OK"
docker compose up -d db
# wait for healthy, then confirm schema exists
docker compose exec db mysql -uroot -p"$(grep MYSQL_ROOT_PASSWORD .env | cut -d= -f2)" -e "SHOW DATABASES;"
```

Expected: `CONFIG OK`; `SHOW DATABASES` lists `ubd`. `docker compose ps` shows `db` as `healthy`.

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml .env.example .gitattributes .gitignore
git commit -m "feat(infra): compose skeleton with owned MySQL db service"
```

---

### Task 2: Backend image — migrate, seed, serve

**Files:**
- Create: `backend/Dockerfile`
- Create: `backend/.dockerignore`
- Create: `backend/docker-entrypoint.sh`
- Modify: `docker-compose.yml` (add `backend` service)

**Interfaces:**
- Consumes: `db` service (healthy) from Task 1.
- Produces: `backend` service reachable in-network as `http://backend:8000`; all API routes under `/api`; `GET /api/health` → `{"status":"ok"}`. On start it runs `alembic upgrade head` then `python -m app.seed` (idempotent).

- [ ] **Step 1: Create `backend/.dockerignore`**

```gitignore
.venv
__pycache__
*.pyc
.pytest_cache
ubd_backend.egg-info
.env
tests
```

- [ ] **Step 2: Create `backend/docker-entrypoint.sh`** (LF endings)

```sh
#!/bin/sh
set -e

echo "[entrypoint] waiting for DB + running migrations..."
until alembic upgrade head; do
  echo "[entrypoint] alembic failed (db not ready?), retrying in 2s..."
  sleep 2
done

echo "[entrypoint] seeding baseline data..."
python -m app.seed

echo "[entrypoint] starting uvicorn on :8000"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- [ ] **Step 3: Create `backend/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app

# Install the package (pyproject-driven). Copy metadata + source, then install.
COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN pip install --no-cache-dir .

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
```

- [ ] **Step 4: Add the `backend` service to `docker-compose.yml`** (inside `services:`)

```yaml
  backend:
    build: ./backend
    depends_on:
      db:
        condition: service_healthy
    environment:
      DATABASE_URL: mysql+pymysql://root:${MYSQL_ROOT_PASSWORD}@db:3306/ubd
      JWT_SECRET: ${JWT_SECRET}
      CRAWLER_API_KEY: ${CRAWLER_API_KEY}
      SEED_ADMIN_EMAIL: ${SEED_ADMIN_EMAIL}
      SEED_ADMIN_PASSWORD: ${SEED_ADMIN_PASSWORD}
    ports:
      - "${BACKEND_PORT:-8000}:8000"
```

- [ ] **Step 5: Build and bring up backend, verify health + seed**

```bash
docker compose up -d --build backend
sleep 5
curl -s http://localhost:8000/api/health
docker compose exec db mysql -uroot -p"$(grep MYSQL_ROOT_PASSWORD .env | cut -d= -f2)" \
  -e "USE ubd; SELECT email, role FROM admin_users;"
```

Expected: health returns `{"status":"ok"}`; `admin_users` contains `admin@example.com | super_admin`. Re-running `docker compose up -d backend` must not error or duplicate the admin (idempotent seed).

- [ ] **Step 6: Commit**

```bash
git add backend/Dockerfile backend/.dockerignore backend/docker-entrypoint.sh docker-compose.yml
git commit -m "feat(infra): backend image with migrate+seed entrypoint"
```

---

### Task 3: Public SPA image — nginx static + `/api` proxy

**Files:**
- Create: `public/Dockerfile`
- Create: `public/.dockerignore`
- Create: `public/nginx.conf`
- Modify: `docker-compose.yml` (add `public` service)

**Interfaces:**
- Consumes: `backend` service (`http://backend:8000`).
- Produces: `public` service serving the built SPA on container port 80, published to `${PUBLIC_PORT}`; proxies `/api/*` → `backend:8000` (preserving the `/api` prefix, since the SPA calls relative `/api`).

- [ ] **Step 1: Create `public/.dockerignore`**

```gitignore
node_modules
dist
.env
```

- [ ] **Step 2: Create `public/nginx.conf`**

```nginx
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    # Preserve the /api prefix (no trailing slash on proxy_pass).
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # SPA history fallback.
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

- [ ] **Step 3: Create `public/Dockerfile`**

```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

- [ ] **Step 4: Add the `public` service to `docker-compose.yml`**

```yaml
  public:
    build: ./public
    depends_on:
      - backend
    ports:
      - "${PUBLIC_PORT:-8080}:80"
```

- [ ] **Step 5: Build, bring up, verify SPA + proxied API**

```bash
docker compose up -d --build public
sleep 3
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/          # expect 200
curl -s http://localhost:8080/api/health                                 # expect {"status":"ok"} via proxy
```

Expected: `/` returns 200 and serves `index.html`; `/api/health` proxied through nginx returns `{"status":"ok"}`.

- [ ] **Step 6: Commit**

```bash
git add public/Dockerfile public/.dockerignore public/nginx.conf docker-compose.yml
git commit -m "feat(infra): public SPA image served by nginx with /api proxy"
```

---

### Task 4: Admin SPA image — nginx static + `/api` proxy

**Files:**
- Create: `admin/Dockerfile`
- Create: `admin/.dockerignore`
- Create: `admin/nginx.conf`
- Modify: `docker-compose.yml` (add `admin` service)

**Interfaces:**
- Consumes: `backend` service (`http://backend:8000`).
- Produces: `admin` service serving the admin SPA on container port 80, published to `${ADMIN_PORT}`; proxies `/api/*` → `backend:8000`.

- [ ] **Step 1: Create `admin/.dockerignore`** (identical content to public)

```gitignore
node_modules
dist
.env
```

- [ ] **Step 2: Create `admin/nginx.conf`** (identical structure to public — repeated in full)

```nginx
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

- [ ] **Step 3: Create `admin/Dockerfile`** (identical structure to public — repeated in full)

```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

- [ ] **Step 4: Add the `admin` service to `docker-compose.yml`**

```yaml
  admin:
    build: ./admin
    depends_on:
      - backend
    ports:
      - "${ADMIN_PORT:-8081}:80"
```

- [ ] **Step 5: Build, bring up, verify SPA + login flow**

```bash
docker compose up -d --build admin
sleep 3
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8081/           # expect 200
# login through the proxy with seeded creds:
curl -s -X POST http://localhost:8081/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"admin12345"}'
```

Expected: `/` returns 200; login returns a JSON body with an access token (not 401). If the login route path differs, confirm it against `backend/app/routers/auth.py` and adjust the curl path only (no app changes).

- [ ] **Step 6: Commit**

```bash
git add admin/Dockerfile admin/.dockerignore admin/nginx.conf docker-compose.yml
git commit -m "feat(infra): admin SPA image served by nginx with /api proxy"
```

---

### Task 5: Demo-seed script (real TDD)

**Files:**
- Create: `backend/app/demo_seed.py`
- Create: `backend/tests/test_demo_seed.py`

**Interfaces:**
- Consumes: `app.core.db.SessionLocal`, `app.models.source.Source`, `app.models.enums.SourceType`/`CreatedBy`.
- Produces: `demo_seed(db) -> Source` and `main()`. Inserts exactly one `website` source `http://fixture/` named `Demo Fixture`, `is_active=True`, `created_by=admin`; idempotent on `url_or_handle`. Runnable as `python -m app.demo_seed`.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_demo_seed.py`

```python
from app.demo_seed import demo_seed, FIXTURE_URL
from app.models.source import Source
from app.models.enums import SourceType, CreatedBy


def test_demo_seed_inserts_fixture_source(db_session):
    src = demo_seed(db_session)
    assert src.url_or_handle == FIXTURE_URL
    assert src.type == SourceType.website
    assert src.is_active is True
    assert src.created_by == CreatedBy.admin


def test_demo_seed_is_idempotent(db_session):
    demo_seed(db_session)
    demo_seed(db_session)  # second run must not duplicate
    rows = db_session.query(Source).filter(Source.url_or_handle == FIXTURE_URL).all()
    assert len(rows) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `backend/`, with `mysql-container` up for `ubd_test`):
```bash
./.venv/Scripts/python.exe -m pytest tests/test_demo_seed.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.demo_seed'`.

- [ ] **Step 3: Write minimal implementation** — `backend/app/demo_seed.py`

```python
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models.source import Source
from app.models.enums import CreatedBy, SourceType

FIXTURE_URL = "http://fixture/"


def demo_seed(db: Session) -> Source:
    existing = db.query(Source).filter(Source.url_or_handle == FIXTURE_URL).first()
    if existing:
        return existing
    src = Source(
        name="Demo Fixture",
        type=SourceType.website,
        url_or_handle=FIXTURE_URL,
        is_active=True,
        created_by=CreatedBy.admin,
    )
    db.add(src)
    db.commit()
    db.refresh(src)
    return src


def main() -> None:
    db = SessionLocal()
    try:
        demo_seed(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_demo_seed.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/demo_seed.py backend/tests/test_demo_seed.py
git commit -m "feat(backend): idempotent demo_seed for the fixture crawler source"
```

---

### Task 6: Fixture website service (deterministic offer)

**Files:**
- Create: `docker/fixture/index.html`
- Modify: `docker-compose.yml` (add `fixture` service, `crawler` profile)

**Interfaces:**
- Produces: `fixture` service (standalone `nginx:alpine`, no deps) serving one HTML page at in-network `http://fixture/`, containing a block the heuristic extractor turns into exactly one offer candidate. Under the `crawler` profile only.

- [ ] **Step 1: Create `docker/fixture/index.html`**

The heuristic extractor triggers on tokens like `знижк`/`%`/`діє до`, reads text from `article`/`li`/`p` blocks ≥30 chars, and matches target categories on a 5-char stem (`Ветеран` → `ветер`). This block satisfies all three:

```html
<!doctype html>
<html lang="uk">
<head><meta charset="utf-8"><title>Demo Fixture — Знижки</title></head>
<body>
  <h1>Демонстраційні пропозиції</h1>
  <article>
    Знижка 20% для ветеранів у нашому кафе. Спеціальна пропозиція для УБД.
    Діє до 31.12.2026. Пред'явіть посвідчення при замовленні.
  </article>
</body>
</html>
```

- [ ] **Step 2: Add the `fixture` service to `docker-compose.yml`**

```yaml
  fixture:
    image: nginx:alpine
    profiles: ["crawler"]
    volumes:
      - ./docker/fixture:/usr/share/nginx/html:ro
```

- [ ] **Step 3: Verify the fixture serves the offer HTML (in-network)**

```bash
docker compose --profile crawler up -d fixture
# curl from within the compose network via a throwaway container:
docker compose run --rm --entrypoint sh fixture -c "wget -qO- http://fixture/ | head -20" 2>/dev/null \
  || docker run --rm --network "$(docker compose ls -q >/dev/null 2>&1; basename "$PWD")_default" curlimages/curl -s http://fixture/
```
Expected: HTML output containing `Знижка 20% для ветеранів`. (Simplest fallback: `docker compose exec fixture cat /usr/share/nginx/html/index.html` to confirm the mount.)

- [ ] **Step 4: Commit**

```bash
git add docker/fixture/index.html docker-compose.yml
git commit -m "feat(infra): deterministic offline fixture website under crawler profile"
```

---

### Task 7: Crawler image + end-to-end demo

**Files:**
- Create: `crawler/Dockerfile`
- Create: `crawler/.dockerignore`
- Create: `crawler/docker-entrypoint.sh`
- Modify: `docker-compose.yml` (add `crawler` service, `crawler` profile)

**Interfaces:**
- Consumes: `backend` (`http://backend:8000`, `CRAWLER_API_KEY`), `fixture` (`http://fixture/`), and the `Demo Fixture` source from Task 5's `demo_seed`.
- Produces: `crawler` service that runs `python -m crawler run` once (`CRAWL_INTERVAL_SECONDS=0`, default) or loops (`>0`). Under the `crawler` profile only.

- [ ] **Step 1: Create `crawler/.dockerignore`**

```gitignore
.venv
__pycache__
*.pyc
.pytest_cache
ubd_crawler.egg-info
.env
tests
```

- [ ] **Step 2: Create `crawler/docker-entrypoint.sh`** (LF endings)

```sh
#!/bin/sh
set -e

INTERVAL="${CRAWL_INTERVAL_SECONDS:-0}"
if [ "$INTERVAL" -gt 0 ] 2>/dev/null; then
  echo "[crawler] scheduled loop every ${INTERVAL}s"
  while true; do
    python -m crawler run || echo "[crawler] run failed, continuing"
    sleep "$INTERVAL"
  done
else
  echo "[crawler] single one-shot pass"
  exec python -m crawler run
fi
```

- [ ] **Step 3: Create `crawler/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app

COPY pyproject.toml ./
COPY crawler ./crawler
RUN pip install --no-cache-dir .

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
```

- [ ] **Step 4: Add the `crawler` service to `docker-compose.yml`**

```yaml
  crawler:
    build: ./crawler
    profiles: ["crawler"]
    depends_on:
      - backend
      - fixture
    environment:
      INTERNAL_API_URL: http://backend:8000
      CRAWLER_API_KEY: ${CRAWLER_API_KEY}
      EXTRACTOR: heuristic
      ACTIVE_DISCOVERY: "false"
      CRAWL_INTERVAL_SECONDS: ${CRAWL_INTERVAL_SECONDS:-0}
```

- [ ] **Step 5: Run the full deterministic demo end-to-end**

```bash
# Ensure core app is up:
docker compose up -d --build
# Seed the fixture source (idempotent):
docker compose --profile crawler run --rm --entrypoint python backend -m app.demo_seed
# Build + run one crawler pass:
docker compose --profile crawler run --rm --build crawler
# Confirm a pending offer landed:
docker compose exec db mysql -uroot -p"$(grep MYSQL_ROOT_PASSWORD .env | cut -d= -f2)" \
  -e "USE ubd; SELECT id, title, status, created_by FROM offers;"
```

Expected: crawler logs `done:` with a non-zero found/submitted count; `offers` contains one row with `status=pending_review`, `created_by=crawler`, and a title derived from the fixture text. Re-running is safe (backend dedups on `content_hash`).

- [ ] **Step 6: Commit**

```bash
git add crawler/Dockerfile crawler/.dockerignore crawler/docker-entrypoint.sh docker-compose.yml
git commit -m "feat(infra): crawler image (one-shot/loop) with end-to-end fixture demo"
```

---

### Task 8: Run docs + final whole-stack verification

**Files:**
- Create: `README-docker.md`

**Interfaces:**
- Consumes: everything from Tasks 1–7.
- Produces: a single documented run flow.

- [ ] **Step 1: Create `README-docker.md`**

````markdown
# Running UBD in Docker

Prod-like local stack: owned MySQL + FastAPI backend + public/admin SPAs behind
nginx. The crawler and its offline fixture are gated behind the `crawler` profile.

## First run

```bash
cp .env.example .env      # adjust secrets/ports if desired
docker compose up -d --build
```

- Public:  http://localhost:8080
- Admin:   http://localhost:8081  (login: `admin@example.com` / `admin12345`)
- API:     http://localhost:8000/api/health

The backend migrates and seeds automatically on start. MySQL is internal only
(port 3306 is not published, to avoid clashing with other local MySQL containers).

## Seeing the crawler work (deterministic offline demo)

```bash
# 1. Register the fixture website as a crawl source (idempotent):
docker compose --profile crawler run --rm --entrypoint python backend -m app.demo_seed
# 2. Run one crawler pass against the offline fixture:
docker compose --profile crawler run --rm crawler
```

A pending offer now appears in the admin moderation queue. Approve it, and it
shows up on the public site.

## Scheduled crawler (optional)

Set `CRAWL_INTERVAL_SECONDS=3600` in `.env`, then:

```bash
docker compose --profile crawler up -d crawler   # loops every hour
```

## Reset

```bash
docker compose down       # keep data
docker compose down -v    # wipe the database volume
```
````

- [ ] **Step 2: Final whole-stack verification (clean slate)**

```bash
docker compose down -v
docker compose up -d --build
sleep 8
curl -s http://localhost:8000/api/health                 # {"status":"ok"}
curl -s -o /dev/null -w "public=%{http_code}\n" http://localhost:8080/
curl -s -o /dev/null -w "admin=%{http_code}\n"  http://localhost:8081/
docker compose --profile crawler run --rm --entrypoint python backend -m app.demo_seed
docker compose --profile crawler run --rm crawler
docker compose exec db mysql -uroot -p"$(grep MYSQL_ROOT_PASSWORD .env | cut -d= -f2)" \
  -e "USE ubd; SELECT status, COUNT(*) FROM offers GROUP BY status;"
```

Expected: health ok; both SPAs 200; after the crawler pass, `offers` shows one
`pending_review` row. Confirm a plain `docker compose up` (without `--profile
crawler`) does NOT start `crawler` or `fixture` (`docker compose ps` lists
neither).

- [ ] **Step 3: Commit**

```bash
git add README-docker.md
git commit -m "docs(infra): how to run the UBD stack and crawler demo in Docker"
```

---

## Self-Review

**Spec coverage:**
- Prod-like core `up` → Tasks 1–4. ✅
- Owned MySQL + named volume, 3306 unpublished → Task 1. ✅
- Backend migrate+seed on start → Task 2. ✅
- SPAs static behind nginx + `/api` proxy → Tasks 3–4. ✅
- Crawler one-shot + loop, profile-gated → Task 7. ✅
- Deterministic offline fixture demo → Tasks 5 (demo_seed) + 6 (fixture) + 7 (run). ✅
- Config/secrets via `.env`, `.env.example` committed, `.dockerignore` per context → Tasks 1–4, 7. ✅
- LF shell scripts → Task 1 `.gitattributes`. ✅
- Run docs → Task 8. ✅
- Non-goals (search discovery, dev/hot-reload, running tests in Docker) → not implemented, as intended. ✅

**Placeholder scan:** No TBD/TODO; every file's full content is inline; the one path that may vary (auth login route in Task 4 Step 5) is called out with how to confirm it. ✅

**Type consistency:** `demo_seed(db) -> Source` and `FIXTURE_URL="http://fixture/"` are defined in Task 5 and reused consistently in Tasks 6–8; the fixture in-network host `fixture` matches `demo_seed`'s URL and the crawler's `depends_on`. Service names (`db`/`backend`/`public`/`admin`/`fixture`/`crawler`), ports (8000/8080/8081), and env var names match across all tasks and the `.env.example`. ✅
