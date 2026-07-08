# UBD Discounts — Backend & Data Model Design

**Date:** 2026-07-08
**Sub-project:** 1 of 4 (Backend & Data Model)
**Status:** Approved design, ready for implementation planning

## Context

Platform that aggregates discounts and free events/services for Ukrainian
combat veterans (УБД — учасники бойових дій) from the Ukrainian segment of the
web and social networks. The full system has four sub-projects, built in order:

1. **Backend & data model** (this document) — the foundation.
2. Admin panel — UI to manage sources/offers and moderate crawler findings.
3. Public frontend — Vue 3 SPA (Less) showing published offers.
4. Crawler — scheduled service that scans sources for offers and discovers new
   sources, submitting both for moderation.

This document covers **sub-project 1 only**. Each subsequent sub-project gets
its own spec → plan → implementation cycle.

## Terminology

The word "resource" in the original brief maps to two distinct concepts:

- **Offer** — a discount or event a veteran can use (shown to end users).
- **Source** — a channel the crawler scans for offers (website / Facebook /
  Telegram / Instagram).

When the crawler discovers a new channel/person/organization, it proposes it as
a **new Source** (a monitoring target), not as an offer.

## Tech Stack

- **Framework:** FastAPI
- **ORM / migrations:** SQLAlchemy + Alembic
- **Database:** MySQL
- **Validation:** Pydantic (separate input/output schemas)
- **Auth:** JWT access tokens (admin), bcrypt password hashing, API key (crawler)
- **Tests:** pytest + FastAPI `TestClient`
- **Environment:** local development for now (no deployment target yet)

## Data Model

### `AdminUser`
| field | type | notes |
|-------|------|-------|
| id | PK | |
| email | string, unique | |
| password_hash | string | bcrypt |
| role | enum | `super_admin` \| `moderator` |
| created_at | datetime | |

### `Source` (crawl target)
| field | type | notes |
|-------|------|-------|
| id | PK | |
| name | string | |
| type | enum | `website` \| `facebook` \| `telegram` \| `instagram` |
| url_or_handle | string | URL or @handle |
| is_active | bool | default true |
| last_crawled_at | datetime, nullable | |
| created_by | enum | `admin` \| `crawler_suggestion` |
| created_at | datetime | |

### `Offer` (discount / event)
| field | type | notes |
|-------|------|-------|
| id | PK | |
| type | enum | `discount` \| `event` |
| title | string | |
| description | text | |
| provider | string | "who offers it" — free text (org/shop name) |
| location | string, nullable | city or "online" |
| valid_from | date, nullable | |
| valid_until | date, nullable | must be ≥ valid_from when both set |
| discount_type | enum, nullable | `percent` \| `fixed` \| `free`; null for events |
| discount_value | decimal, nullable | required when discount_type is percent/fixed |
| contacts | string, nullable | phone / email / link |
| image_url | string, nullable | |
| source_id | FK Source, nullable | set when found by crawler |
| status | enum | `pending_review` \| `published` \| `rejected` \| `expired` |
| created_by | enum | `admin` \| `crawler` |
| reviewed_by | FK AdminUser, nullable | |
| created_at | datetime | |
| updated_at | datetime | |

- **`target_categories`** — M2M to `TargetCategory` ("for whom").
- **`offer_categories`** — M2M to `OfferCategory` ("topic").

### `TargetCategory` ("for whom" — recipient categories)
| field | type | notes |
|-------|------|-------|
| id | PK | |
| name | string | e.g. УБД, ветеран, особа з інвалідністю внаслідок війни, сім'я загиблого, ВПО |
| slug | string, unique | |

Admin-managed; extensible without code changes.

### `OfferCategory` (topic — thematic categories)
| field | type | notes |
|-------|------|-------|
| id | PK | |
| name | string | e.g. розваги, музеї, кафе/ресторани, спорт, освіта, транспорт, медицина |
| slug | string, unique | |

Admin-managed; extensible without code changes.

