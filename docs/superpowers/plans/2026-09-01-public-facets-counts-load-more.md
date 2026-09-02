# Public Contextual Facet Counts + Load-More Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Public offer filters show only values present in published offers, each with a marketplace-style contextual count, and a "Завантажити ще" button grows the list in place alongside the existing numbered pager.

**Architecture:** New public `GET /api/facets` endpoint returns per-facet value→count, computed under the currently-active filters using disjunctive faceting (a facet ignores its own selection). Public frontend swaps the load-once `useDictionaries` for a reactive `useFacets` that refetches on every filter change; `useOffers` gains an appending `loadMore`. Admin is untouched everywhere.

**Tech Stack:** FastAPI + SQLAlchemy (backend, pytest), Vue 3 `<script setup>` + Vite (public frontend, vitest / @vue/test-utils), Docker for deploy.

## Global Constraints

- **Admin is not touched anywhere.** No file under `admin/src` is edited. No existing function in `crud/offer.py` or `crud/category.py` is edited — only new functions are added. The signature of `list_offers` and the schema `CategoryOut` stay unchanged. Endpoints `/target-categories`, `/offer-categories`, `/locations` stay as-is.
- **Disjunctive faceting:** when counting facet F, apply base (published + not-expired + search `q`) + all *other* facets' selections, but ignore F's own selection.
- **Zero visibility:** a value with `count = 0` is hidden, EXCEPT values currently selected (so a checked box never vanishes). The backend re-injects selected values with their real (possibly 0) count.
- **No Russian language** anywhere (text/lexicons) — project-wide invariant.
- Page size stays `SIZE = 12` (public).
- Backend published-and-not-expired predicate is exactly: `Offer.status == OfferStatus.published AND (Offer.valid_until IS NULL OR Offer.valid_until >= date.today())`.

---

### Task 1: Backend `GET /api/facets` endpoint

**Files:**
- Create: `backend/app/schemas/facets.py`
- Modify: `backend/app/crud/offer.py` (append new functions only; add imports)
- Modify: `backend/app/routers/public.py` (add one route + imports)
- Test: `backend/tests/test_offer_facets.py`

**Interfaces:**
- Produces (crud/offer.py), all keyword-only, all returning plain tuples:
  - `facet_target_categories(db, *, types=None, offer_category_ids=None, locations=None, search=None, selected_ids=None) -> list[tuple[int, str, int]]` — `(id, name, count)`
  - `facet_offer_categories(db, *, types=None, target_category_ids=None, locations=None, search=None, selected_ids=None) -> list[tuple[int, str, int]]`
  - `facet_types(db, *, target_category_ids=None, offer_category_ids=None, locations=None, search=None, selected=None) -> list[tuple[OfferType, int]]`
  - `facet_locations(db, *, types=None, target_category_ids=None, offer_category_ids=None, search=None, selected=None) -> list[tuple[str, int]]`
- Produces (schemas/facets.py): `CategoryFacet{id,name,count}`, `TypeFacet{value,count}`, `LocationFacet{name,count}`, `FacetsOut{target_categories,offer_categories,types,locations}`.
- Produces (HTTP): `GET /api/facets?type=&target_category=&offer_category=&location=&q=` → `FacetsOut`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_offer_facets.py`:

```python
import datetime

from app.crud import offer as offer_crud
from app.models import OfferCategory, TargetCategory
from app.models.enums import CreatedBy, OfferStatus, OfferType
from app.schemas.offer import OfferCreate


def _mk(db, *, title, tt=OfferType.discount, tcs=None, ocs=None, locs=None,
        status=OfferStatus.published, valid_until=None):
    return offer_crud.create_offer(
        db, OfferCreate(type=tt, title=title, provider="P", valid_until=valid_until,
                        target_category_ids=tcs or [], offer_category_ids=ocs or [],
                        locations=locs or []),
        created_by=CreatedBy.admin, status=status)


def _cats(db):
    t1 = TargetCategory(name="УБД", slug="ubd")
    t2 = TargetCategory(name="Ветерани", slug="veteran")
    o1 = OfferCategory(name="Розваги", slug="rozvahy")
    o2 = OfferCategory(name="Здоровʼя", slug="health")
    db.add_all([t1, t2, o1, o2]); db.commit()
    return t1, t2, o1, o2


def test_facets_list_only_present_values(client, db_session):
    t1, t2, o1, o2 = _cats(db_session)
    # only t1/o1 are used by a published offer; t2/o2 have none
    _mk(db_session, title="A", tt=OfferType.discount, tcs=[t1.id], ocs=[o1.id], locs=["Київ"])
    _mk(db_session, title="P", tt=OfferType.event, tcs=[t2.id], ocs=[o2.id], status=OfferStatus.pending_review)
    body = client.get("/api/facets").json()
    assert [c["name"] for c in body["target_categories"]] == ["УБД"]
    assert [c["name"] for c in body["offer_categories"]] == ["Розваги"]
    assert [t["value"] for t in body["types"]] == ["discount"]   # event is only pending
    assert [c["count"] for c in body["target_categories"]] == [1]
    assert [l["name"] for l in body["locations"]] == ["Київ"]


