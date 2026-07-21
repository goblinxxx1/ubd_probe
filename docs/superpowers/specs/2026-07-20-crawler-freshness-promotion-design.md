# Crawler Freshness + Promotion — Design

**Date:** 2026-07-20
**Track:** crawler freshness (Track 1) + promotion-link (Track 2). Track 3 (seed catalog) is out of scope.
**Branch:** `feat/crawler-freshness-promotion` (from `main`).

## Goal

Close the loop between active-search discovery and passive re-crawling so that published
crawler offers stay fresh:

1. **Promotion (Track 2):** when an admin **publishes** a crawler offer, the offer's origin
   page automatically becomes an active passive-crawl `Source`, and the offer is linked to it.
2. **Freshness (Track 1):** the passive crawler re-crawls that source each pass, re-confirming
   the offer still exists (`last_seen_at` bumped). An offer that is not re-confirmed for N days
   (default 30) is marked `expired` and drops off the public site.

The only expiry signal is the **re-crawl** — `valid_until` is deliberately ignored.

## The loop

```
active search harvests offer (source_id=None, pending_review)   [unchanged]
        │
        ▼
admin PUBLISHES offer
        │  backend: upsert Source from offer origin, link offer.source_id, last_seen_at=now
        ▼
passive crawler crawls active sources (now incl. promoted ones)
        │  re-extracts the same offer → create_offer dedup match → last_seen_at=now
        │  (also may surface NEW offers from the same vetted site → pending_review)
        ▼
freshness sweep (end of each crawler pass)
        │  published + crawler + source_id set + last_seen_at < now-Ndays → expired
        ▼
offer drops off public (public shows only published)
```

## Design decisions (resolved with user)

- **Promoted source behaves as a NORMAL passive source** — it both re-confirms the published
  offer and may surface new offers from the same (now-vetted) site, which go to moderation as
  usual. Reuses the existing passive crawl path; no "confirm-only" mode.
- **Expiry policy is time-based:** `last_seen_at < now - FRESHNESS_TTL_DAYS` (default 30). Robust
  to irregular / failed passes — a single fetch failure does not expire an offer.
- **Promotion trigger is PUBLICATION**, not discovery.

## Components

### 1. Data model (backend)

Add `Offer.last_seen_at: Mapped[datetime | None]` (nullable `DateTime`).
- Set to `now()` when an offer is created (`create_offer`).
- Alembic migration adds the column and backfills existing rows: `last_seen_at = created_at`.

No other schema change. `OfferStatus.expired` already exists (currently unused) and is what the
sweep sets.

### 2. Promotion on publish (Track 2, backend)

Hook into the publish action (`POST /api/admin/offers/{id}/publish` →
`backend/app/routers/admin.py:94` → `offer_crud.set_status`). The promotion logic lives in the
CRUD/service layer so it is covered by backend tests without HTTP. It fires **only on the
transition to `published`** (not on reject or any other status change).

On publish, **if** all hold:
- `offer.created_by == CreatedBy.crawler`
- `offer.source_id is None`
- the offer has a **fetchable article page**: `offer.article_url` (falling back to
  `offer.site_url`) is a valid `http(s)` URL

then:
1. **Upsert** a `Source` by `(type=website, normalized url_or_handle)`:
   - `url_or_handle = normalize(offer.article_url or offer.site_url)` — the offer's actual page,
     so the passive fetcher re-fetches the same page.
   - `name = offer.provider` — see §3 (makes the re-crawl reproduce the same `content_hash`).
   - `is_active = True`, `created_by = CreatedBy.crawler`.
   - Idempotent: if a source with the same `(type, url_or_handle)` exists, reuse it (and ensure
     `is_active=True`); do not create a duplicate.
2. Set `offer.source_id = source.id`.
3. Set `offer.last_seen_at = now`.

**Unique-constraint safety:** `Offer` has `UniqueConstraint(source_id, content_hash)`. When the
promoted source already existed (idempotent reuse) a prior passive crawl may already hold a row
with the same `(source.id, offer.content_hash)`. Before linking, check for such a row; if one
exists, do **not** violate the constraint — leave the offer's `source_id` unset (the existing
row already represents that offer under the source) or link only when free. The common case
(brand-new source at publish) is always free.

Offers **without** a fetchable article page are published normally but **not** promoted, and
therefore **never expire** (freshness only applies to what can be re-crawled). V1 handles
`website` origins only; `telegram` promotion is a possible later extension.

New source CRUD helper: `get_or_create_source_by_ref(db, type, url_or_handle, name, created_by)`.
URL normalization reuses the crawler's canonical form conceptually; backend uses its own small
normalizer (lowercased host, no trailing slash, strip `utm_*`/fragment) consistent with how the
crawler produced `article_url`.

> **Note:** in the crawler's data model (`crawler/crawler/extract/heuristic.py`), `site_url` is
> the bare origin (`scheme://netloc`, path stripped) while `article_url` is the actual page the
> offer block was found on. `content_hash` is computed from that page's content, so `article_url`
> — not `site_url` — is the correct promotion key for reproducing the same hash on re-crawl.

