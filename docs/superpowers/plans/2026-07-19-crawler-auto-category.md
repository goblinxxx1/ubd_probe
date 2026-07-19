# Crawler auto-category via curated lexicon — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Classify offers over site context via a curated keyword lexicon and let the crawler auto-create a new **тематика** (offer category) when the lexicon matches one absent from the DB — target («для кого») is matched-to-existing only, never created.

**Architecture:** A new offline `lexicon.py` (sibling of `geo.py`/`blocklist.py`) maps curated keyword stems to canonical `(name, slug)` pairs for both axes. The extractor classifies over `provider + site_name + text` and emits offer matches as `(name, slug)` pairs (not ids). A crawler-side resolver turns those into ids, creating missing offer categories through a new `X-API-Key`-guarded internal endpoint (get-or-create by slug) while caching within a run.

**Tech Stack:** Python 3.12 (crawler + backend, pytest, httpx.MockTransport, FastAPI TestClient, SQLAlchemy).

## Global Constraints

- Zero-cost, offline, **no cloud LLM** — heuristics / local parsing only.
- Crawler tests run offline from `crawler/`; backend tests from `backend/` (needs `mysql-container` on :3306, root/`my-secret-pw`, DB `ubd_test`).
- Ukrainian UI copy; communicate in Ukrainian.
- `content_hash` identity is owned by the backend; categories are metadata and **must not** enter `content_hash`.
- Auto-creation is **offer-axis only**; the target axis never creates categories.
- Known verticals **reuse the seed slugs**: offer `rozvahy, museums, food, sport, education, transport, medicine`; target `ubd, veteran, war-disability, fallen-family, idp`.

---

### Task 1: Backend — get-or-create internal offer-category endpoint

**Files:**
- Modify: `backend/app/crud/category.py` (add `get_or_create_category`)
- Modify: `backend/app/routers/internal.py` (add route + imports)
- Test: `backend/tests/test_internal.py` (add three)

**Interfaces:**
- Produces: `POST /api/internal/offer-categories` (body `{name, slug}`, `X-API-Key`) → `CategoryOut`; returns the existing row on duplicate slug instead of 409.
- Produces: `category_crud.get_or_create_category(db, model, name, slug) -> model`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_internal.py`:

```python
def test_crawler_creates_offer_category(client, db_session):
    h = {"X-API-Key": settings.crawler_api_key}
    resp = client.post("/api/internal/offer-categories",
                       json={"name": "Автосервіс", "slug": "auto"}, headers=h)
    assert resp.status_code == 200
    assert resp.json()["slug"] == "auto"
    assert [c["slug"] for c in client.get("/api/offer-categories").json()] == ["auto"]


def test_crawler_offer_category_is_get_or_create(client, db_session):
    h = {"X-API-Key": settings.crawler_api_key}
    body = {"name": "Автосервіс", "slug": "auto"}
    r1 = client.post("/api/internal/offer-categories", json=body, headers=h)
    r2 = client.post("/api/internal/offer-categories", json=body, headers=h)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]           # same row, no 409
    assert len(client.get("/api/offer-categories").json()) == 1


def test_internal_offer_category_requires_api_key(client):
    resp = client.post("/api/internal/offer-categories",
                       json={"name": "X", "slug": "x"})
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_internal.py -q`
Expected: FAIL — 404/405 on the new path (route missing).

- [ ] **Step 3: Add `get_or_create_category` to the CRUD**

In `backend/app/crud/category.py`, after `create_category`, add:

```python
def get_or_create_category(db: Session, model, name: str, slug: str):
    obj = db.query(model).filter(model.slug == slug).first()
    if obj is None:
        obj = model(name=name, slug=slug)
        db.add(obj)
        db.commit()
        db.refresh(obj)
    return obj
