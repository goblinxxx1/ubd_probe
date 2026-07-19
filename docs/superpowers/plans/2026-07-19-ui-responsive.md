# Responsive admin + public — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the admin app usable down to phone width (drawer nav + tables that collapse to cards) and give the public app a full responsive pass.

**Architecture:** A shared breakpoint set (`640` / `1024`) plus a small `useBreakpoint()` composable drive two admin pieces: an off-canvas sidebar drawer (≤1024) and a `ResponsiveTable` wrapper that renders `el-table` on desktop and a card stack on phones (≤640) from a single column definition. Public work is CSS/template only (real header links + a breakpoint audit).

**Tech Stack:** Vue 3 (`<script setup>`), Element Plus (admin), plain Less (public), Vitest + @vue/test-utils, Vite.

## Global Constraints

- **Verification gate per app, every task that touches it:** `npm run build` (catches scoped-Less errors Vitest misses — established project lesson) AND `npm test` (Vitest) must both pass before commit.
- **No visual redesign / re-theming.** Layout & responsiveness only. Keep existing Less tokens, colors, typography. No backend changes. No new admin features.
- **Breakpoints (exact):** mobile = `max-width: 640px` (inclusive); tablet = `max-width: 1024px` (inclusive); desktop = `> 640` / `> 1024`.
- **Keep existing suites green:** admin 77 tests, public 59 tests. New components add tests; don't delete coverage.
- **Commit after every task.** Branch: `feat/ui-responsive` (already created from `main`).

---

## Task 1: matchMedia test mock + shared tokens + `useBreakpoint` (admin)

**Files:**
- Modify: `admin/vitest.setup.js` (add `window.matchMedia` mock)
- Modify: `admin/src/styles/variables.less` (add breakpoint tokens)
- Create: `admin/src/composables/useBreakpoint.js`
- Test: `admin/tests/composables/useBreakpoint.test.js`

**Interfaces:**
- Produces: `useBreakpoint() -> { isMobile: Ref<boolean>, isTablet: Ref<boolean> }`. `isMobile` true at viewport ≤640px, `isTablet` true at ≤1024px. Consumed by Tasks 2 and 3.

- [ ] **Step 1: Add a matchMedia mock to the Vitest setup** (jsdom lacks it; default `matches:false` = desktop so existing view tests keep seeing `el-table`).

Append to `admin/vitest.setup.js`:
```js
if (!global.matchMedia) {
  global.matchMedia = (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent() { return false; },
  });
}
```

- [ ] **Step 2: Add breakpoint tokens** to `admin/src/styles/variables.less` (end of file):
```less
@bp-mobile: 640px;      // phone: table→cards, drawer nav
@bp-tablet: 1024px;     // tablet-portrait and below: drawer nav
```

- [ ] **Step 3: Write the failing test** `admin/tests/composables/useBreakpoint.test.js`:
```js
import { describe, it, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { useBreakpoint } from "@/composables/useBreakpoint";

function harness() {
  return mount({ template: "<div/>", setup() { return useBreakpoint(); } });
}

describe("useBreakpoint", () => {
  it("is desktop when matchMedia reports no match", () => {
    window.matchMedia = vi.fn(() => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
    const w = harness();
    expect(w.vm.isMobile).toBe(false);
    expect(w.vm.isTablet).toBe(false);
  });

  it("is mobile+tablet when both queries match", () => {
    window.matchMedia = vi.fn(() => ({ matches: true, addEventListener() {}, removeEventListener() {} }));
    const w = harness();
    expect(w.vm.isMobile).toBe(true);
    expect(w.vm.isTablet).toBe(true);
  });
});
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd admin && npm test -- useBreakpoint`
Expected: FAIL — `Failed to resolve import "@/composables/useBreakpoint"`.

- [ ] **Step 5: Implement `admin/src/composables/useBreakpoint.js`:**
```js
import { ref, onMounted, onUnmounted } from "vue";

export function useBreakpoint() {
  const mqMobile = window.matchMedia("(max-width: 640px)");
  const mqTablet = window.matchMedia("(max-width: 1024px)");
  const isMobile = ref(mqMobile.matches);
  const isTablet = ref(mqTablet.matches);

  const update = () => {
    isMobile.value = mqMobile.matches;
    isTablet.value = mqTablet.matches;
  };

  onMounted(() => {
    mqMobile.addEventListener("change", update);
    mqTablet.addEventListener("change", update);
  });
  onUnmounted(() => {
    mqMobile.removeEventListener("change", update);
    mqTablet.removeEventListener("change", update);
  });

  return { isMobile, isTablet };
}
```

