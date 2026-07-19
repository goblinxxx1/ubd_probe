# Design — Responsive layout for admin + public

**Date:** 2026-07-19
**Branch:** `feat/ui-responsive` (from `main`)
**Goal:** Full responsive support for both front-ends. Admin must work down to
phone width (≤640px), including data tables; public gets a full responsive pass.
**Order:** admin first, then public. Single track.

## Context

- **Public** (Vue 3, plain Less) is already largely fluid: `container`, grid,
  cards, detail, pagination. The mobile offer-filters panel was fixed separately
  (`fix/mobile-filters`, merged). Remaining work is a systematic pass, not a
  rewrite.
- **Admin** (Vue 3 + Element Plus) is effectively non-responsive: only 2 files
  carry media queries. `AdminLayout.vue` is a fixed-width sidebar + main; the six
  list views use `el-table`, which does not collapse on narrow screens.

## Breakpoints & shared foundation

- Single shared set: `@bp-mobile: 640px` (already defined in public
  `variables.less`), plus a new `@bp-tablet: 1024px`. Mirror both tokens into
  admin `variables.less`.
- A lightweight `useBreakpoint()` composable in **each** app (they are separate
  builds): returns reactive `isMobile` / `isTablet` via `window.matchMedia`,
  with listener cleanup on unmount. Drives `ResponsiveTable` and the admin drawer.

**Decision:** admin drawer navigation engages at **≤1024px** (tablet-portrait
also reclaims width); table→card collapse engages at **≤640px**.

## Admin — shell (`AdminLayout.vue`)

- Desktop (>1024): sidebar as today.
- ≤1024: sidebar becomes an off-canvas drawer (`transform: translateX(-100%)`),
  toggled by a hamburger button added to the topbar (visible ≤1024), with a
  dimmed fixed backdrop. Closes on nav-item click and on backdrop click. Reuses
  the same overlay pattern as the merged mobile-filter fix (fixed positioning,
  dimmed backdrop, high z-index) — no `el-drawer`, to avoid z-index fights and
  keep it lightweight.
- Topbar keeps `role` + "Вийти"; hamburger sits on the left.

## Admin — `ResponsiveTable` component (core)

New `admin/src/components/ResponsiveTable.vue`. Single column definition drives
both presentations:

- **Props:**
  - `columns`: array of `{ prop, label, width?, minWidth?, formatter?, slot? }`.
    `formatter(row)` returns display text; `slot` names a scoped cell slot for
    custom rendering (badges, links).
  - `rows`: array of row objects.
  - `rowKey`: string (defaults to `id`).
  - Optional `#actions` scoped slot (`{ row }`) for per-row action buttons.
- **Desktop (>640):** renders `<el-table :data="rows" :row-key>` with one
  `<el-table-column>` per column (using `formatter` or the named slot), and a
  trailing actions column bound to the `#actions` slot when present.
- **Mobile (≤640):** renders a stacked list of cards; each card shows, per
  column, a `label: value` pair (value via `formatter`/slot), followed by an
  actions row from the same `#actions` slot.
- Empty state shown in both modes. Sorting/selection stay desktop-only (mobile
  cards are read + act, no column sort) to keep the wrapper simple.

**Migrate six views** to `ResponsiveTable`, each defining its columns once:
`OffersListView`, `ModerationQueueView`, `SourcesView`, `SuggestedSourcesView`,
`CategoriesView`, `AdminUsersView`. Row actions (approve/reject/edit/delete)
move into the `#actions` slot.

## Admin — forms & toolbars

- `OfferForm` / `OfferFormView`: on mobile use Element Plus `label-position:
  top`; inputs and action buttons go full-width / stack.
- `DataTableToolbar`: filters and actions wrap / stack on narrow widths.
- Verify `CategoryMultiSelect` and `ImagePreview` render and are usable at ≤640.

## Public — full responsive pass

- `SiteHeader`: nav is currently static text ("Оффери · Про нас") — convert to
  real `router-link`s; ensure the header wraps cleanly on mobile with adequate
  tap targets. (Two items only — a wrap suffices; no hamburger needed.)
- Audit at 375 / 768 / 1280 and fix as needed:
  - `OffersView` head (h1 + Фільтри trigger) stacks cleanly.
  - `OfferGrid` / `OfferCard`: single column on phone, sane image aspect,
    tap targets ≥44px.
  - `OfferDetailView`: image + meta stack on mobile, no overflow.
  - `Pagination`: wraps on narrow widths.
  - Global: container padding, no horizontal scroll anywhere, legible font sizes.

## Testing & verification

- Per app, every change gate: `npm run build` (catches scoped-Less errors that
  Vitest misses — established lesson) + `npm test` (Vitest) + in-app browser
  checks at 375 / 768 / 1280.
- New unit tests:
  - `useBreakpoint` (mocked `matchMedia`).
  - `ResponsiveTable`: renders `el-table` above the breakpoint and card list
    below it; actions slot appears in both; empty state.
- Keep existing suites green (admin 77, public 59) and extend.
- Manual smoke: admin drawer open/close + nav; table→card flip at 640; forms on
  mobile; public screens at all three widths.

## Out of scope

- No visual redesign / re-theming — layout & responsiveness only; keep the
  existing tokens, colors, and typography.
- No new admin features; no backend changes.
- Desktop layouts (>1024) stay as-is except where a shared component is refactored.

## Success criteria

- Admin usable end-to-end on a 375px phone: nav via drawer, every list view
  readable as cards, forms fillable, no horizontal page scroll.
- Public clean at 375 / 768 / 1280 with real header nav and no overflow.
- All builds clean, all test suites green, new components covered by unit tests.