```

- [ ] **Step 4: Add the internal route**

In `backend/app/routers/internal.py`, add to the imports:

```python
from app.crud import category as category_crud
from app.models import OfferCategory
from app.schemas.category import CategoryCreate, CategoryOut
```

and add the route (e.g. after `submit_suggested_source`):

```python
@router.post("/offer-categories", response_model=CategoryOut)
def create_offer_category(data: CategoryCreate, db: Session = Depends(get_db)):
    return category_crud.get_or_create_category(db, OfferCategory, data.name, data.slug)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_internal.py tests/test_categories.py -q`
Expected: PASS (new three + existing unchanged).

- [ ] **Step 6: Commit**

```bash
git add backend/app/crud/category.py backend/app/routers/internal.py backend/tests/test_internal.py
git commit -m "feat(backend): internal get-or-create offer-category endpoint (X-API-Key)"
```

---

### Task 2: Crawler — curated lexicon module

**Files:**
- Create: `crawler/crawler/discovery/lexicon.py`
- Test: `crawler/tests/test_lexicon.py`

**Interfaces:**
- Produces: `classify(text: str | None, lexicon) -> list[tuple[str, str]]` — deterministic, deduplicated `(name, slug)` list.
- Produces: `OFFER_LEXICON`, `TARGET_LEXICON` — module-level lexicon tables consumed by the extractor (Task 3).

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_lexicon.py
from crawler.discovery.lexicon import classify, OFFER_LEXICON, TARGET_LEXICON


def test_offer_known_vertical_reuses_seed_slug():
    assert ("Кафе/ресторани", "food") in classify("Знижка у нашому кафе", OFFER_LEXICON)


def test_offer_new_vertical_gets_new_slug():
    assert ("Автосервіс", "auto") in classify("Наш автосервіс і шиномонтаж", OFFER_LEXICON)


def test_offer_inflected_surface_form_matches():
    # word-start boundary keeps the inflected suffix ("барбершопі")
    assert ("Краса та догляд", "beauty") in classify("Знижка у барбершопі", OFFER_LEXICON)


def test_offer_no_match_returns_empty():
    assert classify("Просто новина без бізнесу", OFFER_LEXICON) == []


def test_offer_none_and_empty():
    assert classify(None, OFFER_LEXICON) == []
    assert classify("", OFFER_LEXICON) == []


def test_target_maps_military_to_ubd_slug():
    slugs = [s for _, s in classify("Знижка для військових і захисників", TARGET_LEXICON)]
    assert "ubd" in slugs


def test_target_maps_idp():
    slugs = [s for _, s in classify("Пропозиція для переселенців", TARGET_LEXICON)]
    assert "idp" in slugs


def test_classify_is_deduplicated():
    # two food stems in one text still yield a single (name, slug)
    got = classify("кафе і ресторан поруч", OFFER_LEXICON)
    assert got.count(("Кафе/ресторани", "food")) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crawler && python -m pytest tests/test_lexicon.py -q`
Expected: FAIL — `ModuleNotFoundError: crawler.discovery.lexicon`.

- [ ] **Step 3: Write the implementation**