- [ ] **Step 6: Run tests + build**

Run: `cd admin && npm test -- useBreakpoint` → PASS. Then `npm test` (full, 77+2 green) and `npm run build` (clean).

- [ ] **Step 7: Commit**
```bash
git add admin/vitest.setup.js admin/src/styles/variables.less admin/src/composables/useBreakpoint.js admin/tests/composables/useBreakpoint.test.js
git commit -m "feat(admin): useBreakpoint composable + matchMedia test mock + bp tokens"
```

---

## Task 2: Admin shell — off-canvas drawer + hamburger

**Files:**
- Modify: `admin/src/layouts/AdminLayout.vue`
- Test: `admin/tests/layouts/AdminLayout.test.js` (extend if present; else create)

**Interfaces:**
- Consumes: `useBreakpoint` (Task 1).
- Produces: `AdminLayout` exposes `drawerOpen: Ref<boolean>` for testing.

- [ ] **Step 1: Write the failing test** — add to (or create) `admin/tests/layouts/AdminLayout.test.js`:
```js
import { describe, it, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import ElementPlus from "element-plus";
import AdminLayout from "@/layouts/AdminLayout.vue";

// AdminLayout fetches a pending-count badge on mount; stub it (non-critical).
vi.mock("@/api/offers", () => ({ list: vi.fn(() => Promise.resolve({ total: 0 })) }));

const stubs = { "router-link": true, "router-view": true };

describe("AdminLayout drawer", () => {
  it("starts closed and toggles open", async () => {
    const w = mount(AdminLayout, { global: { plugins: [ElementPlus, createPinia()], stubs } });
    expect(w.vm.drawerOpen).toBe(false);
    w.vm.drawerOpen = true;
    await w.vm.$nextTick();
    expect(w.find(".sidebar--open").exists()).toBe(true);
  });
});
```
(If an `AdminLayout.test.js` already exists, mirror its Pinia/mock setup instead of duplicating.)

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && npm test -- AdminLayout`
Expected: FAIL — `drawerOpen` undefined / `.sidebar--open` not found.

- [ ] **Step 3: Implement drawer in `AdminLayout.vue`.** In `<script setup>` add:
```js
import { ref } from "vue";
import { useBreakpoint } from "@/composables/useBreakpoint";
const { isTablet } = useBreakpoint();
const drawerOpen = ref(false);
defineExpose({ drawerOpen });
```
In the template: add a hamburger button in `.topbar` (before `.role`) and a backdrop, and bind an `--open` class + close-on-nav:
```html
<header class="topbar">
  <button class="hamburger" aria-label="Меню" @click="drawerOpen = !drawerOpen">☰</button>
  <span class="role">{{ auth.role }}</span>
  <el-button size="small" @click="logout">Вийти</el-button>
</header>
```
Give `<aside class="sidebar" :class="{ 'sidebar--open': drawerOpen }">`, add `@click` on each nav `router-link` to set `drawerOpen = false`, and add a backdrop element after the sidebar:
```html
<div v-if="drawerOpen" class="sidebar__backdrop" @click="drawerOpen = false"></div>
```

- [ ] **Step 4: Add responsive styles** to the `<style scoped>` block:
```less
.hamburger { display: none; background: none; border: none; font-size: 22px; cursor: pointer; color: @text; margin-right: auto; }
@media (max-width: @bp-tablet) {
  .hamburger { display: block; }
  .sidebar {
    position: fixed; z-index: 1001; top: 0; left: 0; height: 100%;
    transform: translateX(-100%); transition: transform .2s ease;
  }
  .sidebar--open { transform: translateX(0); }
  .sidebar__backdrop { position: fixed; inset: 0; z-index: 1000; background: rgba(0,0,0,0.45); }
}
```
(The `.topbar` already uses `justify-content: flex-end`; `margin-right: auto` on the hamburger pushes it to the left.)

- [ ] **Step 5: Run test + full suite + build**

Run: `cd admin && npm test -- AdminLayout` → PASS. Then `npm test` (green) and `npm run build` (clean).

- [ ] **Step 6: Commit**
```bash
git add admin/src/layouts/AdminLayout.vue admin/tests/layouts/AdminLayout.test.js
git commit -m "feat(admin): off-canvas sidebar drawer + hamburger below 1024px"
```

---

## Task 3: `ResponsiveTable` component

**Files:**
- Create: `admin/src/components/ResponsiveTable.vue`
- Test: `admin/tests/components/ResponsiveTable.test.js`

**Interfaces:**
- Consumes: `useBreakpoint` (Task 1).
- Produces: `<ResponsiveTable :columns :rows :row-key :loading>` with a `#col-<slot>` scoped slot per custom column and a `#actions` scoped slot. `columns` item shape: `{ prop?: string, label: string, width?: string|number, slot?: string }`. Consumed by Tasks 4–8.