def test_facets_expired_value_excluded(client, db_session):
    t1, _, o1, _ = _cats(db_session)
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    _mk(db_session, title="Exp", tcs=[t1.id], ocs=[o1.id], locs=["Суми"], valid_until=yesterday)
    body = client.get("/api/facets").json()
    assert body["target_categories"] == []
    assert body["locations"] == []


def test_facets_counts_are_contextual(client, db_session):
    t1, t2, o1, o2 = _cats(db_session)
    _mk(db_session, title="A", tcs=[t1.id], ocs=[o1.id], locs=["Київ"])
    _mk(db_session, title="B", tcs=[t1.id], ocs=[o2.id], locs=["Львів"])
    # no filter: УБД has 2
    base = client.get("/api/facets").json()
    assert {c["name"]: c["count"] for c in base["target_categories"]}["УБД"] == 2
    # filter to Київ: УБД contextual count drops to 1, and only o1 theme remains
    kyiv = client.get("/api/facets?location=Київ").json()
    assert {c["name"]: c["count"] for c in kyiv["target_categories"]}["УБД"] == 1
    assert [c["name"] for c in kyiv["offer_categories"]] == ["Розваги"]


def test_facets_are_disjunctive_within_a_facet(client, db_session):
    t1, t2, _, _ = _cats(db_session)
    _mk(db_session, title="A", tcs=[t1.id])
    _mk(db_session, title="B", tcs=[t2.id])
    # selecting t1 must NOT zero out t2 in the target facet (facet ignores its own selection)
    body = client.get(f"/api/facets?target_category={t1.id}").json()
    names = {c["name"]: c["count"] for c in body["target_categories"]}
    assert names == {"УБД": 1, "Ветерани": 1}


def test_facets_selected_value_with_zero_stays(client, db_session):
    t1, t2, _, _ = _cats(db_session)
    _mk(db_session, title="A", tcs=[t1.id], locs=["Київ"])   # Ветерани used by nobody
    # t2 selected but no published offer uses it -> still present with count 0 (so it can be un-checked)
    body = client.get(f"/api/facets?target_category={t2.id}").json()
    names = {c["name"]: c["count"] for c in body["target_categories"]}
    assert names.get("Ветерани") == 0


def test_facets_empty_db(client, db_session):
    body = client.get("/api/facets").json()
    assert body == {"target_categories": [], "offer_categories": [], "types": [], "locations": []}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_offer_facets.py -q`
Expected: FAIL (404 / `/api/facets` route not found, or ImportError on schemas.facets).

- [ ] **Step 3: Create the schema**

Create `backend/app/schemas/facets.py`:

```python
from pydantic import BaseModel

from app.models.enums import OfferType


class CategoryFacet(BaseModel):
    id: int
    name: str
    count: int


class TypeFacet(BaseModel):
    value: OfferType
    count: int


class LocationFacet(BaseModel):
    name: str
    count: int


class FacetsOut(BaseModel):
    target_categories: list[CategoryFacet]
    offer_categories: list[CategoryFacet]
    types: list[TypeFacet]
    locations: list[LocationFacet]
```

- [ ] **Step 4: Add crud facet helpers**

In `backend/app/crud/offer.py`, add imports near the existing ones (top of file):

```python
from sqlalchemy import func
from app.models.categories import offer_offer_categories, offer_target_categories
```

Append at the end of `backend/app/crud/offer.py`:

```python
def _facet_base(db: Session, *, types=None, target_category_ids=None,
                offer_category_ids=None, locations=None, search=None):
    """Published, not-expired offers narrowed by the given facets (all AND-ed).
    Callers pass None for the facet whose own counts they are computing (disjunctive)."""
    q = db.query(Offer).filter(Offer.status == OfferStatus.published)
    q = q.filter((Offer.valid_until.is_(None)) | (Offer.valid_until >= date.today()))
    if types:
        q = q.filter(Offer.type.in_(types))
    if target_category_ids:
        q = q.filter(Offer.target_categories.any(TargetCategory.id.in_(target_category_ids)))
    if offer_category_ids:
        q = q.filter(Offer.offer_categories.any(OfferCategory.id.in_(offer_category_ids)))
    if locations:
        q = q.filter(Offer.locations.any(OfferLocation.name.in_(locations)))
    if search:
        like = f"%{search}%"
        q = q.filter((Offer.title.ilike(like)) | (Offer.description.ilike(like)) | (Offer.provider.ilike(like)))
    return q


