# Design — Public filter sidebar (Rozetka-style)

**Date:** 2026-08-12
**Scope:** public frontend layout + filter component + backend multi-value filters

## Goal

Rebuild the public offers page so filters live in a persistent **left sidebar** and the
offer grid sits to the **right** (Rozetka-style). Filters are an always-visible list
(no button/popover on desktop), checkboxes sit **left** of their label, and every facet
is a **multi-select** checkbox group.

## Decisions (approved)

- **Live apply:** every checkbox toggle immediately updates the URL query → reloads offers.
  No "Застосувати" button. A "Скинути" (reset) action remains.
- **All facets multi:** «Для кого» (target), «Тематика» (offer_category), «Тип» (type),
  «Локація» (location) — all multi-select checkbox groups. «Пошук» stays a text input.
- **Mobile:** below `@bp-mobile` (640px) the sidebar collapses into an off-canvas **drawer**
  toggled by a «Фільтри» button (reuse the public app's existing drawer pattern). Same
  content, same live-apply.

## Backend (multi-value filters)

`crud/offer.list_offers` and `routers/public.list_offers`:

| Param | Before | After |
|-------|--------|-------|
| `target_category` | `int` → `.any(id == x)` | `list[int]` (Query) → `.any(TargetCategory.id.in_(ids))` |
| `offer_category` | `int` → `.any(id == x)` | `list[int]` (Query) → `.any(OfferCategory.id.in_(ids))` |
| `type` | `OfferType` | `list[OfferType]` (Query) → `.filter(Offer.type.in_(types))` |
| `location` | already `list[str]` | unchanged |

Empty/None list → filter not applied (same as today). Multiple ids within one facet =
OR (an offer matching any selected category qualifies). Different facets = AND.

**Back-compat:** `Query(None)` list params also accept a single repeated value, so existing
single-value links (`?type=discount`, `?target_category=3`) still parse (as one-element
lists). No migration.

## Frontend

**`OffersView.vue`** — layout shell:
- Desktop: CSS grid `[aside 260px] [main 1fr]`, `gap`. `aside` is `position: sticky; top`.
- `main` holds `OfferGrid` + `Pagination`.
- Mobile (`@bp-mobile`): single column; `aside` becomes off-canvas (transform), a «Фільтри»
  button in the head toggles it; dimmed backdrop closes it.
- Still maps `route.query` ⇄ filters; `onApply` pushes query (now may hold arrays).

**`OfferFilters.vue`** — full rewrite into a persistent sidebar (drop `open`/`draft`/
`backdrop`/popover/apply-button):
- Sections: Пошук (input, applies on enter/debounce), Для кого, Тематика, Тип, Локація.
- Each facet: `<label><input type="checkbox" …> {{ name }}</label>` — checkbox left of text.
- Locations keep the "search city" input + scroll list (already multi).
- On any toggle → build clean filter object → `emit("apply", filters)` immediately.
- `modelValue` seeds checked state; single↔array normalized (as `location` already does).
- "Скинути" emits `{}`.

**`composables/useOffers.js`** — `paramsFromQuery` passes array values through for
`target_category`/`offer_category`/`type`/`location` so axios serialises repeated params.

## Tests (TDD)

- **Backend:** `list_offers` with multiple `target_category` ids (OR); multiple `type`;
  multiple `offer_category`; empty list = no filter; public endpoint parses repeated query
  params into lists.
- **Frontend:** OfferFilters renders checkbox-left rows; toggling a target checkbox emits
  an array and keeps others; live-apply fires on change (no button); reset emits `{}`;
  OffersView renders `aside` + `main` (2-col); mobile drawer toggles open/closed.

## Non-goals

Offer card (just reworked), other pages/views, changing offer data, new filter facets
beyond the existing four.