### `SuggestedSource` (crawler proposal for a new source)
| field | type | notes |
|-------|------|-------|
| id | PK | |
| name | string | |
| type | enum | same as Source.type |
| url_or_handle | string | |
| discovered_from_source_id | FK Source, nullable | where it was found |
| discovery_note | text, nullable | why the crawler proposes it |
| status | enum | `pending` \| `approved` \| `rejected` |
| reviewed_by | FK AdminUser, nullable | |
| reviewed_at | datetime, nullable | |
| created_at | datetime | |

On **approve**, a new `Source` is created automatically (created_by =
`crawler_suggestion`).

## Moderation Flow

Everything the crawler produces requires admin approval before it becomes
public or actionable:

- Crawler-found **offers** → created with `status = pending_review` → admin
  publishes or rejects.
- Crawler-discovered **sources** → `SuggestedSource` with `status = pending` →
  admin approves (creates `Source`) or rejects.

## API Design

Three router groups with distinct authorization:

### Public (no auth — fully open)
- `GET /api/offers` — published offers only. Filters: `type`,
  `target_category`, `offer_category`, `location`, text search; pagination;
  sort by date.
- `GET /api/offers/{id}` — single published offer.
- `GET /api/target-categories` — for filters.
- `GET /api/offer-categories` — for filters.

### Admin (JWT)
- `POST /api/auth/login` → JWT.
- CRUD `/api/admin/offers` — includes status changes (publish/reject).
- `GET /api/admin/offers?status=pending_review` — moderation queue.
- CRUD `/api/admin/sources`.
- CRUD `/api/admin/target-categories`.
- CRUD `/api/admin/offer-categories`.
- `GET /api/admin/suggested-sources`.
- `POST /api/admin/suggested-sources/{id}/approve` — creates a `Source`.
- `POST /api/admin/suggested-sources/{id}/reject`.
- CRUD `/api/admin/users` — **super_admin only**.

### Internal (API key — crawler)
- `GET /api/internal/sources?is_active=true` — sources to crawl.
- `POST /api/internal/offers` — create Offer with `status = pending_review`.
- `POST /api/internal/suggested-sources` — propose a new source.

## Roles

- **super_admin** — everything, including managing `AdminUser` and reference
  dictionaries.
- **moderator** — CRUD offers/sources, moderation queue and suggestions; **no**
  user management.

## Error Handling & Validation

- Uniform error shape: `{ "detail": "...", "code": "..." }` via FastAPI
  exception handlers.
- Status codes: 401 (missing/invalid token), 403 (insufficient role), 404,
  422 (Pydantic validation), 409 (conflict, e.g. duplicate slug).
- Pydantic rules: required fields; `valid_from ≤ valid_until`;
  `discount_value` required when `discount_type` ∈ {percent, fixed}.

## Code Structure

```
backend/
  app/
    main.py            # FastAPI app, router registration, exception handlers
    core/              # config, security (JWT, api-key), db session
    models/            # SQLAlchemy models (one module per entity group)
    schemas/           # Pydantic input/output schemas
    crud/              # data-access layer (one module per entity)
    routers/           # public.py / admin.py / internal.py
    deps.py            # dependencies (auth, db session, role checks)
  alembic/             # migrations
  tests/               # pytest
```

## Testing Strategy (TDD)

- **Unit** — CRUD layer against a test DB (separate MySQL schema or
  transaction rollback per test).
- **Integration** — endpoints via `TestClient`:
  - auth (login, token validation, role enforcement),
  - public API filters and published-only visibility,
  - moderation flow (crawler creates pending offer → admin publishes),
  - approve suggested-source → new Source created.
- **Authorization** — public without token, internal with API key, admin with
  correct role; 403 for role violations.

## Seed Data

- Initial `super_admin` from environment variables.
- Base `TargetCategory` entries (УБД, ветеран, особа з інвалідністю внаслідок
  війни, сім'я загиблого, ВПО).
- Base `OfferCategory` entries (розваги, музеї, кафе/ресторани, спорт, освіта,
  транспорт, медицина).

## Out of Scope (this sub-project)

- Admin panel UI (sub-project 2).
- Public frontend SPA (sub-project 3).
- Crawler implementation and cron scheduling (sub-project 4).
- Deployment / containerization.
