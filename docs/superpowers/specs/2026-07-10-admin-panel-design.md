# UBD Discounts — Admin Panel Design

**Date:** 2026-07-10
**Sub-project:** 2 of 4 (Admin Panel)
**Status:** Approved design, ready for implementation planning

## Context

Second sub-project of the UBD platform (see
`2026-07-08-backend-design.md` for the backend it consumes). The admin panel
is the internal UI for staff to manage sources and offers and to moderate what
the crawler produces.

The four sub-projects, built in order:

1. Backend & data model — **done** (branch `feat/backend`).
2. **Admin panel** (this document).
3. Public frontend — Vue 3 SPA (Less).
4. Crawler — scheduled discovery service.

This panel talks only to the backend's **admin** API (`/api/admin/*`, JWT) and
its open reference endpoints (`/api/target-categories`,
`/api/offer-categories`). It never touches the internal (crawler) API.

## Tech Stack

- **Framework:** Vue 3 (Composition API, `<script setup>`)
- **Language:** JavaScript (no TypeScript). JSDoc typedefs for API models
  where they aid editor hints.
- **Build / dev server:** Vite
- **UI library:** Element Plus (tables, forms, dialogs, notifications)
- **Routing:** Vue Router (with auth navigation guards)
- **State:** Pinia (session/token, cached dictionaries)
- **HTTP:** axios (interceptors for auth header and 401 handling)
- **Styles:** Less (own styles layered over Element Plus)
- **Tests:** Vitest + Vue Test Utils

**Location:** a standalone SPA in `admin/` in the same repository, separate
from the public frontend (which is fully open, no auth).

**Backend connection (local dev):** the Vite dev server proxies `/api` →
`http://localhost:8000` (FastAPI via uvicorn). This avoids CORS and requires no
backend change. All requests use the relative `/api/...` base.

**Branch:** work proceeds on a new branch `feat/admin` cut from `feat/backend`
(the admin needs the running backend, which is not yet in `main`).

## Backend API Consumed

Admin (JWT — `Authorization: Bearer <token>`):
- `POST /api/auth/login` → `{ access_token, token_type, role }`
- `GET/POST /api/admin/offers`, `GET/PATCH/DELETE /api/admin/offers/{id}`
- `POST /api/admin/offers/{id}/publish`, `.../reject`
- `GET /api/admin/offers?status=pending_review` — moderation queue
- `GET/POST /api/admin/sources`, `PATCH/DELETE /api/admin/sources/{id}`
- `GET /api/admin/suggested-sources?status=`
- `POST /api/admin/suggested-sources/{id}/approve` (creates a Source)
- `POST /api/admin/suggested-sources/{id}/reject`
- `POST/PATCH/DELETE /api/admin/target-categories[/{id}]` — super_admin only
- `POST/PATCH/DELETE /api/admin/offer-categories[/{id}]` — super_admin only
- `GET/POST /api/admin/users`, `DELETE /api/admin/users/{id}` — super_admin only

Open (no auth), for filters and the offer form:
- `GET /api/target-categories`, `GET /api/offer-categories`

Error shape from backend: `{ "detail": "...", "code": "..." }`.

## Project Structure

```
admin/
  index.html
  package.json
  vite.config.js          # Less, proxy /api → :8000, alias @ → src
  vitest.config.js
  .env.development         # VITE_API_BASE=/api
  src/
    main.js               # mount, Element Plus, Pinia, Router
    App.vue
    router/
      index.js            # routes + guard (token required; /users super_admin only)
    stores/
      auth.js             # token, role, login/logout, isSuperAdmin
      dictionaries.js     # cached target/offer categories
    api/
      client.js           # axios instance + interceptors (auth, 401→logout)
      offers.js
      sources.js
      suggestedSources.js
      categories.js
      users.js
    composables/
      useApiList.js       # pagination/filters/loading for tables
    utils/
      placeholder.js      # context-based SVG placeholder generation
      format.js           # dates, enum labels (Ukrainian)
    constants/
      enums.js            # enum values + Ukrainian labels
    layouts/
      AdminLayout.vue     # sidebar + header (user, logout), <router-view>
    views/
      LoginView.vue
      OffersListView.vue
      ModerationQueueView.vue
      OfferFormView.vue
      SourcesView.vue
      SuggestedSourcesView.vue
      CategoriesView.vue
      AdminUsersView.vue
    components/
      OfferForm.vue
      ImagePreview.vue
      CategoryMultiSelect.vue
      ConfirmDialog.vue
      DataTableToolbar.vue
    styles/
      variables.less
      global.less
  tests/                  # mirrors src; Vitest + Vue Test Utils
```