```python
# crawler/crawler/discovery/lexicon.py
"""Offline curated lexicon: map keyword stems to canonical categories.

Precision over recall. Stems are matched at a word-start boundary (no
end-boundary, so inflected suffixes survive) — the same technique as geo.py.
Known verticals REUSE the DB seed slugs; new verticals get fresh slugs and are
lazily created in the DB by the crawler's resolver."""

import re


def _compile(stems):
    return [re.compile(r"(?<!\w)" + re.escape(s)) for s in stems]


# (name, slug, compiled stem patterns). Order is stable => classify() is deterministic.
OFFER_LEXICON = [
    ("Розваги", "rozvahy", _compile((
        "розваг", "квест", "боулінг", "кінотеатр", "атракціон", "караоке",
        "більярд", "лазертаг"))),
    ("Музеї", "museums", _compile((
        "музе", "галере", "виставк", "експозиц"))),
    ("Кафе/ресторани", "food", _compile((
        "кав'ярн", "кафе", "ресторан", "бариста", "піцер", "суші", "паб ",
        "їдальн", "бістро", "кондитер", "пекарн"))),
    ("Спорт", "sport", _compile((
        "спорт", "фітнес", "тренаж", "качалк", "єдиноборст", "басейн", "йога",
        "кросфіт"))),
    ("Освіта", "education", _compile((
        "освіт", "курси", "навчанн", "тренінг", "репетитор", "автошкол",
        "вебінар"))),
    ("Транспорт", "transport", _compile((
        "транспорт", "таксі", "каршеринг", "переїзд", "доставк"))),
    ("Медицина", "medicine", _compile((
        "клінік", "медцентр", "медичн", "діагностик", "реабілітац",
        "офтальмолог"))),
    ("Краса та догляд", "beauty", _compile((
        "перукар", "барбершоп", "манікюр", "педикюр", "косметолог", "епіляц",
        "візаж"))),
    ("Автосервіс", "auto", _compile((
        "автосервіс", "шиномонтаж", "автомийк", "запчастин", "ремонт авто"))),
    ("Аптека", "pharmacy", _compile(("аптек", "фармац"))),
    ("Стоматологія", "dentistry", _compile(("стоматолог", "дантист", "зубн"))),
    ("Одяг та взуття", "clothing", _compile((
        "одяг", "взутт", "ательє", "кросівк"))),
    ("Квіти", "flowers", _compile(("квіт", "флорист", "букет"))),
    ("Готелі та відпочинок", "hotels", _compile((
        "готель", "хостел", "база відпочинк", "санатор", "екскурс"))),
    ("Книги та канцтовари", "books", _compile(("книгарн", "канцтовар"))),
    ("Електроніка", "electronics", _compile((
        "електронік", "гаджет", "смартфон", "ноутбук"))),
    ("Юридичні послуги", "legal", _compile((
        "юридичн", "адвокат", "нотаріус", "юрист"))),
    ("Оптика", "optics", _compile(("оптик", "окуляр", "лінз"))),
]

TARGET_LEXICON = [
    ("УБД", "ubd", _compile((
        "убд", "учасник бойов", "бойових дій", "воїн", "військов", "захисник",
        "зсу", "всу", "тероборон"))),
    ("Ветеран", "veteran", _compile(("ветеран",))),
    ("Особа з інвалідністю внаслідок війни", "war-disability", _compile((
        "інвалід", "інвалідніст"))),
    ("Сім'я загиблого", "fallen-family", _compile((
        "загибл", "полегл", "родин загибл", "вдов"))),
    ("Внутрішньо переміщена особа", "idp", _compile((
        "переселен", "впо", "переміщен особ"))),
]


def classify(text, lexicon):
    if not text:
        return []
    low = text.lower()
    out = []
    for name, slug, patterns in lexicon:
        if any(p.search(low) for p in patterns):
            out.append((name, slug))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd crawler && python -m pytest tests/test_lexicon.py -q`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/lexicon.py crawler/tests/test_lexicon.py
git commit -m "feat(crawler): curated keyword lexicon for offer/target classification"
```

---

### Task 3: Crawler — extractor classifies over site context via the lexicon

**Files:**
- Modify: `crawler/crawler/models.py` (add `offer_category_matches` to `OfferCandidate`)
- Modify: `crawler/crawler/extract/heuristic.py` (imports, blob, classification; remove `_match_categories`)
- Test: `crawler/tests/test_heuristic.py` (update `CATS` + one assertion, add two)

**Interfaces:**
- Consumes: `classify`, `OFFER_LEXICON`, `TARGET_LEXICON` (Task 2).
- Produces: `OfferCandidate.offer_category_matches: list[tuple[str, str]]` (lexicon offer matches); `target_category_ids` resolved from existing `categories.target` rows by slug; `offer_category_ids` left empty here (filled by the resolver in Task 5).

- [ ] **Step 1: Update `CATS` and existing assertions, add new tests**

In `crawler/tests/test_heuristic.py`, change `CATS` to use real seed slugs:

```python
CATS = CategoryIndex(
    target=[{"id": 10, "name": "Ветеран", "slug": "veteran"}],
    offer=[{"id": 20, "name": "Кафе/ресторани", "slug": "food"}],
)
```

In `test_percent_discount_parsed`, replace the two category assertions with:

```python
    assert 10 in cand.target_category_ids                       # "ветеран" → veteran
    assert ("Кафе/ресторани", "food") in cand.offer_category_matches   # "кафе" → food
    assert cand.offer_category_ids == []                        # ids filled later by resolver
