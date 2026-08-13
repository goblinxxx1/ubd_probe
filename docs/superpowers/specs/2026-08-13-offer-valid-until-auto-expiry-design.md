# Design — Auto-hide offers past `valid_until` from the public site

Date: 2026-08-13
Status: approved (approach), pending implementation
Track: backend (own branch off `main`)

## Problem

An offer with a `valid_until` ("діє до") date in the past stays visible on the
public site. The public listing filters only by `status == published`
([backend/app/routers/public.py:41]); `valid_until` is never checked, so an
expired discount keeps showing.

`valid_until` already exists on `Offer` and the crawler already extracts "діє до
DD.MM" ([crawler/crawler/extract/heuristic.py:52]). There is an existing
`expire_stale()` but it is **freshness**-based (`last_seen_at`), unrelated to
`valid_until`.

## Decision: query-time date filter (soft hide), not a status flip

The public read path excludes offers whose `valid_until` has passed. The offer
stays `status == published` in the DB — it is simply time-gated out of public
responses.

Rejected: a scheduled job flipping `published → expired` by date. Reasons the
soft filter wins:
- **Immediate** — hidden on the next request, no job latency.
- **Reversible** — if an admin extends `valid_until` (or it was wrong), the offer
  reappears automatically; a status flip would need an "un-expire" path.
- **No churn / no scheduler** — does not fight the existing freshness
  `expire_stale`.
- Applies to **all** published offers (crawler and admin-created alike).

## Semantics

- An offer is valid **through** `valid_until` inclusive; it disappears the **next
  day**. Predicate: show when `valid_until IS NULL OR valid_until >= today`.
- `today` = `date.today()` on the server. (Sub-day timezone edge at midnight is
  acceptable; dates are UA business dates.)
- `valid_until IS NULL` → no end date → always shown (unchanged).

## Components

### 1. Backend — public read paths (`backend/app/crud/offer.py`)

- **`list_offers`**: when called for the public listing, add
  `Offer.valid_until.is_(None) | (Offer.valid_until >= today)`. Introduce a flag
  (e.g. `hide_expired: bool = False`) so admin listing is unaffected; the public
  router passes `hide_expired=True`. (Admin must still see everything.)
- **`get_offer`**: add the same date gate when `published_only=True`
  (public detail). Preview (`published_only=False`) bypasses it, so admins can
  still open an expired offer via the preview link.
  ([public.py:53] already passes `published_only=not preview`.)
- **`list_distinct_locations`**: apply the same date predicate so the public
  location facet does not advertise a city that only an expired offer serves.

### 2. Admin — informational badge (no status change)

- `OfferAdminOut` (or the admin list rendering) surfaces an `is_expired`
  computed from `valid_until < today`. Admin shows a "протерміновано" badge so a
  moderator understands why a `published` offer is not on the public site. Status
  stays `published`; nothing is mutated.

## Error handling / edge cases

- `valid_until IS NULL` → always visible.
- Offer with `valid_until == today` → still visible (inclusive).
- Admin listing / counts → unchanged (no `hide_expired`).
- Preview link to an expired offer → still viewable (moderation).
- No migration (uses the existing `valid_until` column).

## Testing (TDD)

- **crud/endpoint** (`test_offers_public.py`): published offer with
  `valid_until = yesterday` → absent from `GET /api/offers` and its detail
  `GET /api/offers/{id}` → 404 (published_only); with `valid_until = today` →
  present; `valid_until = None` → present; `valid_until = tomorrow` → present.
- **preview bypass**: expired offer with `?preview=1` → still returns 200.
- **admin unaffected** (`test_offers_admin.py`): expired offer still listed in
  admin; `is_expired` true.
- **facets** (`test_offer_locations.py` or public): a city served only by an
  expired offer drops out of `/api/locations`.

## Out of scope (YAGNI)

- No status transition, no scheduled job, no new column, no crawler change.
- Freshness `expire_stale` stays as-is (orthogonal).
