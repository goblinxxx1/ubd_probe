# Running UBD in Docker

Prod-like local stack: owned MySQL + FastAPI backend + public/admin SPAs behind
nginx. The crawler and its offline fixture are gated behind the `crawler` profile.

## First run

```bash
cp .env.example .env      # adjust secrets/ports if desired
docker compose up -d --build
```

- Public:  http://localhost:8080
- Admin:   http://localhost:8082  (login: `admin@example.com` / `admin12345`)
- API:     http://localhost:8000/api/health

The backend migrates and seeds automatically on start. MySQL is internal only
(port 3306 is not published, to avoid clashing with other local MySQL containers).

> **Ports:** defaults are `8080` (public), `8082` (admin), `8000` (api). Admin
> uses `8082` because `8081` is often already taken locally. Override any of them
> via `PUBLIC_PORT` / `ADMIN_PORT` / `BACKEND_PORT` in `.env`.

## Seeing the crawler work (deterministic offline demo)

```bash
# 1. Register the fixture website as a crawl source (idempotent).
#    The backend image has an entrypoint script, so override it to run the seed:
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

## Search discovery (crawler, Track A)

The crawler can find NEW candidate sources by searching the web (DuckDuckGo).
Results go to the moderation queue (`suggested_sources`), not straight to offers.

Enable via crawler env: `ACTIVE_DISCOVERY=true`. Keywords/limits live there too
(`SEARCH_KEYWORDS`, `SEARCH_RESULTS_PER_KEYWORD`, `SEARCH_MIN_DELAY`) — see
`crawler/.env.example`.

**Anti-throttle:** to avoid getting the single outbound IP flagged, the DuckDuckGo
search hits **one** backend per query, round-robin across the `SEARCH_BACKENDS` pool
(`google,startpage,duckduckgo,yahoo,brave`), with a per-backend cooldown on failure
and a global backoff when all are cooled. The crawler persists this anti-throttle
state (per-backend cooldown, keyword cache, rotation cursor, global backoff) to
`/data/search_state.json` on the `ubd-crawler-state` volume, so blocked-backend
cooldowns and cached keyword results survive container restarts. Override the path
with `SEARCH_STATE_PATH`.

**First run manually**, then schedule:

```bash
docker compose --profile crawler run --rm crawler          # one manual pass
# then, for scheduled runs, set CRAWL_INTERVAL_SECONDS>0 and:
docker compose --profile crawler up -d crawler
```

### Outbound network address (firewall exception)

The crawler runs in Docker; its egress is NAT'd through the host, so the router
sees the **host LAN IP** as the source. On this machine that is **`192.168.20.69`**
(gateway `192.168.20.1`). Give this address to the network admin for the router's
outbound exception. Note: it is a DHCP/Wi-Fi address and can change — reserve a
static/DHCP-reserved IP so the exception stays valid. Find it anytime with:

```powershell
Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway }
```

Destination domains the crawler contacts during search (for reference):
`duckduckgo.com`, `links.duckduckgo.com`, `html.duckduckgo.com`, plus any site it discovers.

### SearXNG (Track B)

A self-hosted metasearch engine that aggregates several upstream engines (more
resilient than a single one). It runs as the `searxng` service under the `crawler`
profile. Enable it by adding `searxng` to `SEARCH_PROVIDERS` (alone or with
`duckduckgo`):

```bash
docker compose --profile crawler up -d searxng        # starts SearXNG
docker compose --profile crawler run --rm \
  -e ACTIVE_DISCOVERY=true -e SEARCH_PROVIDERS=searxng crawler
```

Set `SEARXNG_SECRET` in `.env` for a stable secret key. With SearXNG enabled,
outbound traffic (from the same host address `192.168.20.69`) additionally reaches
the upstream engines SearXNG queries (Google/Bing/DuckDuckGo/Brave/Qwant/…).

## Reset

```bash
docker compose down       # keep data
docker compose down -v    # wipe the database volume
```