- [ ] **Step 1: Write the failing test** `admin/tests/components/ResponsiveTable.test.js`:
```js
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import ElementPlus from "element-plus";
import ResponsiveTable from "@/components/ResponsiveTable.vue";

const columns = [{ prop: "name", label: "Назва" }, { label: "Дії?", slot: "flag" }];
const rows = [{ id: 1, name: "Alpha", flag: true }];

function mountRT(mobile) {
  window.matchMedia = vi.fn(() => ({ matches: mobile, addEventListener() {}, removeEventListener() {} }));
  return mount(ResponsiveTable, {
    props: { columns, rows },
    slots: {
      "col-flag": '<template #col-flag="{ row }"><b class="flag">{{ row.flag ? "yes" : "no" }}</b></template>',
      actions: '<template #actions="{ row }"><button class="act">del {{ row.id }}</button></template>',
    },
    global: { plugins: [ElementPlus] },
  });
}

describe("ResponsiveTable", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders el-table on desktop", () => {
    const w = mountRT(false);
    expect(w.find(".el-table").exists()).toBe(true);
    expect(w.find(".rt-cards").exists()).toBe(false);
  });

  it("renders card stack with labels + slots on mobile", () => {
    const w = mountRT(true);
    expect(w.find(".rt-cards").exists()).toBe(true);
    expect(w.find(".el-table").exists()).toBe(false);
    expect(w.text()).toContain("Назва");
    expect(w.find(".flag").text()).toBe("yes");
    expect(w.find(".act").text()).toContain("del 1");
  });

  it("shows empty state on mobile with no rows", () => {
    window.matchMedia = vi.fn(() => ({ matches: true, addEventListener() {}, removeEventListener() {} }));
    const w = mount(ResponsiveTable, { props: { columns, rows: [] }, global: { plugins: [ElementPlus] } });
    expect(w.find(".rt-empty").exists()).toBe(true);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && npm test -- ResponsiveTable`
Expected: FAIL — cannot resolve component.

- [ ] **Step 3: Implement `admin/src/components/ResponsiveTable.vue`:**
```vue
<script setup>
import { useBreakpoint } from "@/composables/useBreakpoint";

defineProps({
  columns: { type: Array, required: true },
  rows: { type: Array, default: () => [] },
  rowKey: { type: String, default: "id" },
  loading: { type: Boolean, default: false },
});
const { isMobile } = useBreakpoint();
</script>

<template>
  <el-table v-if="!isMobile" :data="rows" :row-key="rowKey" v-loading="loading" style="width: 100%">
    <el-table-column
      v-for="col in columns"
      :key="col.label"
      :prop="col.prop"
      :label="col.label"
      :width="col.width"
    >
      <template v-if="col.slot" #default="{ row }">
        <slot :name="'col-' + col.slot" :row="row" />
      </template>
    </el-table-column>
    <el-table-column v-if="$slots.actions" label="Дії">
      <template #default="{ row }"><slot name="actions" :row="row" /></template>
    </el-table-column>
  </el-table>

  <div v-else class="rt-cards" v-loading="loading">
    <p v-if="!rows.length" class="rt-empty">Немає даних</p>
    <div v-for="row in rows" :key="row[rowKey]" class="rt-card">
      <div v-for="col in columns" :key="col.label" class="rt-cell">
        <span class="rt-label">{{ col.label }}</span>
        <span class="rt-value">
          <slot v-if="col.slot" :name="'col-' + col.slot" :row="row" />
          <template v-else>{{ row[col.prop] }}</template>
        </span>
      </div>
      <div v-if="$slots.actions" class="rt-actions"><slot name="actions" :row="row" /></div>
    </div>
  </div>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.rt-cards { display: flex; flex-direction: column; gap: 12px; }
.rt-empty { color: @meta-muted; text-align: center; padding: 24px 0; }
.rt-card { border: 1px solid @divider; border-radius: 10px; background: @surface; padding: 12px; }
.rt-cell { display: flex; justify-content: space-between; gap: 12px; padding: 4px 0; border-bottom: 1px solid @divider; }
.rt-cell:last-of-type { border-bottom: none; }
.rt-label { color: @meta-muted; font-size: 13px; flex: 0 0 auto; }
.rt-value { text-align: right; word-break: break-word; }
.rt-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
</style>
```