```

Append two tests:

```python
def test_offer_category_from_site_name_context():
    it = RawItem(source_id=1, platform="website", key="k",
                 text="Знижка 20% для ветеранів", site_name="Барбершоп Резервіст")
    cand = get_extractor("heuristic").extract(it, "Shop", CATS)
    assert ("Краса та догляд", "beauty") in cand.offer_category_matches


def test_target_from_military_keyword_resolves_existing_only():
    # "військових" → ubd, but CATS has no ubd row → no id resolved (no creation)
    cand = get_extractor("heuristic").extract(
        _item("Знижка 20% для військових"), "Shop", CATS)
    assert cand.target_category_ids == []
```

- [ ] **Step 2: Run tests to verify failures**

Run: `cd crawler && python -m pytest tests/test_heuristic.py -q`
Expected: FAIL — `AttributeError: offer_category_matches` and assertion mismatches.

- [ ] **Step 3: Add `offer_category_matches` to `OfferCandidate`**

In `crawler/crawler/models.py`, in `OfferCandidate`, after `offer_category_ids`:

```python
    offer_category_matches: list[tuple[str, str]] = field(default_factory=list)
```

- [ ] **Step 4: Rewrite classification in the extractor**

In `crawler/crawler/extract/heuristic.py`, add the import next to the geo import:

```python
from crawler.discovery.lexicon import classify, OFFER_LEXICON, TARGET_LEXICON
```

Delete the `_match_categories` function (lines defining it).

In `HeuristicExtractor.extract`, after `low = text.lower()` and before the return, build the classification context and matches:

```python
        blob = f"{provider} {item.site_name or ''} {text}".lower()
        target_slugs = {slug for _, slug in classify(blob, TARGET_LEXICON)}
        target_ids = [c["id"] for c in categories.target if c["slug"] in target_slugs]
        offer_matches = classify(blob, OFFER_LEXICON)
```

Change the returned `OfferCandidate(...)` category kwargs from:

```python
            target_category_ids=_match_categories(low, categories.target),
            offer_category_ids=_match_categories(low, categories.offer),
```

to:

```python
            target_category_ids=target_ids,
            offer_category_matches=offer_matches,
```

- [ ] **Step 5: Run the extractor suite**

Run: `cd crawler && python -m pytest tests/test_heuristic.py -q`
Expected: PASS (existing updated + two new).

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/models.py crawler/crawler/extract/heuristic.py crawler/tests/test_heuristic.py
git commit -m "feat(crawler): classify over provider+site_name+text via lexicon"
```

---

### Task 4: Crawler — offer-category resolver

**Files:**
- Create: `crawler/crawler/extract/categories.py`
- Test: `crawler/tests/test_resolve_categories.py`

**Interfaces:**
- Consumes: `CategoryIndex` (`crawler/crawler/extract/base.py`); an api object exposing `create_offer_category(name, slug) -> dict` (Task 5 adds the real one).
- Produces: `resolve_offer_categories(api, cats, matches) -> list[int]` — reuses existing ids, creates missing offer categories once, caches in `cats.offer`.

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_resolve_categories.py
from crawler.extract.base import CategoryIndex
from crawler.extract.categories import resolve_offer_categories


class _FakeApi:
    def __init__(self, next_id=100):
        self.created = []
        self._next = next_id

    def create_offer_category(self, name, slug):
        self.created.append((name, slug))
        row = {"id": self._next, "name": name, "slug": slug}
        self._next += 1
        return row


def test_empty_matches_touches_nothing():
    api = _FakeApi()
    assert resolve_offer_categories(api, None, []) == []
    assert api.created == []


def test_existing_slug_reuses_id_without_create():
    api = _FakeApi()
    cats = CategoryIndex(offer=[{"id": 20, "name": "Кафе/ресторани", "slug": "food"}])
    ids = resolve_offer_categories(api, cats, [("Кафе/ресторани", "food")])
    assert ids == [20]
    assert api.created == []


def test_missing_slug_creates_once_and_caches():
    api = _FakeApi(next_id=100)
    cats = CategoryIndex(offer=[])
    ids1 = resolve_offer_categories(api, cats, [("Автосервіс", "auto")])
    ids2 = resolve_offer_categories(api, cats, [("Автосервіс", "auto")])
    assert ids1 == [100] and ids2 == [100]
    assert api.created == [("Автосервіс", "auto")]          # created exactly once
    assert {c["slug"] for c in cats.offer} == {"auto"}