### 3. Re-crawl matching (the technical crux) ⚠️

For the passive re-crawl to bump `last_seen_at` on the *same* published offer, the re-submitted
offer must dedup-match it. Identity is `content_hash = sha256(title | provider | body)`
(`crawler/dedup.py`). In the passive path the extractor is called as
`extract(item, source["name"], cats)` — i.e. **provider = source name**. Therefore promotion sets
`Source.name = offer.provider` and `Source.url_or_handle = the offer's article page`, so the passive
extractor over the unchanged page yields the same `title | provider | body` → the same
`content_hash`. Because the published offer now has `source_id = source.id`, the passive submission
(same `source_id`, same `content_hash`) matches via `create_offer`'s `(source_id, content_hash)`
dedup branch.

**Fallback:** `create_offer` also dedups globally by `target_url`; a re-crawl that reproduces the
same `target_url` bumps `last_seen_at` even if the hash drifts.

**Accepted consequence:** if the origin page changes materially (different title/body), the hash
diverges and the passive crawl creates a **new** `pending_review` offer (a fresh candidate) while
the stale published one is not re-confirmed and expires after N days. This is correct behaviour —
the offer changed.

### 4. Freshness bump (Track 1, backend)

In `create_offer` (`backend/app/crud/offer.py`), when the dedup logic returns an **existing**
offer — both the `(source_id, content_hash)` branch and the `target_url` branch — set
`existing.last_seen_at = now` and commit. Every "seen again on a source" is a confirmation.

(`create_offer` is only called for crawler submissions via the internal API; admin-created offers
go through a separate path and are unaffected.)

### 5. Expiry sweep (backend + crawler)

New internal endpoint: `POST /api/internal/offers/expire-stale` with body `{older_than_days: int}`.
It sets `status = expired` for every offer where:
- `status == published`
- `created_by == CreatedBy.crawler`
- `source_id IS NOT NULL`   (only re-crawlable/promoted offers)
- `last_seen_at < now - older_than_days`

Returns `{"expired": <count>}`. Idempotent (already-expired rows are excluded by `status==published`).

The crawler calls this endpoint once at the **end of each pass** (`Runner.run`), passing the config
value, and records `expired` in the run summary `{sources, offers, suggestions, expired, errors}`.

Rationale: the crawler is the cadence driver (there is no backend scheduler); the expiry logic
itself lives in the backend, which owns the DB.

### 6. Config

Crawler config knob `FRESHNESS_TTL_DAYS` (default `30`), wired through
`_RawSettings → Config → load_config` and documented in `.env.example`. Passed as `older_than_days`
in the sweep call. No backend config change (threshold travels in the request).

## Out of scope (deliberate)

- **Track 3** — seed catalog of trusted sources.
- **Telegram-origin promotion** (v1 = website only).
- **Expiring non-promoted offers** (offers with no re-crawlable source never expire).
- **`valid_until`** as an expiry signal (ignored by design).

## Testing

**Backend:**
- Publishing a crawler offer with a website origin: upserts a `Source` (name=provider,
  url_or_handle=normalized article_url, active), sets `offer.source_id`, sets `last_seen_at`.
- Idempotent promotion: two published offers sharing an origin → one source; re-publish reuses it.
- No promotion when: `created_by != crawler`, `source_id` already set, or no valid `article_url`
  (falling back to `site_url`).
- `create_offer` dedup (both branches) bumps `last_seen_at` on the existing offer.
- Sweep expires only rows matching all four conditions; leaves published-but-fresh, un-promoted,
  admin, and non-published rows untouched; returns the correct count.
- Alembic migration adds the column and backfills `last_seen_at = created_at`.

**Crawler:**
- `Runner.run` calls `expire-stale` once with the configured TTL and folds `expired` into the summary.
- End-to-end matching: a fake origin page harvested → promoted (source name=provider) → passive
  re-crawl of that source reproduces the same `content_hash` → dedup match (asserted).
- `FRESHNESS_TTL_DAYS` config default and override.

## Files (anticipated)

- `backend/app/models/offer.py` — `last_seen_at` column.
- `backend/alembic/versions/*` — migration (add column + backfill).
- `backend/app/crud/offer.py` — set `last_seen_at` on create and on dedup match.
- `backend/app/crud/source.py` — `get_or_create_source_by_ref`.
- `backend/app/routers/admin.py` (or a service helper) — promotion on publish.
- `backend/app/routers/internal.py` + `backend/app/crud/offer.py` — `expire-stale` endpoint + query.
- `backend/app/core/` — small URL normalizer for source refs.
- `crawler/crawler/config.py` — `FRESHNESS_TTL_DAYS`.
- `crawler/crawler/runner.py` — call `expire-stale`, extend summary.
- `crawler/crawler/api_client.py` — `expire_stale(older_than_days)` client method.
- `crawler/.env.example` — document `FRESHNESS_TTL_DAYS`.
- Tests across `backend/tests/` and `crawler/tests/`.