- [ ] **Step 4: Run test + build**

Run: `cd admin && npm test -- ResponsiveTable` → PASS. Then `npm run build` (clean).

- [ ] **Step 5: Commit**
```bash
git add admin/src/components/ResponsiveTable.vue admin/tests/components/ResponsiveTable.test.js
git commit -m "feat(admin): ResponsiveTable — el-table on desktop, card stack on mobile"
```

---

## Task 4: Migrate OffersListView (covers Moderation via reuse)

**Files:**
- Modify: `admin/src/views/OffersListView.vue`

**Interfaces:**
- Consumes: `ResponsiveTable` (Task 3). `ModerationQueueView` renders `<OffersListView fixed-status="pending_review"/>`, so it inherits the change — no separate task.

- [ ] **Step 1: Import and replace the table.** Add `import ResponsiveTable from "@/components/ResponsiveTable.vue";`. In `<script setup>`, define the column list (put near the top of setup):
```js
const columns = [
  { prop: "title", label: "Заголовок" },
  { prop: "provider", label: "Провайдер" },
  { label: "Тип", slot: "type" },
  { label: "Статус", slot: "status" },
  { label: "Дійсний до", slot: "validUntil" },
  { label: "Джерело", slot: "source" },
];
```
Replace the entire `<el-table>…</el-table>` block with:
```html
<ResponsiveTable :columns="columns" :rows="items" :loading="loading">
  <template #col-type="{ row }">{{ enumLabel(OFFER_TYPES, row.type) }}</template>
  <template #col-status="{ row }">
    <el-tag :type="statusTagType(row.status)">{{ enumLabel(OFFER_STATUSES, row.status) }}</el-tag>
  </template>
  <template #col-validUntil="{ row }">{{ formatDate(row.valid_until) }}</template>
  <template #col-source="{ row }">
    <el-link v-if="isHttpUrl(row.site_url)" :href="row.site_url" type="primary" target="_blank" rel="noopener noreferrer">Сайт ↗</el-link>
    <el-link v-if="isHttpUrl(row.article_url)" :href="row.article_url" type="primary" target="_blank" rel="noopener noreferrer" style="margin-left: 8px">Стаття ↗</el-link>
    <span v-if="!isHttpUrl(row.site_url) && !isHttpUrl(row.article_url)" style="color: var(--el-text-color-placeholder)">—</span>
  </template>
  <template #actions="{ row }">
    <el-button size="small" @click="edit(row.id)">Редагувати</el-button>
    <el-button v-if="row.status !== 'published'" size="small" type="success" @click="onPublish(row.id)">Опублікувати</el-button>
    <el-button v-if="row.status === 'pending_review'" size="small" type="warning" @click="onReject(row.id)">Відхилити</el-button>
    <el-button size="small" type="danger" @click="onDelete(row.id)">Видалити</el-button>
  </template>
</ResponsiveTable>
```

- [ ] **Step 2: Run the view's existing tests (desktop path) + Moderation test**

Run: `cd admin && npm test -- OffersListView ModerationQueue`
Expected: PASS (matchMedia mock → desktop → `el-table` present; behavior tests unchanged). If any test asserts raw `<el-table>` DOM that moved under ResponsiveTable, it still resolves because ResponsiveTable renders `el-table` on desktop.