def test_mixed_existing_and_new():
    api = _FakeApi(next_id=200)
    cats = CategoryIndex(offer=[{"id": 20, "name": "Кафе/ресторани", "slug": "food"}])
    ids = resolve_offer_categories(
        api, cats, [("Кафе/ресторани", "food"), ("Квіти", "flowers")])
    assert ids == [20, 200]
    assert api.created == [("Квіти", "flowers")]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crawler && python -m pytest tests/test_resolve_categories.py -q`
Expected: FAIL — `ModuleNotFoundError: crawler.extract.categories`.

- [ ] **Step 3: Write the resolver**

```python
# crawler/crawler/extract/categories.py
"""Resolve lexicon (name, slug) offer matches to DB category ids, creating any
missing offer category once per run. cats.offer doubles as the in-run cache."""


def resolve_offer_categories(api, cats, matches) -> list[int]:
    if not matches:
        return []
    by_slug = {c["slug"]: c for c in cats.offer}
    ids = []
    for name, slug in matches:
        row = by_slug.get(slug)
        if row is None:
            row = api.create_offer_category(name, slug)
            cats.offer.append(row)
            by_slug[slug] = row
        ids.append(row["id"])
    return ids
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd crawler && python -m pytest tests/test_resolve_categories.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/extract/categories.py crawler/tests/test_resolve_categories.py
git commit -m "feat(crawler): resolver turns offer-category matches into ids, creating missing"
```

---

### Task 5: Crawler — api client method + wire resolver into runner & harvester

**Files:**
- Modify: `crawler/crawler/api_client.py` (add `create_offer_category`)
- Modify: `crawler/crawler/runner.py` (`_crawl_source`: resolve before submit)
- Modify: `crawler/crawler/discovery/harvest.py` (`_harvest_one`: resolve before submit)
- Test: `crawler/tests/test_runner.py` (extend `FakeApi`, add one test)

**Interfaces:**
- Consumes: `resolve_offer_categories` (Task 4); `OfferCandidate.offer_category_matches` (Task 3).
- Produces: `ApiClient.create_offer_category(name, slug) -> dict`; runner and harvester set `cand.offer_category_ids` via the resolver before `submit_offer`.

- [ ] **Step 1: Write the failing runner test**

In `crawler/tests/test_runner.py`, extend `FakeApi.__init__` and add methods:

```python
    def __init__(self, sources):
        self._sources = sources
        self.offers = []
        self.suggestions = []
        self.state = {}
        self.created = []
        self._offer_cats = []

    def list_offer_categories(self): return list(self._offer_cats)
    def create_offer_category(self, name, slug):
        row = {"id": 900 + len(self.created), "name": name, "slug": slug}
        self.created.append((name, slug)); self._offer_cats.append(row)
        return row
```

(Remove the old one-line `def list_offer_categories(self): return []`.)

Append the test:

```python
def test_runner_autocreates_offer_category():
    src = {"id": 1, "type": "website", "name": "Барбершоп", "url_or_handle": "http://x"}
    item = RawItem(source_id=1, platform="website", key="k",
                   text="Знижка 20% для ветеранів на стрижку у барбершопі", links=[])
    api = FakeApi([src])
    runner = Runner(api, {"website": FakeFetcher([item])}, get_extractor("heuristic"), _rl())

    runner.run()
    assert api.created == [("Краса та догляд", "beauty")]
    assert api.offers[0]["offer_category_ids"] == [900]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd crawler && python -m pytest tests/test_runner.py::test_runner_autocreates_offer_category -q`
Expected: FAIL — `offer_category_ids` is `[]` (resolver not wired).

- [ ] **Step 3: Write the failing api-client test**

Append to `crawler/tests/test_api_client.py`. First add a branch to the shared handler in `_handler` (before the final `return httpx.Response(404, ...)`):

```python
        if request.url.path == "/api/internal/offer-categories":
            body = json.loads(request.content)
            return httpx.Response(200, json={"id": 42, "name": body["name"],
                                             "slug": body["slug"]})