def _merge_selected_categories(db, model, rows, selected_ids):
    # rows: list[(id, name, count)]. Re-inject selected ids missing from the grouped
    # result with count 0, so a checked box never disappears. Sorted by name.
    merged = {r[0]: [r[1], r[2]] for r in rows}
    for cid in selected_ids or []:
        if cid not in merged:
            obj = db.get(model, cid)
            if obj is not None:
                merged[cid] = [obj.name, 0]
    out = [(cid, name, cnt) for cid, (name, cnt) in merged.items()]
    out.sort(key=lambda r: r[1])
    return out


def facet_target_categories(db, *, types=None, offer_category_ids=None, locations=None,
                            search=None, selected_ids=None):
    base = _facet_base(db, types=types, offer_category_ids=offer_category_ids,
                       locations=locations, search=search)
    rows = (base.join(offer_target_categories, offer_target_categories.c.offer_id == Offer.id)
                .join(TargetCategory, TargetCategory.id == offer_target_categories.c.target_category_id)
                .with_entities(TargetCategory.id, TargetCategory.name, func.count(func.distinct(Offer.id)))
                .group_by(TargetCategory.id, TargetCategory.name).all())
    return _merge_selected_categories(db, TargetCategory, rows, selected_ids)


def facet_offer_categories(db, *, types=None, target_category_ids=None, locations=None,
                           search=None, selected_ids=None):
    base = _facet_base(db, types=types, target_category_ids=target_category_ids,
                       locations=locations, search=search)
    rows = (base.join(offer_offer_categories, offer_offer_categories.c.offer_id == Offer.id)
                .join(OfferCategory, OfferCategory.id == offer_offer_categories.c.offer_category_id)
                .with_entities(OfferCategory.id, OfferCategory.name, func.count(func.distinct(Offer.id)))
                .group_by(OfferCategory.id, OfferCategory.name).all())
    return _merge_selected_categories(db, OfferCategory, rows, selected_ids)


def facet_types(db, *, target_category_ids=None, offer_category_ids=None, locations=None,
                search=None, selected=None):
    base = _facet_base(db, target_category_ids=target_category_ids,
                       offer_category_ids=offer_category_ids, locations=locations, search=search)
    rows = base.with_entities(Offer.type, func.count(Offer.id)).group_by(Offer.type).all()
    counts = {t: n for t, n in rows}
    for t in selected or []:
        counts.setdefault(t, 0)
    # stable order following the OfferType enum definition
    return [(t, counts[t]) for t in OfferType if t in counts]


def facet_locations(db, *, types=None, target_category_ids=None, offer_category_ids=None,
                    search=None, selected=None):
    base = _facet_base(db, types=types, target_category_ids=target_category_ids,
                       offer_category_ids=offer_category_ids, search=search)
    rows = (base.join(OfferLocation, OfferLocation.offer_id == Offer.id)
                .with_entities(OfferLocation.name, func.count(func.distinct(Offer.id)))
                .group_by(OfferLocation.name).all())
    counts = {name: n for name, n in rows}
    for name in selected or []:
        counts.setdefault(name, 0)
    return sorted(counts.items(), key=lambda r: r[0])