- [ ] **Step 3: Build + full suite**

Run: `cd admin && npm run build` (clean) and `npm test` (green).

- [ ] **Step 4: Commit**
```bash
git add admin/src/views/OffersListView.vue
git commit -m "feat(admin): OffersListView via ResponsiveTable (covers moderation)"
```

---

## Task 5: Migrate SourcesView

**Files:**
- Modify: `admin/src/views/SourcesView.vue`

- [ ] **Step 1: Import ResponsiveTable and define columns** (read the current `<el-table>` block first — its cell slots for type/URL/active are reused verbatim inside the new slots):
```js
const columns = [
  { prop: "name", label: "Назва" },
  { label: "Тип", slot: "type" },
  { label: "URL / handle", slot: "ref" },
  { label: "Активне", slot: "active" },
];
```
Replace the `<el-table>…</el-table>` with a `<ResponsiveTable :columns="columns" :rows="items" :loading="loading">`, moving the existing `#default` cell contents into `#col-type`, `#col-ref`, `#col-active`, and the action buttons into `#actions`. Keep the exact inner markup/handlers from the current cells (`enumLabel(SOURCE_TYPES, row.type)`, the URL/handle rendering, `row.is_active ? "Так" : "Ні"`).

- [ ] **Step 2: Run tests** — `cd admin && npm test -- SourcesView` → PASS.
- [ ] **Step 3: Build + full suite** — `npm run build` clean, `npm test` green.
- [ ] **Step 4: Commit**
```bash
git add admin/src/views/SourcesView.vue
git commit -m "feat(admin): SourcesView via ResponsiveTable"
```

---

## Task 6: Migrate SuggestedSourcesView

**Files:**
- Modify: `admin/src/views/SuggestedSourcesView.vue`

- [ ] **Step 1: Import ResponsiveTable and define columns:**
```js
const columns = [
  { prop: "name", label: "Назва" },
  { label: "Тип", slot: "type" },
  { label: "URL / handle", slot: "ref" },
  { prop: "discovery_note", label: "Нотатка" },
];
```
Replace `<el-table>` with `<ResponsiveTable>`, moving the `Тип` cell (`enumLabel(SOURCE_TYPES, row.type)`) into `#col-type`, the URL/handle cell into `#col-ref`, and the action buttons into `#actions`. `name` and `discovery_note` are plain props (no slot).

- [ ] **Step 2: Run tests** — `npm test -- SuggestedSources` → PASS.
- [ ] **Step 3: Build + full suite** — clean + green.
- [ ] **Step 4: Commit**
```bash
git add admin/src/views/SuggestedSourcesView.vue
git commit -m "feat(admin): SuggestedSourcesView via ResponsiveTable"
```

---

## Task 7: Migrate CategoriesView (two tab tables)

**Files:**
- Modify: `admin/src/views/CategoriesView.vue`

- [ ] **Step 1: Import ResponsiveTable and define a shared column list** (both tabs — "Для кого" and "Тематика" — have identical columns):
```js
const columns = [
  { prop: "name", label: "Назва" },
  { prop: "slug", label: "Slug" },
];
```
Replace **both** `<el-table>` blocks (inside the two `<el-tab-pane>`s) with:
```html
<ResponsiveTable :columns="columns" :rows="dictionaries.targetCategories">
  <template #actions="{ row }"><!-- existing target-category action buttons --></template>
</ResponsiveTable>
```
and the analogous one bound to `dictionaries.offerCategories`. Move each tab's existing action buttons into its `#actions` slot verbatim.

- [ ] **Step 2: Run tests** — `npm test -- CategoriesView` → PASS.
- [ ] **Step 3: Build + full suite** — clean + green.
- [ ] **Step 4: Commit**
```bash
git add admin/src/views/CategoriesView.vue
git commit -m "feat(admin): CategoriesView tables via ResponsiveTable"
```

---

## Task 8: Migrate AdminUsersView

**Files:**
- Modify: `admin/src/views/AdminUsersView.vue`

