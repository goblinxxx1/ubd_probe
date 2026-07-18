# UBD Crawler

Scheduled service that crawls sources (website / telegram / instagram / facebook)
and extracts candidate offers into moderation — all via the backend internal API
(`X-API-Key`). Optional Level-2 active search additionally fetches found
website/telegram pages and, when a provider can be attributed, submits offers
straight to moderation (source suggestions are a by-product). See
`docs/superpowers/specs/2026-07-12-crawler-design.md` and
`docs/superpowers/specs/2026-07-18-crawler-active-harvest-design.md`.

## Setup

**Note:** run all commands below from this `crawler/` directory — the config loads `.env` relative to your current working directory, so running from elsewhere silently falls back to placeholder defaults.

    python -m venv .venv
    .venv/Scripts/python.exe -m pip install -e ".[dev]"
    copy .env.example .env   # then edit .env

## Run once (manual / debug)

    .venv/Scripts/python.exe -m crawler run

## Run on a schedule (Windows)

    .\register-task.ps1 -IntervalMinutes 60

## Tests

    .venv/Scripts/python.exe -m pytest -q

## Configuration (.env)

- `INTERNAL_API_URL`, `CRAWLER_API_KEY` — backend internal API.
- `EXTRACTOR=heuristic` — offline extractor (only option shipped).
- `ACTIVE_DISCOVERY=false` — Level-2 active search is opt-in (off by default).
  When on, found website/telegram pages are fetched and, if a provider can be
  attributed, offers are submitted straight to moderation (source suggestions
  are a by-product). Instagram/Facebook results are ignored for now.
- `ACTIVE_FETCH_BUDGET=20` — max page fetches per active-search pass (`0` disables).
- `INSTAGRAM_ACCOUNTS`, `FACEBOOK_ACCOUNTS` — `user:pass` pairs, comma-separated.
  Credentials live only here, never in the database or repo.
- `PROXIES` — optional per-platform proxy.

Zero-cost runtime: no cloud LLM, no paid services required.