```

- [ ] **Step 5: Add the route**

In `backend/app/routers/public.py`, extend imports:

```python
from app.schemas.facets import CategoryFacet, FacetsOut, LocationFacet, TypeFacet
```

Add this route (place it right after the existing `/locations` route, before `/offers`):

```python
@router.get("/facets", response_model=FacetsOut)
def list_facets(type: list[OfferType] | None = Query(None),
                target_category: list[int] | None = Query(None),
                offer_category: list[int] | None = Query(None),
                location: list[str] | None = Query(None),
                q: str | None = None, db: Session = Depends(get_db)):
    # Marketplace-style contextual facets: each facet's counts honour every OTHER active
    # facet but ignore its own selection (disjunctive), so options never zero themselves out.
    tc = offer_crud.facet_target_categories(db, types=type, offer_category_ids=offer_category,
                                            locations=location, search=q, selected_ids=target_category)
    oc = offer_crud.facet_offer_categories(db, types=type, target_category_ids=target_category,
                                           locations=location, search=q, selected_ids=offer_category)
    tp = offer_crud.facet_types(db, target_category_ids=target_category, offer_category_ids=offer_category,
                                locations=location, search=q, selected=type)
    loc = offer_crud.facet_locations(db, types=type, target_category_ids=target_category,
                                     offer_category_ids=offer_category, search=q, selected=location)
    return FacetsOut(
        target_categories=[CategoryFacet(id=i, name=n, count=c) for i, n, c in tc],
        offer_categories=[CategoryFacet(id=i, name=n, count=c) for i, n, c in oc],
        types=[TypeFacet(value=v, count=c) for v, c in tp],
        locations=[LocationFacet(name=n, count=c) for n, c in loc],
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_offer_facets.py tests/test_offers_public.py -q`
Expected: PASS (new facet tests + existing public tests still green).

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/facets.py backend/app/crud/offer.py backend/app/routers/public.py backend/tests/test_offer_facets.py
git commit -m "feat(public-api): contextual facet counts endpoint /api/facets"
```

---

### Task 2: Public API client — `facets()`

**Files:**
- Modify: `public/src/api/offers.js`
- Test: `public/tests/api/api.test.js`

**Interfaces:**
- Produces: `facets(params) -> Promise<FacetsOut>` calling `GET /facets` with `{ params }`.

- [ ] **Step 1: Write the failing test**

In `public/tests/api/api.test.js`, inside the `describe("offers api", …)` block, add:

```javascript
  it("facets passes filter params", async () => {
    await offers.facets({ type: "discount", location: ["Київ"] });
    expect(client.get).toHaveBeenCalledWith("/facets", { params: { type: "discount", location: ["Київ"] } });
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd public && npx vitest run tests/api/api.test.js`
Expected: FAIL (`offers.facets is not a function`).

- [ ] **Step 3: Implement**

In `public/src/api/offers.js`, add:

```javascript
export const facets = (params) => client.get("/facets", { params }).then((r) => r.data);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd public && npx vitest run tests/api/api.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add public/src/api/offers.js public/tests/api/api.test.js
git commit -m "feat(public): facets() api client"
```

---

### Task 3: `useFacets` composable (replaces `useDictionaries`)

**Files:**
- Create: `public/src/composables/useFacets.js`
- Delete: `public/src/composables/useDictionaries.js`
- Create: `public/tests/composables/useFacets.test.js`
- Delete: `public/tests/composables/useDictionaries.test.js`

**Interfaces:**
- Consumes: `facets(params)` from Task 2.
- Produces: `useFacets() -> { targetCategories, offerCategories, types, locations, load }` — four refs of arrays; refetches on `route.query` change; keeps the previous snapshot on failure (stale-while-revalidate).

- [ ] **Step 1: Write the failing test**

Create `public/tests/composables/useFacets.test.js`:

```javascript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import { h } from "vue";
import { useFacets } from "@/composables/useFacets";

vi.mock("@/api/offers", () => ({
  facets: vi.fn(() => Promise.resolve({
    target_categories: [{ id: 1, name: "УБД", count: 2 }],
    offer_categories: [{ id: 5, name: "Розваги", count: 1 }],
    types: [{ value: "discount", count: 3 }],
    locations: [{ name: "Київ", count: 2 }],
  })),
}));
import * as offers from "@/api/offers";

const Host = { setup: () => useFacets(), render: () => h("div") };

async function mountAt(query) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/", component: Host }] });
  router.push({ path: "/", query });
  await router.isReady();
  const wrapper = mount(Host, { global: { plugins: [router] } });
  await flushPromises();
  return { wrapper, router };
}

describe("useFacets", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads facets on mount and exposes each group", async () => {
    const { wrapper } = await mountAt({});
    expect(offers.facets).toHaveBeenCalledWith({});
    expect(wrapper.vm.targetCategories[0].name).toBe("УБД");
    expect(wrapper.vm.types[0].value).toBe("discount");
    expect(wrapper.vm.locations[0].count).toBe(2);
  });

  it("refetches with the active filters when the query changes", async () => {
    const { router } = await mountAt({});
    await router.push({ path: "/", query: { location: "Київ" } });
    await flushPromises();
    expect(offers.facets).toHaveBeenLastCalledWith({ location: "Київ" });
  });

  it("keeps the previous snapshot when a refetch fails", async () => {
    const { wrapper, router } = await mountAt({});
    offers.facets.mockRejectedValueOnce(new Error("boom"));
    await router.push({ path: "/", query: { q: "x" } });
    await flushPromises();
    expect(wrapper.vm.targetCategories[0].name).toBe("УБД");   // unchanged, not cleared
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd public && npx vitest run tests/composables/useFacets.test.js`
Expected: FAIL (cannot resolve `@/composables/useFacets`).

- [ ] **Step 3: Implement the composable**

Create `public/src/composables/useFacets.js`:

```javascript
import { ref, watch } from "vue";
import { useRoute } from "vue-router";
import { facets as fetchFacets } from "@/api/offers";

const FILTER_KEYS = ["type", "target_category", "offer_category", "location", "q"];

export function useFacets() {
  const route = useRoute();
  const targetCategories = ref([]);
  const offerCategories = ref([]);
  const types = ref([]);
  const locations = ref([]);

  function paramsFromQuery(query) {
    const params = {};
    for (const key of FILTER_KEYS) if (query[key]) params[key] = query[key];
    return params;
  }

  async function load() {
    try {
      // Contextual counts depend on the active filters, so refetch on every change.
      const data = await fetchFacets(paramsFromQuery(route.query));
      targetCategories.value = data.target_categories;
      offerCategories.value = data.offer_categories;
      types.value = data.types;
      locations.value = data.locations;
    } catch {
      // Facets are non-critical filter adornments — keep the last snapshot (no blink) and retry next change.
    }
  }

  watch(() => route.query, load, { immediate: true });

  return { targetCategories, offerCategories, types, locations, load };
}
```

- [ ] **Step 4: Delete the replaced composable and its test**

```bash
git rm public/src/composables/useDictionaries.js public/tests/composables/useDictionaries.test.js
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd public && npx vitest run tests/composables/useFacets.test.js`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add public/src/composables/useFacets.js public/tests/composables/useFacets.test.js
git commit -m "feat(public): reactive useFacets composable, retire useDictionaries"
```

---

### Task 4: `OfferFilters` renders counts and prop-driven type options

**Files:**
- Modify: `public/src/components/OfferFilters.vue`
- Test: `public/tests/components/OfferFilters.test.js`

**Interfaces:**
- Consumes props: `targetCategories: [{id,name,count}]`, `offerCategories: [{id,name,count}]`, `types: [{value,count}]`, `locations: [{name,count}]`, `modelValue: {}`.
- Produces: unchanged `apply` emit contract (arrays of string values); a count `<span>` per option; type options rendered from `props.types` (labels from `OFFER_TYPES`).

- [ ] **Step 1: Update the test file**

Replace the `mountFilters` helper and add count/type tests in `public/tests/components/OfferFilters.test.js`. New `mountFilters`:

```javascript
function mountFilters(modelValue = {}) {
  return mount(OfferFilters, {
    props: {
      modelValue,
      targetCategories: [{ id: 1, name: "УБД", count: 5 }, { id: 2, name: "Ветерани", count: 2 }],
      offerCategories: [{ id: 5, name: "Розваги", count: 3 }],
      types: [{ value: "discount", count: 7 }, { value: "event", count: 1 }],
      locations: [{ name: "Київ", count: 4 }, { name: "Львів", count: 2 }, { name: "Одеса", count: 1 }],
    },
  });
}
```

Add two tests at the end of the `describe` block:

```javascript
  it("shows the contextual count beside each option", () => {
    const w = mountFilters({});
    const firstRow = w.get(".filters__opt");
    expect(firstRow.get(".filters__cnt").text()).toBe("5");
  });

  it("renders only the type options supplied in props", () => {
    const w = mount(OfferFilters, {
      props: {
        modelValue: {},
        targetCategories: [], offerCategories: [], locations: [],
        types: [{ value: "discount", count: 7 }],   // event contextually absent
      },
    });
    const labels = w.findAll(".filters__group").map((g) => g.text());
    expect(labels.join(" ")).toContain("Знижка");
    expect(labels.join(" ")).not.toContain("Подія");
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd public && npx vitest run tests/components/OfferFilters.test.js`
Expected: FAIL (`.filters__cnt` not found; type section still renders from the static constant).

- [ ] **Step 3: Implement the component changes**

In `public/src/components/OfferFilters.vue` `<script setup>`, update props (locations now objects, add `types`):

```javascript
const props = defineProps({
  modelValue: { type: Object, default: () => ({}) },
  targetCategories: { type: Array, default: () => [] },
  offerCategories: { type: Array, default: () => [] },
  types: { type: Array, default: () => [] },
  locations: { type: Array, default: () => [] },
});
```

Add a label map + type options computed (keep the existing `OFFER_TYPES` import):

```javascript
const TYPE_LABELS = Object.fromEntries(OFFER_TYPES.map((t) => [t.value, t.label]));
const typeOptions = computed(() =>
  props.types.map((t) => ({ value: t.value, count: t.count, label: TYPE_LABELS[t.value] || t.value })),
);
```

Update `filteredLocations` to read `.name`:

```javascript
const filteredLocations = computed(() => {
  const term = locSearch.value.trim().toLowerCase();
  return term ? props.locations.filter((c) => c.name.toLowerCase().includes(term)) : props.locations;
});
```

In the template, add a count span to each option and drive types from `typeOptions`. Target group:

```html
      <label v-for="c in targetCategories" :key="c.id" class="filters__opt">
        <input type="checkbox" :value="String(c.id)" v-model="sel.target_category" @change="apply" />
        <span class="filters__opt-name">{{ c.name }}</span>
        <span class="filters__cnt">{{ c.count }}</span>
      </label>
```

Theme (offer categories) group — same pattern with `offerCategories` / `sel.offer_category`. Type group:

```html
      <label v-for="t in typeOptions" :key="t.value" class="filters__opt">
        <input type="checkbox" :value="t.value" v-model="sel.type" @change="apply" />
        <span class="filters__opt-name">{{ t.label }}</span>
        <span class="filters__cnt">{{ t.count }}</span>
      </label>
```

Location group:

```html
        <label v-for="c in filteredLocations" :key="c.name" class="filters__opt">
          <input type="checkbox" :value="c.name" v-model="sel.location" @change="apply" />
          <span class="filters__opt-name">{{ c.name }}</span>
          <span class="filters__cnt">{{ c.count }}</span>
        </label>
```

In `<style scoped>`, let the name take the row and push the count right:

```less
.filters__opt-name { flex: 1 1 auto; min-width: 0; }
.filters__cnt { flex: none; color: @meta-muted; font-size: 12px; font-variant-numeric: tabular-nums; }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd public && npx vitest run tests/components/OfferFilters.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add public/src/components/OfferFilters.vue public/tests/components/OfferFilters.test.js
git commit -m "feat(public): filter options show contextual counts, types from props"
```

---

### Task 5: `useOffers` — appending `loadMore` + `hasMore`

**Files:**
- Modify: `public/src/composables/useOffers.js`
- Test: `public/tests/composables/useOffers.test.js`

**Interfaces:**
- Produces: `useOffers() -> { items, total, loading, loadingMore, error, size, page, hasMore, load, loadMore }`.
  - `page` is the base page from `?page=` (drives the numbered pager, unchanged).
  - `loadMore()` fetches `loadedPage + 1` and **appends** to `items`; no-op while `loadingMore` or when `!hasMore`.
  - filter/page query change resets: replace `items`, `loadedPage = page`.

- [ ] **Step 1: Add failing tests**

In `public/tests/composables/useOffers.test.js`, make the mock page-aware and add load-more tests. Replace the `vi.mock("@/api/offers", …)` block with:

```javascript
vi.mock("@/api/offers", () => ({
  list: vi.fn((params) =>
    Promise.resolve({ items: [{ id: params.page }], total: 3, page: params.page, size: 12 })),
}));
```

Add tests at the end of the `describe` block:

```javascript
  it("appends the next page on loadMore and advances hasMore", async () => {
    const { wrapper } = await mountAt({});
    expect(wrapper.vm.items).toEqual([{ id: 1 }]);
    expect(wrapper.vm.hasMore).toBe(true);
    await wrapper.vm.loadMore();
    await flushPromises();
    expect(offers.list).toHaveBeenLastCalledWith({ page: 2, size: 12 });
    expect(wrapper.vm.items).toEqual([{ id: 1 }, { id: 2 }]);
  });

  it("stops offering more once every item is loaded", async () => {
    const { wrapper } = await mountAt({});
    await wrapper.vm.loadMore();   // page 2
    await wrapper.vm.loadMore();   // page 3 -> 3 items == total
    await flushPromises();
    expect(wrapper.vm.items.map((i) => i.id)).toEqual([1, 2, 3]);
    expect(wrapper.vm.hasMore).toBe(false);
  });

  it("resets to the base page when filters change", async () => {
    const { wrapper, router } = await mountAt({});
    await wrapper.vm.loadMore();
    await router.push({ path: "/", query: { q: "кава" } });
    await flushPromises();
    expect(wrapper.vm.items).toEqual([{ id: 1 }]);   // fresh page 1, not appended
  });
```

Note: the existing tests (`builds params`, `reads page from query`, `reloads when query changes`, `sets error`) remain valid — do not change them.

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `cd public && npx vitest run tests/composables/useOffers.test.js`
Expected: FAIL (`loadMore is not a function`, `hasMore` undefined).

- [ ] **Step 3: Rewrite the composable**

Replace the whole body of `public/src/composables/useOffers.js`:

```javascript
import { ref, computed, watch } from "vue";
import { useRoute } from "vue-router";
import * as offersApi from "@/api/offers";
import { extractError } from "@/utils/errors";

const SIZE = 12;
const FILTER_KEYS = ["type", "target_category", "offer_category", "location", "q"];

export function useOffers() {
  const route = useRoute();
  const items = ref([]);
  const total = ref(0);
  const loading = ref(false);        // initial / reset load
  const loadingMore = ref(false);    // appending load ("Завантажити ще")
  const error = ref(null);
  const page = computed(() => Number(route.query.page) || 1);   // base page for the numbered pager
  const loadedPage = ref(page.value);
  const hasMore = computed(() => items.value.length < total.value);

  function paramsForPage(p) {
    const params = { page: p, size: SIZE };
    for (const key of FILTER_KEYS) if (route.query[key]) params[key] = route.query[key];
    return params;
  }

  async function load() {
    loading.value = true;
    error.value = null;
    loadedPage.value = page.value;
    try {
      const data = await offersApi.list(paramsForPage(page.value));
      items.value = data.items;
      total.value = data.total;
    } catch (e) {
      error.value = extractError(e);
      items.value = [];
      total.value = 0;
    } finally {
      loading.value = false;
    }
  }

  async function loadMore() {
    if (loadingMore.value || !hasMore.value) return;
    loadingMore.value = true;
    error.value = null;
    try {
      const next = loadedPage.value + 1;
      const data = await offersApi.list(paramsForPage(next));
      items.value = [...items.value, ...data.items];
      total.value = data.total;
      loadedPage.value = next;
    } catch (e) {
      error.value = extractError(e);
    } finally {
      loadingMore.value = false;
    }
  }

  watch(() => route.query, load, { immediate: true });

  return { items, total, loading, loadingMore, error, size: SIZE, page, hasMore, load, loadMore };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd public && npx vitest run tests/composables/useOffers.test.js`
Expected: PASS (old + new).

- [ ] **Step 5: Commit**

```bash
git add public/src/composables/useOffers.js public/tests/composables/useOffers.test.js
git commit -m "feat(public): useOffers loadMore appends next page, hasMore gauge"
```

---

### Task 6: `LoadMore.vue` button component

**Files:**
- Create: `public/src/components/LoadMore.vue`
- Test: `public/tests/components/LoadMore.test.js`

**Interfaces:**
- Consumes props: `hasMore: Boolean`, `loading: Boolean`, `shown: Number`, `total: Number`.
- Produces: renders nothing when `!hasMore`; a button that emits `load` on click, disabled while `loading`; a "Показано X з Y" meta line.

- [ ] **Step 1: Write the failing test**

Create `public/tests/components/LoadMore.test.js`:

```javascript
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import LoadMore from "@/components/LoadMore.vue";

describe("LoadMore", () => {
  it("renders nothing when there is no more to load", () => {
    const w = mount(LoadMore, { props: { hasMore: false, shown: 12, total: 12 } });
    expect(w.find(".loadmore__btn").exists()).toBe(false);
  });

  it("emits load on click and shows progress", async () => {
    const w = mount(LoadMore, { props: { hasMore: true, loading: false, shown: 12, total: 40 } });
    expect(w.get(".loadmore__meta").text()).toContain("12");
    expect(w.get(".loadmore__meta").text()).toContain("40");
    await w.get(".loadmore__btn").trigger("click");
    expect(w.emitted().load).toBeTruthy();
  });

  it("disables the button while loading", () => {
    const w = mount(LoadMore, { props: { hasMore: true, loading: true, shown: 12, total: 40 } });
    expect(w.get(".loadmore__btn").attributes("disabled")).toBeDefined();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd public && npx vitest run tests/components/LoadMore.test.js`
Expected: FAIL (cannot resolve `@/components/LoadMore.vue`).

- [ ] **Step 3: Implement the component**

Create `public/src/components/LoadMore.vue`:

```vue
<script setup>
defineProps({
  hasMore: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  shown: { type: Number, default: 0 },
  total: { type: Number, default: 0 },
});
const emit = defineEmits(["load"]);
</script>

<template>
  <div v-if="hasMore" class="loadmore">
    <button class="loadmore__btn" type="button" :disabled="loading" @click="emit('load')">
      {{ loading ? "Завантаження…" : "Завантажити ще" }}
    </button>
    <p class="loadmore__meta">Показано {{ shown }} з {{ total }}</p>
  </div>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.loadmore { display: flex; flex-direction: column; align-items: center; gap: 8px; margin: 24px 0 8px; }
.loadmore__btn {
  padding: 10px 22px; border: 1px solid @border; border-radius: @radius-sm; background: @card-bg;
  color: @text; font-size: 15px; font-weight: 600; cursor: pointer;
}
.loadmore__btn:not(:disabled):hover { border-color: @link; }
.loadmore__btn:disabled { opacity: 0.6; cursor: default; }
.loadmore__meta { color: @muted; font-size: 13px; margin: 0; }
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd public && npx vitest run tests/components/LoadMore.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add public/src/components/LoadMore.vue public/tests/components/LoadMore.test.js
git commit -m "feat(public): LoadMore button component"
```

---

### Task 7: Wire `OffersView` to facets + LoadMore

**Files:**
- Modify: `public/src/views/OffersView.vue`
- Test: `public/tests/views/OffersView.test.js`

**Interfaces:**
- Consumes: `useFacets` (Task 3), `useOffers` `{ loadingMore, hasMore, loadMore }` (Task 5), `LoadMore` (Task 6).
- Produces: `OfferFilters` receives `:types="types"` and count-bearing lists; `LoadMore` sits between `OfferGrid` and `Pagination`.

- [ ] **Step 1: Update the test file**

In `public/tests/views/OffersView.test.js`, swap the category/locations mocks for a `facets` mock. Replace the two `vi.mock(...)` blocks with:

```javascript
vi.mock("@/api/offers", () => ({
  list: vi.fn(() => Promise.resolve({ items: [{ id: 1, type: "event", title: "T", provider: "P", target_categories: [] }], total: 1, page: 1, size: 12 })),
  facets: vi.fn(() => Promise.resolve({ target_categories: [], offer_categories: [], types: [], locations: [] })),
}));
import * as offers from "@/api/offers";
```

Add one test at the end of the `describe` block:

```javascript
  it("renders the load-more control in the main column", async () => {
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    const w = mount(OffersView, { global: { plugins: [router] } });
    await flushPromises();
    expect(w.getComponent({ name: "LoadMore" }).exists()).toBe(true);
  });
```

The existing OffersView tests (loads on mount, applying filters refetches, sidebar present, mobile drawer, changing page) stay valid — the `facets` mock covers the new composable.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd public && npx vitest run tests/views/OffersView.test.js`
Expected: FAIL (`useDictionaries` import gone / `LoadMore` not found in the view).

- [ ] **Step 3: Implement the view changes**

In `public/src/views/OffersView.vue` `<script setup>`:

- Replace the import and composable use:

```javascript
import { useFacets } from "@/composables/useFacets";
import LoadMore from "@/components/LoadMore.vue";
```

Remove the `useDictionaries` import and its `onMounted(loadDicts)` line (and the now-unused `onMounted` import). Replace the two composable lines with:

```javascript
const { items, total, loading, loadingMore, error, size, page, hasMore, loadMore } = useOffers();
const { targetCategories, offerCategories, types, locations } = useFacets();
```

- In the template, pass `types` to `OfferFilters`:

```html
        <OfferFilters
          :model-value="currentFilters"
          :target-categories="targetCategories"
          :offer-categories="offerCategories"
          :types="types"
          :locations="locations"
          @apply="onApply"
        />
```

- Insert `LoadMore` between the grid and the pager in `.offers__main`:

```html
      <main class="offers__main">
        <OfferGrid :offers="items" :loading="loading" :error="error" />
        <LoadMore :has-more="hasMore" :loading="loadingMore" :shown="items.length" :total="total" @load="loadMore" />
        <Pagination :total="total" :size="size" :page="page" @change="onPage" />
      </main>
```

- [ ] **Step 4: Run the full public suite to verify it passes**

Run: `cd public && npx vitest run`
Expected: PASS (all public tests, including views/composables/components/api).

- [ ] **Step 5: Commit**

```bash
git add public/src/views/OffersView.vue public/tests/views/OffersView.test.js
git commit -m "feat(public): OffersView uses contextual facets and load-more"
```

---

### Task 8: Full verification + deploy rebuild

**Files:** none (verification only).

- [ ] **Step 1: Backend suite**

Run: `cd backend && python -m pytest -q`
Expected: PASS (no regressions; new `test_offer_facets.py` green).

- [ ] **Step 2: Public build + suite**

Run: `cd public && npm run build && npx vitest run`
Expected: build succeeds (catches scoped-Less errors that vitest misses), all tests PASS.

- [ ] **Step 3: Rebuild containers**

Run: `docker compose up -d --build public backend`
Expected: both images rebuild and start.

- [ ] **Step 4: Live-check the endpoint**

Run: `curl -s "http://localhost:8000/api/facets" | head -c 400`
Expected: JSON with `target_categories`/`offer_categories`/`types`/`locations` arrays whose entries carry a `count`.

- [ ] **Step 5: Live-check the bundle carries load-more**

Run: `curl -s http://localhost:8080/ | grep -oE 'assets/index-[^"]+\.js' | head -1`
then `curl` that JS asset and confirm it contains `Завантажити ще`.
Expected: the string is present in the shipped bundle.

- [ ] **Step 6: Final commit (if any verification tweaks were needed)**

```bash
git add -A
git commit -m "chore(public): verify facets + load-more build and deploy" --allow-empty
```

---

## Self-Review Notes

- **Spec coverage:** contextual counts (Task 1 tests `test_facets_counts_are_contextual`), disjunctive faceting (`test_facets_are_disjunctive_within_a_facet`), selected-zero visibility (`test_facets_selected_value_with_zero_stays`), present-only values incl. types (`test_facets_list_only_present_values`), expired exclusion (`test_facets_expired_value_excluded`), empty DB (`test_facets_empty_db`); frontend counts (Task 4), reactive facets (Task 3), load-more append + both controls (Tasks 5–7); admin untouched (only additive backend + `public/` edits). All covered.
- **Admin guardrail:** no task edits `admin/src`, `list_offers`, `list_categories`, or `CategoryOut`; `/target-categories`, `/offer-categories`, `/locations` remain.
- **Type consistency:** crud returns tuples `(id,name,count)` / `(value,count)` / `(name,count)`; router maps them to `CategoryFacet`/`TypeFacet`/`LocationFacet`; frontend reads `.count`, `.name`, `.value`, `.id` consistently across `useFacets`, `OfferFilters`, `LoadMore`.