- [ ] **Step 1: Import ResponsiveTable and define columns:**
```js
const columns = [
  { prop: "email", label: "Email" },
  { label: "Роль", slot: "role" },
  { label: "Створено", slot: "created" },
];
```
Replace `<el-table>` with `<ResponsiveTable :columns="columns" :rows="items" :loading="loading">`, moving `enumLabel(ADMIN_ROLES, row.role)` into `#col-role`, `formatDate(row.created_at)` into `#col-created`, and the action button(s) into `#actions`.

- [ ] **Step 2: Run tests** — `npm test -- AdminUsersView` → PASS (existing test drives `create`/`onDelete` via `wrapper.vm`, unaffected).
- [ ] **Step 3: Build + full suite** — clean + green.
- [ ] **Step 4: Commit**
```bash
git add admin/src/views/AdminUsersView.vue
git commit -m "feat(admin): AdminUsersView via ResponsiveTable"
```

---

## Task 9: Admin forms & toolbars on mobile

**Files:**
- Modify: `admin/src/components/OfferForm.vue`
- Modify: `admin/src/components/DataTableToolbar.vue`

**Interfaces:**
- Consumes: `useBreakpoint` (Task 1) for `OfferForm` label position.

- [ ] **Step 1: OfferForm — top labels + full-width controls on mobile.** In `OfferForm.vue` `<script setup>` add `import { useBreakpoint } from "@/composables/useBreakpoint"; const { isMobile } = useBreakpoint();` and bind the root `<el-form>` `:label-position="isMobile ? 'top' : 'right'"`. In its `<style scoped lang="less">` add:
```less
@import "@/styles/variables.less";
@media (max-width: @bp-mobile) {
  :deep(.el-select), :deep(.el-input), :deep(.el-input-number) { width: 100%; }
  .el-form-item { margin-bottom: 14px; }
}
```

- [ ] **Step 2: DataTableToolbar — wrap/stack on mobile.** In `DataTableToolbar.vue` `<style scoped lang="less">` ensure the toolbar row wraps and controls go full-width on mobile:
```less
@import "@/styles/variables.less";
@media (max-width: @bp-mobile) {
  .toolbar { flex-wrap: wrap; }
  .toolbar :deep(.el-select), .toolbar :deep(.el-input) { width: 100% !important; }
}
```
(Read the component first to match its actual root class name; replace `.toolbar` with the real one.)

- [ ] **Step 3: Build + full suite** — `cd admin && npm run build` clean, `npm test` green.
- [ ] **Step 4: Manual check** — `npm run dev`, in-app browser at 375px: open the offer form (fields stacked, full width) and a list view toolbar (filters wrap).
- [ ] **Step 5: Commit**
```bash
git add admin/src/components/OfferForm.vue admin/src/components/DataTableToolbar.vue
git commit -m "feat(admin): mobile form (top labels, full-width) + toolbar wrap"
```

---

## Task 10: Public — real header links + mobile header

**Files:**
- Modify: `public/src/components/SiteHeader.vue`
- Test: `public/tests/components/SiteHeader.test.js` (create)

**Interfaces:**
- Public routes are `offers`, `offer`, `not-found` only. There is no "Про нас" page — make "Оффери" a real link and drop the dead "Про нас" label (do not invent an about page).

- [ ] **Step 1: Write the failing test** `public/tests/components/SiteHeader.test.js`:
```js
import { describe, it, expect } from "vitest";
import { mount, RouterLinkStub } from "@vue/test-utils";
import SiteHeader from "@/components/SiteHeader.vue";

describe("SiteHeader", () => {
  it("links Оффери to the offers route", () => {
    const w = mount(SiteHeader, { global: { stubs: { RouterLink: RouterLinkStub } } });
    const links = w.findAllComponents(RouterLinkStub);
    const offers = links.find((l) => l.props("to")?.name === "offers");
    expect(offers).toBeTruthy();
    expect(w.text()).not.toContain("Про нас");
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd public && npm test -- SiteHeader`
Expected: FAIL — nav is static text; no offers router-link, "Про нас" present.

