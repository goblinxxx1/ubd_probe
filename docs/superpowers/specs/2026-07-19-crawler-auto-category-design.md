# Crawler auto-category via curated lexicon — Design

**Date:** 2026-07-19
**Track:** `feat/crawler-auto-category`
**Status:** approved design, pending implementation plan

## Goal

Two coordinated improvements to how the crawler assigns categories, with
**auto-creation limited to the offer axis (тематика)**:

1. **Richer classification coverage.** Replace the current weak `name[:5]`-stem
   substring match with a curated keyword **lexicon**, and classify over the
   **site context** (`provider + site_name + text`), not just the offer block.
   Applies to **both** axes (target «для кого» and offer «тематика»).
2. **Auto-creation of new тематика.** When the lexicon matches an offer category
   that does not yet exist in the DB, the crawler creates it via a new internal
   endpoint. The target axis is **match-to-existing only — never created.**

### Why offer-only auto-creation

The «для кого» axis is a small, legally-bounded, stable set (statuses:
УБД / ветеран / інвалідність внаслідок війни / сім'я загиблого / ВПО). Auto-creating
audiences from noisy offer text would (a) fragment the primary user filter into
synonym duplicates («воїнам» / «захисникам» / «ЗСУ» → all really УБД), (b) admit
non-audience junk («для всієї родини»), and (c) drift from the legal statuses that
back eligibility. Business verticals («тематика») are genuinely open-ended, so
auto-creation there has real upside and produces concrete, clean names.

### Why a curated lexicon (not emergent naming)

A controlled vocabulary guarantees a clean taxonomy: names come from a reviewable
file, never free text. An unknown vertical simply gets **no тематика** (a harmless,
recoverable *miss*) rather than **garbage** in a shared filter taxonomy (corrosive,
needs manual cleanup). The lexicon is deliberately **broader than the DB seed** —
the DB starts with whatever admin seeded, and the crawler lazily materialises
lexicon verticals in the DB on first live encounter. That lazy materialisation *is*
the auto-creation the moderator sees.

## Global constraints

- Zero-cost, offline, **no cloud LLM** — heuristics / local parsing only.
- Crawler tests run offline from `crawler/` (httpx.MockTransport); backend tests
  from `backend/` (FastAPI TestClient, needs `mysql-container` on :3306).
- Ukrainian UI copy; communicate in Ukrainian.
- `content_hash` identity is owned by the backend; categories are metadata and
  **must not** enter `content_hash`.

## Current state (baseline)

- `crawler/crawler/extract/heuristic.py` — `_match_categories(text_low, cats)`
  matches `c["name"].lower()[:5]` as a bare substring in the offer-block text only.
  Fills `target_category_ids` and `offer_category_ids` on `OfferCandidate`.
- `crawler/crawler/api_client.py` — only `X-API-Key` internal calls; category
  listing via public `GET /api/{target,offer}-categories`.
- `backend/app/routers/internal.py` — `X-API-Key`-guarded router; **no** category
  endpoints.
- `backend/app/routers/admin.py` — category create/update/delete under
  `require_super_admin` (admin-JWT).
- `backend/app/crud/category.py` — `create_category` raises `conflict` on dup slug;
  no get-or-create.
- **Seed** (`backend/app/seed.py`):
  - target slugs: `ubd, veteran, war-disability, fallen-family, idp`
  - offer slugs: `rozvahy, museums, food, sport, education, transport, medicine`
  The lexicon **must reuse these slugs** for known verticals so classification
  attaches to seeded rows instead of creating duplicates.

## Components

### 1. `crawler/crawler/discovery/lexicon.py` (new)

Curated offline lexicon, sibling to `geo.py` / `blocklist.py` (same "curated data +
pure function" pattern).

Two tables mapping a canonical `(name, slug)` to a tuple of lowercase keyword
**stems** (inflection-surviving, precision-first):

- `OFFER_LEXICON` — known verticals **reuse seed slugs**; new verticals get new
  slugs. Representative starter set (~18 verticals):
  - `("Розваги", "rozvahy")` — розваг, квест, боулінг, кінотеатр, атракціон, караоке, більярд, лазертаг
  - `("Музеї", "museums")` — музе, галере, виставк, експозиц
  - `("Кафе/ресторани", "food")` — кав'ярн, кафе, ресторан, бариста, піц, суші, паб, їдальн, бістро, кондитер, пекарн
  - `("Спорт", "sport")` — спорт, фітнес, тренаж, качалк, єдиноборст, басейн, йог, кросфіт
  - `("Освіта", "education")` — освіт, курс, навчанн, тренінг, репетитор, автошкол, вебінар
  - `("Транспорт", "transport")` — транспорт, таксі, каршеринг, переїзд, доставк
  - `("Медицина", "medicine")` — клінік, медцентр, лікар, діагностик, реабілітац, офтальмолог
  - `("Краса та догляд", "beauty")` — перукар, барбершоп, манікюр, педикюр, косметолог, епіляц, візаж
  - `("Автосервіс", "auto")` — автосервіс, шиномонтаж, автомийк, запчастин, ремонт авто
  - `("Аптека", "pharmacy")` — аптек, фармац
  - `("Стоматологія", "dentistry")` — стоматолог, дантист, зубн
  - `("Одяг та взуття", "clothing")` — одяг, взутт, ательє, кросівк
  - `("Квіти", "flowers")` — квіт, флорист, букет
  - `("Готелі та відпочинок", "hotels")` — готель, хостел, база відпочинк, санатор, екскурс
  - `("Книги та канцтовари", "books")` — книгарн, канцтовар
  - `("Електроніка", "electronics")` — електронік, гаджет, смартфон, ноутбук
  - `("Юридичні послуги", "legal")` — юридичн, адвокат, нотаріус, юрист
  - `("Оптика", "optics")` — оптик, окуляр, лінз
  (exact stem set finalised in the plan; **`food`/`sport`/… reuse seed slugs**.)

- `TARGET_LEXICON` — canonical is an **existing** seed slug; keyword stems only,
  no creation:
  - `ubd` — убд, учасник бойов, бойових дій, воїн, військовослужбовц, захисник, зсу, всу, тероборон
  - `veteran` — ветеран
  - `war-disability` — інвалід, інвалідніст
  - `fallen-family` — загибл, полегл, родин загибл, вдов
  - `idp` — переселен, впо, переміщен особ

- **Interface:** `classify(text: str | None, lexicon) -> list[tuple[str, str]]`
  — deterministic, deduplicated list of `(name, slug)` for every matched canonical.
  Matching uses a **word-start boundary regex** (`(?<!\w)stem`, no end-boundary so
  inflected suffixes survive) — the same precision technique as `geo.py`. Stems are
  curated to be discriminative (≥4–5 chars; ambiguous short stems like bare «бар»
  excluded). No match → `[]`.

### 2. `crawler/crawler/models.py`

Add a transient field to `OfferCandidate`:

```python
    offer_category_matches: list[tuple[str, str]] = field(default_factory=list)
```

`offer_category_ids` stays (default `[]`) but is now filled **later** by the
resolver; `target_category_ids` is still filled directly by the extractor.

### 3. `crawler/crawler/extract/heuristic.py`

- Build the classification blob: `blob = f"{provider} {item.site_name or ''} {text}".lower()`.
- Offer: `offer_category_matches = classify(blob, OFFER_LEXICON)` (stored as-is; ids
  come later).
- Target: `classify(blob, TARGET_LEXICON)` → set of slugs → resolve to ids of the
  **existing** `categories.target` rows by slug (no creation).
- `_match_categories` (the old `name[:5]` matcher) is removed.

### 4. Resolver (crawler side, where `self._api` lives)

A small helper — `resolve_offer_categories(api, cats, matches) -> list[int]` (new
`crawler/crawler/extract/categories.py` or in `payloads.py`; decided in the plan):

- Maintains `cats.offer` as an in-run slug→id cache (list of `{id,name,slug}` dicts).
- For each `(name, slug)`: present → reuse id; absent → `api.create_offer_category(name, slug)`,
  append the returned row to `cats.offer`, use its id.
- Returns the id list. In-run cache means each new vertical is created **once** per pass.

Wiring in `runner._crawl_source` and `harvester.harvest`:
`cand = extract(...)` → `cand.offer_category_ids = resolve_offer_categories(api, cats, cand.offer_category_matches)` → `submit_offer(offer_payload(cand))`.
`offer_payload` is unchanged (still reads `offer_category_ids`).

### 5. `crawler/crawler/api_client.py`

```python
def create_offer_category(self, name: str, slug: str) -> dict:
    r = self._client.post("/api/internal/offer-categories",
                          json={"name": name, "slug": slug})
    r.raise_for_status()
    return r.json()
```

### 6. Backend

- `backend/app/crud/category.py` — add
  `get_or_create_category(db, model, name, slug)`: return the existing row if `slug`
  exists, else create. (Leaves `create_category`'s strict-conflict behaviour intact
  for the admin path.)
- `backend/app/routers/internal.py` — add
  `POST /api/internal/offer-categories` (body `CategoryCreate {name, slug}`) →
  `get_or_create_category(db, OfferCategory, …)` → `CategoryOut`. Guarded by the
  router-level `X-API-Key` dependency. **Offer only** — no internal target-category
  endpoint.

## Data flow

```
Runner.run
  cats = CategoryIndex(target[], offer[])           # public list endpoints
  per source item / per harvested page:
    cand = extractor.extract(item, provider, cats)
      cand.target_category_ids  = ids of existing target rows (lexicon → slug → id)
      cand.offer_category_matches = classify(blob, OFFER_LEXICON)   # (name,slug) list
    cand.offer_category_ids = resolve_offer_categories(api, cats, cand.offer_category_matches)
      # existing slug → reuse id ; new slug → POST /internal/offer-categories → id (+cache)
    api.submit_offer(offer_payload(cand))            # both id lists in payload
```

## Edge cases / safety

- No lexicon match → empty list → offer stays uncategorised (acceptable miss).
- Auto-creation is offer-only and sourced from curated names → garbage impossible.
- `get_or_create` is idempotent by slug; the in-run cache avoids duplicate create
  calls; a single crawler process means no create races.
- `content_hash` untouched (categories are metadata).
- The new internal endpoint is `X-API-Key`-guarded (not publicly reachable).

## Testing (all offline)

**crawler:**
- `tests/test_lexicon.py` — offer + target classification: known-vertical hit,
  new-vertical hit, inflected surface form, precision (short-stem false-match
  avoided), no-match → `[]`, `None`/empty input.
- `tests/test_heuristic.py` (extend) — blob includes `provider`/`site_name` (a
  vertical present only in `site_name` is classified, e.g. Rezervist→sport);
  `offer_category_matches` populated; `target_category_ids` resolved from existing
  rows.
- resolver tests — existing slug reuses id (no API call); missing slug triggers one
  create and caches it; second offer with same new slug makes no second create.
- `tests/test_api_client.py` (or existing) — `create_offer_category` posts to the
  right path with `X-API-Key`.

**backend:**
- `tests/test_internal.py` (extend) — `POST /api/internal/offer-categories` creates a
  new category, returns the existing one on duplicate slug (no error), and requires
  `X-API-Key` (401 without).
- `tests/test_categories.py` (extend) — `get_or_create_category` unit behaviour.

## Out of scope / follow-ups

- Target-axis auto-creation (explicitly rejected).
- IG/FB harvest; news Telegram-channel attribution.
- The lexicon is seed-curated and extensible — adding a vertical is a one-line edit;
  unknown verticals are a harmless miss until curated.
