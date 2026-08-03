# Admin UX (top pagination + return-to-origin + live badge) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Steps use `- [ ]` checkboxes.

**Goal:** Three admin UX fixes — pagination bar above the list, save returns to the originating section+tab, and the sidebar moderation badge updates live after offer mutations.

**Architecture:** All admin-only (Vue 3 + Element Plus + Pinia). A new Pinia `moderation` store holds `pendingCount`; `AdminLayout` and `OffersListView` share it. The offers tab moves into the URL query so it survives an edit round-trip.

**Tech Stack:** Vue 3, Element Plus, Pinia, Vitest.

## Global Constraints

- Admin-only; backend/crawler unchanged.
- User-facing strings in Ukrainian.
- Before merge: `npm test` AND `npm run build` (Vitest doesn't compile scoped-Less).
- Run admin tests from `admin/`; TDD test-first; frequent commits.
- Pagination only exists in `OffersListView` (Offers + Moderation routes) — do not add it elsewhere.

---

### Task 1: Moderation store + live badge in AdminLayout

**Files:**
- Create: `admin/src/stores/moderation.js`
- Modify: `admin/src/layouts/AdminLayout.vue`
- Test: `admin/tests/stores/moderation.test.js` (create), `admin/tests/layouts/AdminLayout.test.js`

**Interfaces:**
- Produces: `useModerationStore()` with reactive `pendingCount` and async `refresh()`.

- [ ] **Step 1: Write failing store test**

`admin/tests/stores/moderation.test.js`:
```javascript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { createPinia, setActivePinia } from "pinia";
vi.mock("@/api/offers", () => ({ list: vi.fn(() => Promise.resolve({ total: 7 })) }));
import * as offers from "@/api/offers";
import { useModerationStore } from "@/stores/moderation";

describe("moderation store", () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks(); });

  it("refresh loads the pending_review total", async () => {
    const s = useModerationStore();
    expect(s.pendingCount).toBe(0);
    await s.refresh();
    expect(offers.list).toHaveBeenCalledWith({ status: "pending_review", size: 1 });
    expect(s.pendingCount).toBe(7);
  });

  it("refresh swallows errors and keeps prior count", async () => {
    offers.list.mockRejectedValueOnce(new Error("x"));
    const s = useModerationStore();
    await s.refresh();
    expect(s.pendingCount).toBe(0);
  });
});
```

- [ ] **Step 2: Run — fails** (`npm test -- moderation`) — module missing.

- [ ] **Step 3: Implement store**

`admin/src/stores/moderation.js`:
```javascript
import { defineStore } from "pinia";
import { ref } from "vue";
import * as offers from "@/api/offers";

export const useModerationStore = defineStore("moderation", () => {
  const pendingCount = ref(0);
  async function refresh() {
    try {
      const result = await offers.list({ status: "pending_review", size: 1 });
      pendingCount.value = result?.total ?? 0;
    } catch {
      // badge is non-critical — keep the previous value
    }
  }
  return { pendingCount, refresh };
});
```

- [ ] **Step 4: Wire AdminLayout to the store**

In `admin/src/layouts/AdminLayout.vue` `<script setup>`: remove the local `pendingCount` ref and the inline `offers.list` call; instead:
```javascript
import { useModerationStore } from "@/stores/moderation";
const moderation = useModerationStore();
onMounted(() => { moderation.refresh(); });
```
Template badge becomes:
```html
<el-badge :value="moderation.pendingCount" :hidden="!moderation.pendingCount">Черга модерації</el-badge>
```
(Keep the existing `offers` import only if still used; it is no longer needed here — remove it.)

- [ ] **Step 5: Update AdminLayout test**

In `admin/tests/layouts/AdminLayout.test.js`, ensure a Pinia instance is active (add `setActivePinia(createPinia())` in `beforeEach` and import from pinia) and mock `@/api/offers` `list` to resolve `{ total: N }`; assert the badge shows N after mount. (Match existing test structure; add pinia plugin to the mount `global.plugins` if not present.)

- [ ] **Step 6: Run tests** (`npm test -- moderation AdminLayout`) — pass.

- [ ] **Step 7: Commit**
```bash
git add admin/src/stores/moderation.js admin/src/layouts/AdminLayout.vue admin/tests/stores/moderation.test.js admin/tests/layouts/AdminLayout.test.js
git commit -m "feat(admin): moderation pending-count store + live sidebar badge"
```

---

### Task 2: OffersListView actions refresh the badge

**Files:**
- Modify: `admin/src/views/OffersListView.vue`
- Test: `admin/tests/views/OffersListView.test.js`

**Interfaces:**
- Consumes: `useModerationStore().refresh()` (Task 1).

- [ ] **Step 1: Write failing test**

In `admin/tests/views/OffersListView.test.js` — the mount already needs Pinia (createPinia in beforeEach exists). Add a spy on the store's refresh:
```javascript
import { useModerationStore } from "@/stores/moderation";

it("publish refreshes the moderation badge count", async () => {
  const router = makeRouter();
  router.push("/"); await router.isReady();
  const wrapper = mount(OffersListView, { global: { plugins: [router, ElementPlus] } });
  await flushPromises();
  const store = useModerationStore();
  const spy = vi.spyOn(store, "refresh");
  await wrapper.vm.onPublish(1);
  await flushPromises();
  expect(spy).toHaveBeenCalled();
});
```
(`@/api/offers` is already mocked in this file; `useModerationStore` will call the mocked `offers.list`.)

- [ ] **Step 2: Run — fails** (`npm test -- OffersListView -t "refreshes the moderation badge"`).

- [ ] **Step 3: Implement**

In `OffersListView.vue` `<script setup>`:
```javascript
import { useModerationStore } from "@/stores/moderation";
const moderation = useModerationStore();
```
In each of `onPublish`, `onReject`, `onDelete`, `onRestore`, after the existing `await load();` (inside the try, success path), add:
```javascript
    moderation.refresh();
```

- [ ] **Step 4: Run tests** (`npm test -- OffersListView`) — pass.

- [ ] **Step 5: Commit**
```bash
git add admin/src/views/OffersListView.vue admin/tests/views/OffersListView.test.js
git commit -m "feat(admin): refresh moderation badge after offer publish/reject/delete/restore"
```

---

### Task 3: Pagination bar above the list

**Files:**
- Modify: `admin/src/views/OffersListView.vue`
- Test: `admin/tests/views/OffersListView.test.js`

**Interfaces:** none new.

- [ ] **Step 1: Write failing test**

```javascript
it("renders a pagination bar both above and below the table", async () => {
  offers.list.mockResolvedValueOnce({
    items: [{ id: 1, title: "T", provider: "P", type: "discount", status: "published", valid_until: null }],
    total: 40,
  });
  const router = makeRouter();
  router.push("/"); await router.isReady();
  const wrapper = mount(OffersListView, { global: { plugins: [router, ElementPlus] } });
  await flushPromises();
  expect(wrapper.findAllComponents({ name: "ElPagination" }).length).toBe(2);
});
```

- [ ] **Step 2: Run — fails** (only 1 pagination today).

- [ ] **Step 3: Implement**

In `OffersListView.vue` template, add a pagination block immediately after the `</DataTableToolbar>` (above `<ResponsiveTable>`), identical to the existing bottom one:
```html
    <el-pagination
      layout="prev, pager, next"
      :total="total"
      :page-size="size"
      :current-page="page"
      @current-change="setPage"
    />
```
Leave the existing bottom `<el-pagination>` unchanged.

- [ ] **Step 4: Run tests** (`npm test -- OffersListView`) — pass.

- [ ] **Step 5: Commit**
```bash
git add admin/src/views/OffersListView.vue admin/tests/views/OffersListView.test.js
git commit -m "feat(admin): pagination bar above the offers list"
```

---

### Task 4: Return to originating section + tab after save

**Files:**
- Modify: `admin/src/views/OffersListView.vue`, `admin/src/views/OfferFormView.vue`
- Test: `admin/tests/views/OffersListView.test.js`, `admin/tests/views/OfferFormView.test.js`

**Interfaces:**
- Produces: edit/new navigation carries `query: { from, tab }`; `OfferFormView` returns to `{ name: from||'offers', query: tab?{tab}:{} }`.

- [ ] **Step 1: Write failing tests**

OffersListView — tab initialises from the URL and edit carries origin:
```javascript
it("initialises the tab from the URL query", async () => {
  const router = makeRouter();
  router.push("/?tab=rejected"); await router.isReady();
  const wrapper = mount(OffersListView, { global: { plugins: [router, ElementPlus] } });
  await flushPromises();
  expect(offers.list).toHaveBeenCalledWith({ status: "rejected", page: 1, size: 20 });
});

it("edit navigates with from + tab query", async () => {
  const router = makeRouter();
  const spy = vi.spyOn(router, "push");
  router.push("/"); await router.isReady();
  const wrapper = mount(OffersListView, { global: { plugins: [router, ElementPlus] } });
  await flushPromises();
  wrapper.vm.tab = "pending_review";
  wrapper.vm.edit(5);
  expect(spy).toHaveBeenCalledWith({ name: "offer-edit", params: { id: 5 },
    query: { from: "offers", tab: "pending_review" } });
});
```
OfferFormView — returns to origin (extend the existing mock router to accept query; assert push target). Add to `admin/tests/views/OfferFormView.test.js` a test that, given `route.query = { from: 'moderation' }`, `onSubmit` pushes `{ name: 'moderation', query: {} }`; and given `{ from:'offers', tab:'rejected' }`, pushes `{ name:'offers', query:{ tab:'rejected' } }`. Follow the file's existing mount/route-stub pattern (use a memory router with an `offer-edit` route carrying the query, or set `route` via `useRoute` mock as the file already does).

- [ ] **Step 2: Run — fails** (`npm test -- OffersListView OfferFormView`).

- [ ] **Step 3: Implement OffersListView**

`<script setup>`: import `useRoute`; `const route = useRoute();`
Initialise tab from URL (only when not fixedStatus):
```javascript
const tab = ref(props.fixedStatus ? "pending_review" : (route.query.tab || "published"));
```
On tab change, reflect it in the URL (only for the tabbed offers view). Change the `<el-tabs>` handler to a method:
```javascript
function onTabChange() {
  if (!props.fixedStatus) router.replace({ query: { ...route.query, tab: tab.value } });
  applyFilters({});
}
```
and template `@tab-change="onTabChange"`.
`edit(id)`:
```javascript
function edit(id) {
  const query = props.fixedStatus ? { from: route.name } : { from: route.name, tab: tab.value };
  router.push({ name: "offer-edit", params: { id }, query });
}
```
"Створити оффер" button → `@click="router.push({ name: 'offer-new', query: { from: route.name } })"`.
Add `edit` to `defineExpose` if not present (it is used in template; expose for the test).

- [ ] **Step 4: Implement OfferFormView**

`<script setup>` already has `route`. Add a helper and use it in all three exits:
```javascript
function backToOrigin() {
  const from = route.query.from || "offers";
  const query = route.query.tab ? { tab: route.query.tab } : {};
  router.push({ name: from, query });
}
```
Replace the three `router.push({ name: "offers" })` occurrences (`onSubmit`, `onSubmitPublish`, and the template `@cancel`) with `backToOrigin()`. For `@cancel`, change to `@cancel="backToOrigin"` and expose `backToOrigin` via `defineExpose`.

- [ ] **Step 5: Run tests** (`npm test -- OffersListView OfferFormView`) — pass.

- [ ] **Step 6: Full suite + build**

`npm test` then `npm run build` — all green, build clean.

- [ ] **Step 7: Commit**
```bash
git add admin/src/views/OffersListView.vue admin/src/views/OfferFormView.vue admin/tests/views/OffersListView.test.js admin/tests/views/OfferFormView.test.js
git commit -m "feat(admin): save returns to originating section + tab"
```

---

## Self-Review notes
- Task-1 covers spec §3 (store + AdminLayout badge). Task-2 covers spec §3 mutation wiring. Task-3 covers spec §1. Task-4 covers spec §2 (tab-in-URL, from/tab passing, OfferFormView return).
- No placeholders; each code step shows the code.
- Type/name consistency: `useModerationStore`/`refresh`/`pendingCount`, `backToOrigin`, `onTabChange`, `edit` used consistently across tasks.
- Deploy after merge: canonical rebuild of `admin` image only. Update memory.