- [ ] **Step 3: Update `SiteHeader.vue` template** — replace the static `<nav>` with a real link (keeping the brand link as-is):
```html
<nav class="nav">
  <router-link :to="{ name: 'offers' }" class="nav__link">Оффери</router-link>
</nav>
```
Update `.nav` styles so the link inherits the muted uppercase treatment and has a ≥44px tap target; ensure `.site-header__inner` wraps gracefully on narrow widths:
```less
.site-header__inner { flex-wrap: wrap; gap: 8px 16px; }
.nav__link { color: @nav-muted; text-decoration: none; display: inline-flex; align-items: center; min-height: 44px; }
.nav__link:hover { color: @text; }
```

- [ ] **Step 4: Run test + build**

Run: `cd public && npm test -- SiteHeader` → PASS. Then `npm test` (60 green) and `npm run build` (clean).

- [ ] **Step 5: Commit**
```bash
git add public/src/components/SiteHeader.vue public/tests/components/SiteHeader.test.js
git commit -m "feat(public): real header nav link + mobile-friendly header"
```

---

## Task 11: Public — responsive audit fixes

**Files (modify as the audit requires):**
- `public/src/views/OffersView.vue`, `public/src/components/OfferGrid.vue`, `public/src/components/OfferCard.vue`, `public/src/views/OfferDetailView.vue`, `public/src/components/Pagination.vue`, and `public/src/styles/*` as needed.

- [ ] **Step 1: Audit at three widths.** `cd public && npm run dev`; in-app browser at 375 / 768 / 1280. On each screen (list, detail) confirm: single-column grid on phone, no horizontal page scroll, images `max-width:100%` with sane aspect, tap targets ≥44px, pagination wraps, `OffersView` head (h1 + Фільтри) stacks cleanly. Note each concrete defect.

- [ ] **Step 2: Fix each noted defect** with minimal scoped CSS in the owning component, using `@bp-mobile`/`@bp-tablet`. Typical fixes (apply only those the audit actually surfaces):
  - `OfferGrid`: `grid-template-columns: 1fr` at `≤@bp-mobile`.
  - `OfferCard`: `img { max-width: 100%; height: auto; }`; ensure the card link tap area is ≥44px tall.
  - `OfferDetailView`: stack image + meta to one column at `≤@bp-mobile`; `img { max-width: 100%; }`.
  - `Pagination`: `flex-wrap: wrap; justify-content: center;`.
  - Global: verify `.container` side padding on phone; add `overflow-x: hidden` on the page wrapper only if a real overflow source can't be removed at source.

- [ ] **Step 3: Build + full suite** — `cd public && npm run build` clean, `npm test` (60 green).
- [ ] **Step 4: Re-check** the same three widths in-browser; confirm each noted defect is gone.
- [ ] **Step 5: Commit**
```bash
git add public/src
git commit -m "fix(public): responsive audit — grid, cards, detail, pagination, tap targets"
```

---

## Task 12: Final verification (both apps)

**Files:** none (verification only).

- [ ] **Step 1: Admin** — `cd admin && npm run build` (clean) && `npm test` (all green, incl. new `useBreakpoint`, `ResponsiveTable`, `AdminLayout` drawer). Then `npm run dev` + in-app browser at 375: drawer opens/closes and navigates; every list view (Offers, Moderation, Sources, Suggested, Categories, Users) renders as readable cards; offer form is fillable.
- [ ] **Step 2: Public** — `cd public && npm run build` (clean) && `npm test` (all green). In-app browser at 375 / 768 / 1280: header link works, no horizontal scroll, list + detail read cleanly.
- [ ] **Step 3:** If all green, the branch is ready for review + merge (handled outside this plan via `superpowers:requesting-code-review` then `superpowers:finishing-a-development-branch`).

---

## Notes for the implementer

- Element Plus cell slots use `#default="{ row }"`; ResponsiveTable re-exposes them as `#col-<slot>="{ row }"` and `#actions="{ row }"`. When migrating a view, move the **exact** inner markup and handlers from each `<el-table-column>`'s `#default` into the matching `#col-*` slot — no logic changes.
- The desktop path is what existing view tests exercise (matchMedia mock → `matches:false`). Keep those green; they are the regression guard for the migrations. The mobile card path is covered once, centrally, by the `ResponsiveTable` unit test — do not re-test it per view.
- Read each view's current `<el-table>` block before editing; the column configs above are exact, but the cell/action inner markup must be copied from the live file.
