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
- The crawler must detect the **full gazetteer (~460 cities)**, not a curated
  subset — "walk all of Ukraine". Achieved with build-time generated inflected
  forms + a homograph veto (see §Gazetteer, §Crawler), so no runtime morphology
  dependency is added.

Non-goals (explicitly out of scope):

- Disambiguating homonym cities (same name, different oblast). In a name-string
  model these collapse to one location; accepted for a discounts catalogue.
- Region/oblast grouping of the filter (no cities table). Can be added later.
- Separating "Онлайн" into its own boolean/flag — it stays a normal location value.
- A **runtime** morphology dependency in the crawler image. Inflection is done once
  at build time; the committed form-map is matched with the stdlib at runtime.

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

One committed generator, one master dataset, two derived artifacts. The gazetteer
now serves **two** consumers — the admin dropdown (names only) and the crawler
detector (inflected + transliterated forms with a homograph flag).

- **Generator**: `crawler/scripts/build_gazetteer.py` (Python — it needs Overpass +
  a morphology inflector, both Python). Steps, all at build time:
  1. Query **OSM Overpass** for Ukrainian populated places of city/town rank, take
     `name:uk`, dedupe, sort → the canonical name list (~460+).
  2. For each name, generate **inflected surface forms** (nominative + common
     oblique cases) via a Ukrainian morphology inflector
     (`pymorphy3` + `pymorphy3-dicts-uk`) — a **build/dev-only** dependency, never
     in the crawler runtime image.
  3. Generate a **transliterated Latin form** per name via the deterministic KMU
     UA→Latin table, plus a small manual map of common alternates
     (`Kyiv/Kiev, Lviv/Lvov, Odesa/Odessa, Kharkiv/Kharkov, Dnipro/Dnepr`).
  4. **Homograph veto**: cross-check every generated form against a bundled
     open Ukrainian word list (spellcheck/frequency). Any form that is also a common
     word is flagged **marker-only** (`m=1`); the rest are permissive (`m=0`). A
     small curated override list corrects auto misses/over-flags.
- **Master dataset** (committed): per city `{ "name", "forms": [{"f": form, "m": 0|1}, …] }`.
- **Derived artifacts** (both committed, regenerated together):
  - `crawler/crawler/discovery/gazetteer_data.py` (or `.json` loaded by `geo.py`) —
    the full form-map, consumed by the runtime detector.
  - `admin/src/constants/gazetteer.js` — flat, sorted array of **names only**, for
    the admin dropdown.
- "Онлайн" is a pinned option in the admin control, not part of the gazetteer file.
- The backend stores plain strings and facets from data — it consumes neither
  artifact.

## Crawler changes

- `discovery/geo.py` — replace the hand-curated `_CITIES` dict with the generated
  `gazetteer_data` form-map (§Gazetteer) and a stdlib matcher:
  - Load the form-map into a lookup `form -> canonical` plus each form's marker flag.
  - **Matcher** (no runtime dependency): lowercase and tokenize the text, scan
    single- and multi-token windows (multi-word names like `Біла Церква`,
    `Кривий Ріг`) against the lookup. A **permissive** form (`m=0`) matches anywhere;
    a **marker-only** form (`m=1`) matches only when the preceding token is a
    locality marker (`м`, `с`, `смт`, `місто`, with optional dot). Word boundaries
    are inherent to token matching. For throughput over the ~thousands of forms,
    build the lookup once at import (dict / set), not per-call regexes.
  - `find_cities(text) -> list[str]` returns **all** distinct canonical cities in
    first-appearance order. `find_city` remains as a thin `find_cities(...)[:1]`
    wrapper for any single-value caller (e.g. `website.py`).
  - `is_online(text)` is unchanged.
- `extract/heuristic.py`: replace the single `location=` assignment with
  `locations=` — the **union** of the canonicalized `item.locality`
  (run through `find_cities`; keep the raw value only if it resolves to nothing) and
  all `find_cities(text)` results; if empty and `is_online(text)`, `["Онлайн"]`;
  dedupe preserving order.
- `fetchers/website.py`: the contact/footer locality helper keeps returning a single
  value via `find_city(...)`; it now resolves against the full gazetteer.
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

- **crawler**: `find_cities` over the generated gazetteer — multi-return &
  first-appearance order; permissive tail city matched in prose; **marker-only**
  (vetoed homograph) city matched only with a locality marker and NOT as a bare
  common word (e.g. `суми` vs `м. Суми`); transliteration (`Lviv → Львів`);
  multi-word name (`Біла Церква`); existing curated cases still pass.
  `heuristic` (union `locations`, `item.locality` canonicalized); `payloads`
  (emits `locations`). The generated form-map is loaded from the committed artifact
  (fixture-independent of live Overpass).
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
