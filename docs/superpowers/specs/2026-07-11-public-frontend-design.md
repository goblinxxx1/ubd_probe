# UBD Discounts — Public Frontend Design

**Date:** 2026-07-11
**Sub-project:** 3 of 4 (Public Frontend)
**Status:** Approved design, ready for implementation planning

## Context

Third sub-project of the UBD platform (backend = sub-project 1, admin panel =
sub-project 2, both merged to `main`). The public frontend is the veteran-facing
site: it shows **published** offers (discounts / free events) with filtering and
a detail view. It reads only the backend's open endpoints — no auth anywhere.

Built in a fresh session on branch `feat/public` (cut from `main`), following the
per-track workflow (see `docs/RESUME.md`).

## Tech Stack

- **Framework:** Vue 3 (Composition API, `<script setup>`)
- **Language:** JavaScript (no TypeScript), matching the admin panel.
- **Build / dev server:** Vite
- **Routing:** Vue Router (history mode)
- **HTTP:** axios via a thin shared client (`baseURL = import.meta.env.VITE_API_BASE || "/api"`)
- **Styles:** Less only — all styling hand-rolled, no UI component library; mobile-first responsive.
- **State:** no Pinia. Filters live in the URL (source of truth); category
  dictionaries cached in a composable.
- **Tests:** Vitest + @vue/test-utils (jsdom); API always mocked.

**Location:** a standalone SPA in `public/` in the repo, separate from `admin/`.

**Backend connection (local dev):** the Vite dev server proxies `/api` →
`http://localhost:8000`. No CORS config, no backend change.

## Backend API Consumed (all open, no auth)

- `GET /api/offers` — published offers only. Query: `type`, `target_category`
  (id), `offer_category` (id), `location`, `q` (text search), `page`, `size`.
  Returns `{ items, total, page, size }`.
- `GET /api/offers/{id}` — single published offer (404 if missing/not published).
- `GET /api/target-categories`, `GET /api/offer-categories` — filter options.

Offer fields used: `id, type, title, description, provider, location,
valid_from, valid_until, discount_type, discount_value, contacts, image_url,
target_categories[], offer_categories[]`. `source_id` is internal and NOT shown.

## Reuse from Admin

Copied (not cross-app imported, since these are separate apps):
- `utils/placeholder.js` — context SVG placeholder ("безкоштовно/знижка для УБД").
- `utils/format.js` — date formatting, enum labels; plus a new `offerBadge(offer)` helper here.
- `constants/enums.js` — type/discount/category values with Ukrainian labels.

## Project Structure

```
public/
  index.html
  package.json
  vite.config.js          # Less, proxy /api → :8000, alias @ → src
  vitest.config.js
  vitest.setup.js
  .env.development         # VITE_API_BASE=/api
  src/
    main.js
    App.vue               # SiteHeader + <router-view> + SiteFooter
    router/index.js
    api/
      client.js           # axios instance (baseURL /api)
      offers.js           # list(params), get(id)
      categories.js       # listTarget(), listOffer()
    composables/
      useDictionaries.js  # cache target/offer categories for filters
      useOffers.js        # load list + sync with route query
    utils/
      placeholder.js      # (copied) context SVG placeholder
      format.js           # (copied) dates, enum labels, offerBadge()
      errors.js           # extractError
    constants/
      enums.js            # (copied) enums + Ukrainian labels
    components/
      SiteHeader.vue
      SiteFooter.vue
      OfferCard.vue
      OfferFilters.vue    # "Фільтри" button → dropdown panel with all fields
      OfferGrid.vue       # card grid + loading/empty/error states
      Pagination.vue
      OfferBadge.vue
    views/
      OffersView.vue      # filters + grid + pagination
      OfferDetailView.vue
      NotFoundView.vue
    styles/
      variables.less      # colors, breakpoints, spacing
      base.less           # reset, typography, globals
  tests/                  # mirrors src
```

Each `view` composes small `components`; all network in thin `api/*`; list logic
(filters↔URL, pagination, loading) lives in `useOffers`.

## Routing & Filter/URL Sync

- `/` → `OffersView`. Filters + pagination in query:
  `?type=&target_category=&offer_category=&location=&q=&page=`.
- `/offers/:id` → `OfferDetailView`.
- `/:catchAll(.*)` → `NotFoundView`.