```

Then add the test:

```python
def test_create_offer_category_posts_name_and_slug():
    captured = []
    client = ApiClient("http://api", "secret", 10.0,
                       transport=httpx.MockTransport(_handler(captured)))
    out = client.create_offer_category("Автосервіс", "auto")
    assert out["id"] == 42
    assert captured[-1].url.path == "/api/internal/offer-categories"
    assert captured[-1].headers["X-API-Key"] == "secret"
    body = json.loads(captured[-1].content)
    assert body == {"name": "Автосервіс", "slug": "auto"}
```

Run: `cd crawler && python -m pytest tests/test_api_client.py::test_create_offer_category_posts_name_and_slug -q`
Expected: FAIL — `AttributeError: 'ApiClient' object has no attribute 'create_offer_category'`.

- [ ] **Step 3b: Add the api client method**

In `crawler/crawler/api_client.py`, after `submit_suggestion`:

```python
    def create_offer_category(self, name: str, slug: str) -> dict:
        r = self._client.post("/api/internal/offer-categories",
                              json={"name": name, "slug": slug})
        r.raise_for_status()
        return r.json()
```

Run: `cd crawler && python -m pytest tests/test_api_client.py -q`
Expected: PASS.

- [ ] **Step 4: Wire the resolver into the runner**

In `crawler/crawler/runner.py`, add the import:

```python
from crawler.extract.categories import resolve_offer_categories
```

In `_crawl_source`, change:

```python
            cand = self._extractor.extract(item, source["name"], cats)
            if cand is not None:
                self._api.submit_offer(offer_payload(cand))
                summary["offers"] += 1
```

to:

```python
            cand = self._extractor.extract(item, source["name"], cats)
            if cand is not None:
                cand.offer_category_ids = resolve_offer_categories(
                    self._api, cats, cand.offer_category_matches)
                self._api.submit_offer(offer_payload(cand))
                summary["offers"] += 1
```

- [ ] **Step 5: Wire the resolver into the harvester**

In `crawler/crawler/discovery/harvest.py`, add the import:

```python
from crawler.extract.categories import resolve_offer_categories
```

In `_harvest_one`, change:

```python
            offer = self._extractor.extract(item, attr.provider, cats)
            self._api.submit_offer(offer_payload(offer))
            summary["offers"] += 1
```

to:

```python
            offer = self._extractor.extract(item, attr.provider, cats)
            offer.offer_category_ids = resolve_offer_categories(
                self._api, cats, offer.offer_category_matches)
            self._api.submit_offer(offer_payload(offer))
            summary["offers"] += 1
```

- [ ] **Step 6: Run the runner + harvester suites**

Run: `cd crawler && python -m pytest tests/test_runner.py tests/test_active_harvest.py tests/test_runner_discovery.py -q`
Expected: PASS. (The harvest tests use a gate extractor with empty `offer_category_matches`, so the resolver early-returns `[]` and needs no `create_offer_category` on their fake api.)

- [ ] **Step 7: Commit**

```bash
git add crawler/crawler/api_client.py crawler/crawler/runner.py crawler/crawler/discovery/harvest.py crawler/tests/test_runner.py crawler/tests/test_api_client.py
git commit -m "feat(crawler): auto-create missing offer categories during crawl/harvest"
```

---

## Final verification (after all tasks)

- [ ] `cd crawler && python -m pytest -q` — all green.
- [ ] (If MySQL container up) `cd backend && python -m pytest -q` — all green.
- [ ] **Live Docker check (non-destructive):** rebuild backend+crawler images; capture baseline `max(id)` of `offer_categories`; run one pass `docker compose --profile crawler run --rm -e ACTIVE_DISCOVERY=true -e SEARCH_PROVIDERS=duckduckgo,searxng crawler`; confirm any newly-created offer categories have clean canonical names from the lexicon and that offers carry sane `offer_category_ids`. Note observed new verticals.
- [ ] Update memory `ubd-crawler-discovery-redesign.md` with the auto-category outcome; note remaining follow-ups (target-axis stays curated; IG/FB; news Telegram).
- [ ] Merge to `main` per workflow (`superpowers:finishing-a-development-branch`); push.
