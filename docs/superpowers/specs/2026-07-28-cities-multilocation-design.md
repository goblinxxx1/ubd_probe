# Cities: gazetteer + multi-location offers — design

Date: 2026-07-28
Track: 1 (Міста) of the cities/dedup/searxng queue.

## Problem

`location` is a single free-text `String(255)` on `Offer`. The crawler normalizes
to one canonical Ukrainian city (`find_city` returns the first match) or `"Онлайн"`;
admin edits it as a free `el-input`; the public filter is a free-text substring
(`location.ilike("%q%")`). There is no gazetteer-backed selection, no way to attach
several cities to one offer (a network with branches), no multi-city public filter,
and Latin/transliterated city spellings on source sites are not recognized.

## Goals (decisions locked in brainstorming)

- An offer can carry **several cities**. The crawler fills **all** cities it detects
  on the offer page (not just the first).
- **Admin**: searchable multi-select over a full Ukrainian gazetteer (~460, oblast
  centres + all cities), plus a pinned "Онлайн" option.
- **Public**: multi-select city filter (OR) whose options are **only cities that
  actually appear in published offers** (faceted from data). Cards show all of an
  offer's cities.
- The crawler must map **transliterated / alternate spellings** on sites to the
  canonical Ukrainian name (e.g. `Kyiv/Kiev → Київ`, `Lviv → Львів`,
  `Odesa/Odessa → Одеса`).

Non-goals (explicitly out of scope):

- Expanding the crawler's *detection* set from the curated ~35 cities to all ~460.
  Safe inflected matching for hundreds of names is a separate recall lever. Admin
  manual selection covers the full gazetteer; the crawler auto-detects its curated
  set (now with transliteration and multi-return).
- Disambiguating homonym cities (same name, different oblast). In a name-string
  model these collapse to one location; accepted for a discounts catalogue.
- Region/oblast grouping of the filter (no cities table). Can be added later.
- Separating "Онлайн" into its own boolean/flag — it stays a normal location value.

## Data model

New child table, one row per (offer, city):

```
offer_locations(
  id        PK,
  offer_id  FK -> offers.id  ON DELETE CASCADE, indexed,
  name      String(255), indexed          -- canonical city name, or "Онлайн"
)
```

- ORM: `Offer.locations` relationship (cascade delete-orphan) + association proxy
  `Offer.location_names -> [name]` for read paths.
- **Remove** the `Offer.location` column. It participates in neither dedup
  (`content_hash` / `target_url_canonical`) nor search (title/description/provider),
  so restructuring it is safe.

Migration (single revision):

1. create `offer_locations`;
2. backfill: every offer with non-null `location` → one row with that value;
3. drop `offers.location`.

Names are canonical strings coming from controlled sources (admin dropdown, crawler
gazetteer), so no FK/cities table is used. Homonym names collapse to a single
selectable value (accepted).

## Gazetteer asset

- **Source**: OSM Overpass (already used elsewhere in the crawler). A committed
  generator `scripts/build_gazetteer.py` queries Ukrainian populated places of
  city/town rank, takes `name:uk`, dedupes, sorts, and writes the output. Both the
  script and its generated output are committed for reproducibility.
- **Format / location**: `admin/src/constants/gazetteer.js` — a flat, sorted array
  of canonical city name strings (~460+). **Sole consumer is the admin app**; the
  backend stores plain strings and facets from data, and the crawler keeps its own
  detection surface forms (below).
- "Онлайн" is a pinned option in the admin control, not part of the gazetteer file.

## Crawler changes

- `discovery/geo.py`:
  - `find_city(text) -> str | None` becomes / gains `find_cities(text) -> list[str]`
    returning **all** distinct canonical cities in first-appearance order, preserving
    the precision rules (prefix-only homographs `Вишневе/Буча/Бровари`, word
    boundaries). `find_city` may remain as a thin `find_cities(...)[:1]` wrapper if
    any caller still needs a single value.
  - Add **transliteration** surface forms to the curated cities (Latin, and common
    Russian variants where unambiguous), all lowercased, mapping to the canonical
    Ukrainian name. Latin forms are low-collision, so precision is preserved.
- `extract/heuristic.py`: replace the single `location=` assignment with
  `locations=` — the **union** of the canonicalized `item.locality` and all
  `find_cities(text)` results; if empty and `is_online(text)`, `["Онлайн"]`; dedupe
  preserving order.
- `models.py`: `OfferCandidate.location: str | None` → `locations: list[str]`
  (default empty).
- `payloads.py`: emit `"locations": cand.locations` instead of `"location"`.

## Backend API

- Schemas (`schemas/offer.py`):
  - `OfferBase` / `OfferCreate`: `location: str | None` → `locations: list[str] = []`
    (this is the crawler ingest shape).
  - `OfferUpdate`: `locations: list[str] | None = None`.
  - `OfferOut`: `locations: list[str]`, serialized from `location_names`.
- CRUD (`crud/offer.py`): `create_offer` / `update_offer` accept `locations` and
  (re)build the child rows — dedupe, strip blanks; on update, replace when the field
  is provided.
- Public filter (`routers/public.py` + `crud.list_offers`): the `location` query
  param becomes **repeated / multi** (`?location=Київ&location=Львів`), exact-name,
  OR-matched via `Offer.locations.any(OfferLocation.name.in_(values))`.
- New facet endpoint **`GET /api/locations`** → sorted DISTINCT `name` among
  **published** offers only. Feeds the public filter so it lists only cities that
  have offers.

## Admin UI

- `components/OfferForm.vue`: the "Локація" field becomes an
  `el-select multiple filterable`, options from `constants/gazetteer.js` plus a
  pinned "Онлайн", bound to `form.locations`.
- `utils/offerForm.js`: `fromInitial` / `buildOfferPayload` carry `locations` as an
  array; location stays optional (no validation requirement).
- Any admin list/detail view that showed `location` shows `locations.join(", ")`.

## Public UI

- `components/OfferFilters.vue`: the "Локація" text input becomes a **multi-select
  checkbox list** of cities (scrollable, with an inline search when long), options
  from `GET /api/locations`. `draft.locations` is an array; `activeCount` counts a
  non-empty array; the query sends repeated `location=` params.
- `components/OfferCard.vue`: `meta = offer.locations.join(" · ")` — show all cities.
- The public offer-detail view shows all cities too.

## Testing (TDD)

- **crawler**: `find_cities` (multi-return, transliteration, homograph precision);
  `heuristic` (union `locations`); `payloads` (emits `locations`).
- **backend**: crud create/update (replace-on-update, dedupe); public filter
  (multi / OR, exact-name); facet endpoint (distinct, published-only); migration
  (backfill + column drop); `OfferOut` serialization.
- **admin**: `offerForm` util (`locations` in payload and `fromInitial`).
- **public**: `OfferFilters` (multi-select apply → repeated params);
  `OfferCard` (joins cities).

## Rollout

Standard: merge `--no-ff` to main, push, canonical rebuild of the affected images
(backend, crawler, admin, public), live Docker smoke check (migration applied,
crawler emits multi-city, admin dropdown, public facet + filter, card display),
update memory / RESUME.