Principle: each `api/*.js` is a thin wrapper over one endpoint group; `views/*`
compose UI from shared `components/*`; list logic (pagination/filters/loading)
lives in `useApiList` for DRY tables.

## Authentication & API Layer

**Login flow:** `LoginView` → `POST /api/auth/login` → store
`{ access_token, role }` in Pinia + `localStorage` (survives reload) → redirect
to offers list.

**axios client (`api/client.js`):**
- `baseURL` = `/api` (proxied to backend).
- Request interceptor: attach `Authorization: Bearer <token>` when present.
- Response interceptor: on `401` clear session and redirect to `/login`; other
  errors propagate in the `{detail, code}` shape for display via
  `ElMessage` / `ElNotification`.

**Router guards:**
- All routes except `/login` require a token; otherwise redirect to `/login`.
- `/users` additionally requires `role === 'super_admin'`; otherwise redirect
  to offers list with an "insufficient permissions" message.
- The "Admins" menu item is hidden for non-super_admin.

**Roles:** the `auth` store exposes `isSuperAdmin`. The UI hides/disables
super_admin-only actions (admin-user management, and category dictionary
management — the backend restricts category CRUD to super_admin). A moderator
sees offers, sources, the moderation queue, and suggested sources.

**Dictionaries:** the `dictionaries` store loads `GET /api/target-categories`
and `GET /api/offer-categories` once (open endpoints) and caches them for
filters and the offer form.

## Screens & Features

- **Login** — email/password form, validation, error display on 401.
- **Offers list** — `el-table` with pagination; filters: status, type, text
  search; columns: title, provider, type, status (colored tag), validity
  dates, created date. Row actions: edit, publish/reject (by status), delete
  (confirm). "Create offer" button.
- **Moderation queue** — same list fixed to `status=pending_review`, emphasis
  on Publish / Reject. Sidebar badge shows the pending count.
- **Offer form** (create/edit) — all fields: type (discount/event), title,
  description, provider, "for whom" (target-category multiselect), topic
  (offer-category multiselect), location, `valid_from`/`valid_until`,
  discount_type (percent/fixed/free — for discount), discount_value, contacts,
  `image_url` + preview. Client validation mirrors the backend:
  `valid_until ≥ valid_from`; `discount_value` required for percent/fixed and
  forbidden for free/events.
- **Sources** — table + form (name, type website/facebook/telegram/instagram,
  url/handle, active). CRUD, delete with confirm.
- **Suggested sources** — table of pending crawler proposals (name, type, url,
  discovered-from, note). Actions: Approve (creates a Source) / Reject. Status
  filter.
- **Category dictionaries** — two tabs (target / offer), each a table with
  inline create/edit/delete (name, slug). super_admin only.
- **Admins** (super_admin) — table (email, role, created), create
  (email/password/role), delete. Hidden for moderator.

## Error Handling & Validation

- Backend returns `{detail, code}`. A central helper extracts `detail` and
  shows it via `ElMessage.error` (actions) or `ElNotification`.
- Special codes: `401` → redirect to login (interceptor); `403` →
  "insufficient permissions"; `409` (e.g. duplicate slug, repeat approve) →
  show `detail`; `422` → highlight offending form fields.
- Form validation via `el-form` rules mirrors backend rules (required fields,
  discount_value/discount_type dependency, date order). Invalid forms cannot
  be submitted — saves a round trip.

## Image Placeholder

Auto-extracting an image from a source post is the **crawler's** job
(sub-project 4): it sets `image_url` when submitting an offer. The admin panel
only shows/edits `image_url`.

`utils/placeholder.js`: when `image_url` is empty, `ImagePreview` renders an
inline SVG (data-URI) with text:
- "безкоштовно для УБД" — when `type=event` or `discount_type=free`;
- "знижка для УБД" — otherwise.

The function returns an SVG string by context; the same logic is reused later
on the public frontend.

## Testing Strategy (Vitest + Vue Test Utils)

- **Unit:** `api/*` (correct URLs/params with mocked axios); `auth` store
  (login stores token/role, logout clears, isSuperAdmin); `placeholder.js`
  (correct text by context); `format.js` (enum labels, dates); form validation
  rules.
- **Component:** `LoginView` (submit, error display on mocked 401); `OfferForm`
  (validation blocks invalid submit, discount-field dependency);
  `OffersListView` (renders rows from mocked data, filter changes the request);
  `SuggestedSourcesView` (approve/reject call the right endpoints).
- The API is always mocked — no real backend. Goal: pristine output,
  deterministic.

## Out of Scope (this sub-project)

- Public frontend SPA (sub-project 3).
- Crawler and image auto-extraction (sub-project 4).
- File upload / image storage backend (offers use `image_url` strings).
- Backend changes of any kind.
- Deployment / production reverse-proxy config.