**URL is the single source of truth for filters.** `useOffers` reads
`route.query`, builds request params (dropping empties), calls `offers.list`,
and `watch`es `route.query` — any query change reloads. `OfferFilters` and
`Pagination` hold no persistent state; they push changes via
`router.push({ query })`, which triggers the reload. Browser back/forward and
shareable links work naturally. `size` is fixed (12), not in the URL.

## Data Flow

**List:** `OffersView` mounts → `useDictionaries.load()` (fills filter dropdowns,
cached once) + `useOffers` reads the current query → `offers.list(cleanParams)`
→ `{ items, total, page, size }`. Filter/page change → `router.push(query)` →
watcher → new `load()`.

**Detail:** `OfferDetailView` takes `route.params.id` → `offers.get(id)`. Backend
returns only published offers; on 404 (missing/unpublished) it shows the
not-found state with a link back to the list.

## Components & Pages

- **OffersView** — page title ("Знижки та події для УБД"), the `OfferFilters`
  trigger, `OfferGrid`, `Pagination`.
- **OfferFilters** — a "Фільтри" button/chip (with a count of active filters)
  that opens a single dropdown **panel** containing all fields: type
  (Знижка/Подія), "для кого" (from target-categories), topic (from
  offer-categories), location (text), search (text). The panel has
  **Застосувати** (pushes all fields to the URL query and closes) and
  **Скинути** (clears filters). Clicking outside closes the panel without
  applying.
- **OfferGrid** — responsive `OfferCard` grid with three states: `loading`
  (skeletons/spinner), `empty` ("Нічого не знайдено" + reset hint), and the list.
  Also an `error` state ("Не вдалося завантажити. Спробуйте пізніше").
- **OfferCard** — image (`image_url` or placeholder), `OfferBadge`, title,
  provider, location, "для кого" tags; click → `/offers/:id`.
- **OfferBadge** — short context tag via `offerBadge(offer)`: `Подія`
  (type=event), `Безкоштовно` (discount_type=free), `−50%` (percent),
  `−200 ₴` (fixed).
- **Pagination** — prev/next + page numbers from `total`/`size`; emits `page`;
  disabled at bounds.
- **OfferDetailView** — large image/placeholder, title, `OfferBadge`, provider,
  full description, "для кого" + topic tags, location, validity period
  (`valid_from`–`valid_until`, formatted), contacts, "← до списку". No source.
- **SiteHeader** (title/logo + link home) and **SiteFooter** (short purpose
  text) on all pages via `App.vue`.
- **NotFoundView** — for unknown routes and missing/unpublished offers.

## Error, Loading & Empty Handling

- Public API is open — no 401 handling.
- Network/5xx errors surface a friendly message via `extractError` in the grid
  and detail views (not a raw error).
- Empty list → "Нічого не знайдено" + a reset-filters action.

## Image Placeholder

`OfferCard` and `OfferDetailView` show `image_url` when present, else
`placeholderDataUri(offer)` — the same context-based SVG as the admin panel
("безкоштовно для УБД" for events/free, "знижка для УБД" otherwise).

## Responsive

Mobile-first Less: card grid collapses to a single column on narrow screens;
the filters panel is full-width on mobile. Breakpoints in `variables.less`.

## Testing Strategy (Vitest + Vue Test Utils, API mocked)

- **Unit:** `api/offers` + `api/categories` (correct URLs/params); `format.js`
  (dates, enum labels, `offerBadge` by context); `placeholder.js`; `useOffers`
  (builds params from query, drops empties, reloads on query change);
  `useDictionaries` (caches once).
- **Component:** `OfferFilters` (opens panel, Застосувати emits/pushes filters,
  Скинути clears, active count); `OfferCard` (badge + placeholder fallback +
  link target); `OfferGrid` (loading/empty/error/list states); `Pagination`
  (emits page, disabled at bounds); `OffersView` (query → `offers.list` with
  mapped params; filter change pushes to router); `OfferDetailView` (loads by
  id; not-found state on rejection).

## Out of Scope (this sub-project)

- Crawler (sub-project 4).
- Any backend change.
- SSR / SEO pre-rendering (ТЗ mandates a client-side SPA).
- Landing/marketing page, about page (only list + filters + detail this iteration).
- Auth / user accounts (public site is fully anonymous).
- Deployment / production hosting config.
