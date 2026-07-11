# UBD Public Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Vue 3 public SPA that shows published UBD offers (discounts/events) with a filter panel, pagination, and a detail view, reading the backend's open API.

**Architecture:** Vite-built Vue 3 SPA (Composition API, plain JavaScript) in `public/`, styled entirely with hand-rolled Less (no UI library, no Pinia). Vue Router (history mode) drives a list route and a detail route; filters + pagination live in the URL query (single source of truth) and a `useOffers` composable reloads whenever the query changes. A thin axios client hits only the open endpoints.

**Tech Stack:** Vue 3, Vite, Vue Router, axios, Less, Vitest + @vue/test-utils (jsdom).

## Global Constraints

- **Language:** plain JavaScript, no TypeScript.
- **UI copy:** Ukrainian.
- **Styling:** Less only, no UI component library; mobile-first responsive.
- **No Pinia:** filters live in the URL; category dictionaries cached in a composable.
- **API base:** all requests go through the shared axios client with `baseURL = import.meta.env.VITE_API_BASE || "/api"`. Never hardcode `http://localhost:8000` in app code — the Vite proxy handles it.
- **Open endpoints only:** `GET /api/offers`, `GET /api/offers/{id}`, `GET /api/target-categories`, `GET /api/offer-categories`. No auth anywhere. Never call `/api/admin/*` or `/api/internal/*`.
- **Page size:** fixed `size = 12` (not in the URL).
- **`source_id` is internal** — never displayed.
- **Tests:** Vitest + @vue/test-utils on jsdom; the API is always mocked; output must be pristine.
- **TDD:** write the failing test first, watch it fail, implement minimally, watch it pass, commit.
- **Toolchain:** Node ≥ 20, npm. All commands run from `public/`.

---

## File Structure

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
    api/client.js
    api/offers.js
    api/categories.js
    composables/useDictionaries.js
    composables/useOffers.js
    utils/placeholder.js   # copied from admin
    utils/format.js        # copied from admin + offerBadge()
    utils/errors.js
    constants/enums.js     # OFFER_TYPES, DISCOUNT_TYPES (Ukrainian labels)
    components/SiteHeader.vue
    components/SiteFooter.vue
    components/OfferBadge.vue
    components/OfferCard.vue
    components/OfferFilters.vue
    components/OfferGrid.vue
    components/Pagination.vue
    views/OffersView.vue
    views/OfferDetailView.vue
    views/NotFoundView.vue
    styles/variables.less
    styles/base.less
  tests/                  # mirrors src
```

---

### Task 1: Scaffold Vite project, base styles, test harness

**Files:**
- Create: `public/package.json`, `public/index.html`, `public/vite.config.js`, `public/vitest.config.js`, `public/vitest.setup.js`, `public/.env.development`, `public/.gitignore`
- Create: `public/src/main.js`, `public/src/App.vue`, `public/src/styles/variables.less`, `public/src/styles/base.less`
- Test: `public/tests/smoke.test.js`

**Interfaces:**
- Produces: a runnable Vite app and a green Vitest harness. `App.vue` renders a static shell (router added in Task 5; a `$route` fallback lets the smoke test mount without a router).

- [ ] **Step 1: Create `public/package.json`**

```json
{
  "name": "ubd-public",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "axios": "^1.7.0",
    "vue": "^3.4.0",
    "vue-router": "^4.3.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.0.0",
    "@vue/test-utils": "^2.4.0",
    "jsdom": "^24.0.0",
    "less": "^4.2.0",
    "vite": "^5.2.0",
    "vitest": "^1.6.0"
  }
}
```

- [ ] **Step 2: Create `public/index.html`**

```html
<!doctype html>
<html lang="uk">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Знижки та події для УБД</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.js"></script>
  </body>
</html>
```

- [ ] **Step 3: Create `public/vite.config.js`**

```js
import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    port: 5174,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
```

- [ ] **Step 4: Create `public/vitest.config.js`**

```js
import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.js"],
  },
});
```

- [ ] **Step 5: Create `public/vitest.setup.js`** (matchMedia stub for any responsive checks in jsdom)

```js
if (!window.matchMedia) {
  window.matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
  });
}
```

- [ ] **Step 6: Create `public/.env.development`**

```
VITE_API_BASE=/api
```

- [ ] **Step 7: Create `public/.gitignore`**

```
node_modules/
dist/
*.local
```

- [ ] **Step 8: Create `public/src/styles/variables.less` and `public/src/styles/base.less`**

`variables.less`:
```less
@brand: #1f6feb;
@text: #1a1a1a;
@muted: #666;
@bg: #ffffff;
@card-bg: #f7f9fc;
@border: #e3e8ef;
@radius: 10px;
@bp-mobile: 640px;
@maxw: 1100px;
```

`base.less`:
```less
@import "./variables.less";

* { box-sizing: border-box; }
html, body, #app { margin: 0; min-height: 100%; }
body { font-family: system-ui, -apple-system, sans-serif; color: @text; background: @bg; }
a { color: @brand; text-decoration: none; }
a:hover { text-decoration: underline; }
.container { max-width: @maxw; margin: 0 auto; padding: 16px; }
```

- [ ] **Step 9: Create `public/src/App.vue`**

```vue
<script setup></script>

<template>
  <router-view v-if="$route" />
  <div v-else class="container">UBD Public</div>
</template>
```

Note: the `v-if="$route"` fallback lets Task 1's smoke test mount `App` before the router exists; Task 5 removes it.

- [ ] **Step 10: Create `public/src/main.js`**

```js
import { createApp } from "vue";
import App from "./App.vue";
import "./styles/base.less";

createApp(App).mount("#app");
```

Note: Task 5 adds `app.use(router)`.

- [ ] **Step 11: Write the smoke test — `public/tests/smoke.test.js`**

```js
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import App from "@/App.vue";

describe("App", () => {
  it("mounts and shows the shell fallback", () => {
    const wrapper = mount(App, { global: { config: { globalProperties: { $route: null } } } });
    expect(wrapper.text()).toContain("UBD Public");
  });
});
```

- [ ] **Step 12: Install and run**

Run: `cd public && npm install && npm run test`
Expected: install succeeds; smoke test PASSES (1 passed). Output pristine.

- [ ] **Step 13: Commit**

```bash
git add public/
git commit -m "chore(public): scaffold Vue 3 + Vite + Vitest, base Less styles"
```

---

### Task 2: Copied utils, enums, and offerBadge

**Files:**
- Create: `public/src/constants/enums.js`, `public/src/utils/placeholder.js`, `public/src/utils/format.js`
- Test: `public/tests/utils/format.test.js`, `public/tests/utils/placeholder.test.js`

**Interfaces:**
- Produces:
  - `constants/enums.js`: `OFFER_TYPES` and `DISCOUNT_TYPES` — arrays of `{ value, label }` (Ukrainian labels).
  - `utils/placeholder.js`: `placeholderText({type,discount_type})`, `placeholderDataUri({type,discount_type})` (same behavior as admin).
  - `utils/format.js`: `enumLabel(list, value)`, `formatDate(iso) -> "dd.mm.yyyy" | ""`, and `offerBadge(offer) -> { text, kind }` where `kind ∈ {"event","free","discount"}`.

- [ ] **Step 1: Create `public/src/constants/enums.js`**

```js
export const OFFER_TYPES = [
  { value: "discount", label: "Знижка" },
  { value: "event", label: "Подія" },
];

export const DISCOUNT_TYPES = [
  { value: "percent", label: "Відсоток" },
  { value: "fixed", label: "Фіксована" },
  { value: "free", label: "Безкоштовно" },
];
```

- [ ] **Step 2: Create `public/src/utils/placeholder.js`**

```js
export function placeholderText({ type, discount_type }) {
  if (type === "event" || discount_type === "free") return "безкоштовно для УБД";
  return "знижка для УБД";
}

export function placeholderDataUri(offer) {
  const text = placeholderText(offer);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="225">` +
    `<rect width="100%" height="100%" fill="#1f6feb"/>` +
    `<text x="50%" y="50%" fill="#ffffff" font-family="sans-serif" font-size="24" ` +
    `text-anchor="middle" dominant-baseline="middle">${text}</text>` +
    `</svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}
```

- [ ] **Step 3: Write the failing test — `public/tests/utils/placeholder.test.js`**

```js
import { describe, it, expect } from "vitest";
import { placeholderText, placeholderDataUri } from "@/utils/placeholder";

describe("placeholderText", () => {
  it("says 'безкоштовно' for events and free", () => {
    expect(placeholderText({ type: "event", discount_type: null })).toBe("безкоштовно для УБД");
    expect(placeholderText({ type: "discount", discount_type: "free" })).toBe("безкоштовно для УБД");
  });
  it("says 'знижка' otherwise", () => {
    expect(placeholderText({ type: "discount", discount_type: "percent" })).toBe("знижка для УБД");
  });
});

describe("placeholderDataUri", () => {
  it("returns an svg data uri containing the text", () => {
    const uri = placeholderDataUri({ type: "event", discount_type: null });
    expect(uri.startsWith("data:image/svg+xml,")).toBe(true);
    expect(decodeURIComponent(uri)).toContain("безкоштовно для УБД");
  });
});
```

- [ ] **Step 4: Write the failing test — `public/tests/utils/format.test.js`**

```js
import { describe, it, expect } from "vitest";
import { enumLabel, formatDate, offerBadge } from "@/utils/format";
import { OFFER_TYPES } from "@/constants/enums";

describe("enumLabel", () => {
  it("maps value to label, falls back to raw", () => {
    expect(enumLabel(OFFER_TYPES, "event")).toBe("Подія");
    expect(enumLabel(OFFER_TYPES, "???")).toBe("???");
  });
});

describe("formatDate", () => {
  it("formats ISO date as dd.mm.yyyy, empty for null", () => {
    expect(formatDate("2026-07-01")).toBe("01.07.2026");
    expect(formatDate(null)).toBe("");
  });
});

describe("offerBadge", () => {
  it("event → Подія", () => {
    expect(offerBadge({ type: "event" })).toEqual({ text: "Подія", kind: "event" });
  });
  it("free → Безкоштовно", () => {
    expect(offerBadge({ type: "discount", discount_type: "free" })).toEqual({ text: "Безкоштовно", kind: "free" });
  });
  it("percent → −N%", () => {
    expect(offerBadge({ type: "discount", discount_type: "percent", discount_value: "50.00" })).toEqual({ text: "−50%", kind: "discount" });
  });
  it("fixed → −N ₴", () => {
    expect(offerBadge({ type: "discount", discount_type: "fixed", discount_value: 200 })).toEqual({ text: "−200 ₴", kind: "discount" });
  });
  it("discount with no type → Знижка", () => {
    expect(offerBadge({ type: "discount", discount_type: null })).toEqual({ text: "Знижка", kind: "discount" });
  });
});
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `cd public && npx vitest run tests/utils/placeholder.test.js tests/utils/format.test.js`
Expected: FAIL — modules/functions undefined.

- [ ] **Step 6: Create `public/src/utils/format.js`**

```js
export function enumLabel(list, value) {
  const found = list.find((item) => item.value === value);
  return found ? found.label : value;
}

export function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const dd = String(d.getUTCDate()).padStart(2, "0");
  const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
  return `${dd}.${mm}.${d.getUTCFullYear()}`;
}

export function offerBadge(offer) {
  if (offer.type === "event") return { text: "Подія", kind: "event" };
  if (offer.discount_type === "free") return { text: "Безкоштовно", kind: "free" };
  if (offer.discount_type === "percent" && offer.discount_value != null) {
    return { text: `−${Number(offer.discount_value)}%`, kind: "discount" };
  }
  if (offer.discount_type === "fixed" && offer.discount_value != null) {
    return { text: `−${Number(offer.discount_value)} ₴`, kind: "discount" };
  }
  return { text: "Знижка", kind: "discount" };
}
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd public && npx vitest run tests/utils/placeholder.test.js tests/utils/format.test.js`
Expected: PASS (all).

- [ ] **Step 8: Commit**

```bash
git add public/src/constants public/src/utils/placeholder.js public/src/utils/format.js public/tests/utils
git commit -m "feat(public): enums, placeholder, and format utils (with offerBadge)"
```

---

### Task 3: API layer (client, offers, categories, errors)

**Files:**
- Create: `public/src/api/client.js`, `public/src/api/offers.js`, `public/src/api/categories.js`, `public/src/utils/errors.js`
- Test: `public/tests/api/api.test.js`

**Interfaces:**
- Produces:
  - `api/client.js` default export `client` (axios instance, `baseURL = import.meta.env.VITE_API_BASE || "/api"`). No interceptors (public API).
  - `api/offers.js`: `list(params) -> Promise<{items,total,page,size}>` GET `/offers`; `get(id) -> Promise<offer>` GET `/offers/{id}`.
  - `api/categories.js`: `listTarget()` GET `/target-categories`; `listOffer()` GET `/offer-categories`.
  - `utils/errors.js`: `extractError(err) -> string`.

- [ ] **Step 1: Write the failing test — `public/tests/api/api.test.js`**

```js
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/api/client", () => {
  const client = { get: vi.fn(() => Promise.resolve({ data: "OK" })) };
  return { default: client };
});

import client from "@/api/client";
import * as offers from "@/api/offers";
import * as categories from "@/api/categories";
import { extractError } from "@/utils/errors";

beforeEach(() => vi.clearAllMocks());

describe("offers api", () => {
  it("list passes params", async () => {
    await offers.list({ type: "discount", page: 2, size: 12 });
    expect(client.get).toHaveBeenCalledWith("/offers", { params: { type: "discount", page: 2, size: 12 } });
  });
  it("get fetches by id", async () => {
    await offers.get(7);
    expect(client.get).toHaveBeenCalledWith("/offers/7");
  });
});

describe("categories api", () => {
  it("hits the open dictionary endpoints", async () => {
    await categories.listTarget();
    await categories.listOffer();
    expect(client.get).toHaveBeenCalledWith("/target-categories");
    expect(client.get).toHaveBeenCalledWith("/offer-categories");
  });
});

describe("extractError", () => {
  it("prefers detail, then message, then fallback", () => {
    expect(extractError({ response: { data: { detail: "Ой" } } })).toBe("Ой");
    expect(extractError({ message: "Network Error" })).toBe("Network Error");
    expect(extractError({})).toBe("Не вдалося завантажити. Спробуйте пізніше");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd public && npx vitest run tests/api/api.test.js`
Expected: FAIL — modules undefined.

- [ ] **Step 3: Create `public/src/api/client.js`**

```js
import axios from "axios";

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || "/api",
});

export default client;
```

- [ ] **Step 4: Create `public/src/api/offers.js`**

```js
import client from "./client";

export const list = (params) => client.get("/offers", { params }).then((r) => r.data);
export const get = (id) => client.get(`/offers/${id}`).then((r) => r.data);
```

- [ ] **Step 5: Create `public/src/api/categories.js`**

```js
import client from "./client";

export const listTarget = () => client.get("/target-categories").then((r) => r.data);
export const listOffer = () => client.get("/offer-categories").then((r) => r.data);
```

- [ ] **Step 6: Create `public/src/utils/errors.js`**

```js
export function extractError(err) {
  const detail = err?.response?.data?.detail;
  if (detail) return detail;
  if (err?.message) return err.message;
  return "Не вдалося завантажити. Спробуйте пізніше";
}
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd public && npx vitest run tests/api/api.test.js`
Expected: PASS (5 tests).

- [ ] **Step 8: Commit**

```bash
git add public/src/api public/src/utils/errors.js public/tests/api
git commit -m "feat(public): axios client and offers/categories API wrappers"
```

---

### Task 4: Composables — useDictionaries and useOffers

**Files:**
- Create: `public/src/composables/useDictionaries.js`, `public/src/composables/useOffers.js`
- Test: `public/tests/composables/useDictionaries.test.js`, `public/tests/composables/useOffers.test.js`

**Interfaces:**
- Consumes: `api/categories.js` (`listTarget`, `listOffer`); `api/offers.js` (`list`); `utils/errors.js` (`extractError`); `vue-router` `useRoute`.
- Produces:
  - `useDictionaries()` → `{ targetCategories, offerCategories, load }` (module-level cache; `load()` fetches both once; concurrent calls share the in-flight promise).
  - `useOffers()` → `{ items, total, loading, error, size, page, load }`. `size` is the constant `12`. `page` is a computed reading `route.query.page` (default 1). `load()` reads `route.query`, builds params (`page`, `size`, plus non-empty `type/target_category/offer_category/location/q`), calls `offers.list`, sets `items`/`total`; on error sets `error` (via `extractError`) and clears items. A `watch(() => route.query, load, { immediate: true })` reloads on any query change.

- [ ] **Step 1: Write the failing test — `public/tests/composables/useDictionaries.test.js`**

```js
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/api/categories", () => ({
  listTarget: vi.fn(() => Promise.resolve([{ id: 1, name: "УБД", slug: "ubd" }])),
  listOffer: vi.fn(() => Promise.resolve([{ id: 2, name: "Розваги", slug: "rozvahy" }])),
}));

import { useDictionaries } from "@/composables/useDictionaries";
import { listTarget, listOffer } from "@/api/categories";

describe("useDictionaries", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads both lists once and caches", async () => {
    const d = useDictionaries();
    await d.load();
    await d.load();
    expect(listTarget).toHaveBeenCalledTimes(1);
    expect(listOffer).toHaveBeenCalledTimes(1);
    expect(d.targetCategories.value[0].slug).toBe("ubd");
    expect(d.offerCategories.value[0].slug).toBe("rozvahy");
  });
});
```

Note: the cache is module-level, so this test file gets a fresh module (Vitest isolates modules per file). Within the file the two `load()` calls share the cache — that is exactly what we assert.

- [ ] **Step 2: Write the failing test — `public/tests/composables/useOffers.test.js`**

```js
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import { h } from "vue";
import { useOffers } from "@/composables/useOffers";

vi.mock("@/api/offers", () => ({
  list: vi.fn(() => Promise.resolve({ items: [{ id: 1 }], total: 1, page: 1, size: 12 })),
}));
import * as offers from "@/api/offers";

// Host component that exercises the composable and exposes its state.
const Host = {
  setup() {
    const s = useOffers();
    return s;
  },
  render() {
    return h("div");
  },
};

async function mountAt(query) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/", component: Host }],
  });
  router.push({ path: "/", query });
  await router.isReady();
  const wrapper = mount(Host, { global: { plugins: [router] } });
  await flushPromises();
  return { wrapper, router };
}

describe("useOffers", () => {
  beforeEach(() => vi.clearAllMocks());

  it("builds params from query, dropping empties", async () => {
    await mountAt({ type: "discount", q: "кава" });
    expect(offers.list).toHaveBeenCalledWith({ page: 1, size: 12, type: "discount", q: "кава" });
  });

  it("reads page from query", async () => {
    await mountAt({ page: "3" });
    expect(offers.list).toHaveBeenCalledWith({ page: 3, size: 12 });
  });

  it("reloads when the query changes", async () => {
    const { router } = await mountAt({});
    expect(offers.list).toHaveBeenCalledTimes(1);
    await router.push({ path: "/", query: { location: "Київ" } });
    await flushPromises();
    expect(offers.list).toHaveBeenCalledTimes(2);
    expect(offers.list).toHaveBeenLastCalledWith({ page: 1, size: 12, location: "Київ" });
  });

  it("sets error on failure", async () => {
    offers.list.mockRejectedValueOnce({ message: "boom" });
    const { wrapper } = await mountAt({});
    expect(wrapper.vm.error).toBe("boom");
    expect(wrapper.vm.items).toEqual([]);
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd public && npx vitest run tests/composables`
Expected: FAIL — composables undefined.

- [ ] **Step 4: Create `public/src/composables/useDictionaries.js`**

```js
import { ref } from "vue";
import { listTarget, listOffer } from "@/api/categories";

const targetCategories = ref([]);
const offerCategories = ref([]);
let loaded = false;
let inflight = null;

export function useDictionaries() {
  async function load() {
    if (loaded) return;
    if (inflight) return inflight;
    inflight = Promise.all([listTarget(), listOffer()])
      .then(([t, o]) => {
        targetCategories.value = t;
        offerCategories.value = o;
        loaded = true;
      })
      .catch(() => {
        // dictionaries are non-critical (filter options only) — leave lists empty, allow retry
      })
      .finally(() => {
        inflight = null;
      });
    return inflight;
  }
  return { targetCategories, offerCategories, load };
}
```

- [ ] **Step 5: Create `public/src/composables/useOffers.js`**

```js
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
  const loading = ref(false);
  const error = ref(null);
  const page = computed(() => Number(route.query.page) || 1);

  function paramsFromQuery(query) {
    const params = { page: Number(query.page) || 1, size: SIZE };
    for (const key of FILTER_KEYS) {
      if (query[key]) params[key] = query[key];
    }
    return params;
  }

  async function load() {
    loading.value = true;
    error.value = null;
    try {
      const data = await offersApi.list(paramsFromQuery(route.query));
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

  watch(() => route.query, load, { immediate: true });

  return { items, total, loading, error, size: SIZE, page, load };
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd public && npx vitest run tests/composables`
Expected: PASS (5 tests).

- [ ] **Step 7: Commit**

```bash
git add public/src/composables public/tests/composables
git commit -m "feat(public): useDictionaries and useOffers composables"
```

---

### Task 5: Router, app shell (header/footer), main wiring

**Files:**
- Create: `public/src/router/index.js`, `public/src/components/SiteHeader.vue`, `public/src/components/SiteFooter.vue`
- Create (stubs, filled later): `public/src/views/OffersView.vue`, `public/src/views/OfferDetailView.vue`, `public/src/views/NotFoundView.vue`
- Modify: `public/src/App.vue`, `public/src/main.js`, `public/tests/smoke.test.js`
- Test: `public/tests/router/router.test.js`

**Interfaces:**
- Consumes: the three view components.
- Produces: `router/index.js` default export `router` with routes `offers` (`/`), `offer` (`/offers/:id`), `not-found` (`/:catchAll(.*)`). `App.vue` renders `SiteHeader`, `<router-view>`, `SiteFooter`. View files exist as minimal stubs (single labelled div); Tasks 9–10 fill them.

- [ ] **Step 1: Create the three view stubs**

`public/src/views/OffersView.vue`:
```vue
<script setup></script>
<template>
  <div class="container">Оффери</div>
</template>
```
`public/src/views/OfferDetailView.vue`:
```vue
<script setup></script>
<template>
  <div class="container">Деталі оффера</div>
</template>
```
`public/src/views/NotFoundView.vue`:
```vue
<script setup></script>
<template>
  <div class="container">
    <h1>Сторінку не знайдено</h1>
    <router-link :to="{ name: 'offers' }">← на головну</router-link>
  </div>
</template>
```

- [ ] **Step 2: Create `public/src/components/SiteHeader.vue`**

```vue
<script setup></script>

<template>
  <header class="site-header">
    <div class="container">
      <router-link :to="{ name: 'offers' }" class="logo">Знижки для УБД</router-link>
    </div>
  </header>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.site-header { border-bottom: 1px solid @border; background: @bg; }
.logo { font-weight: 700; font-size: 20px; color: @brand; }
</style>
```

- [ ] **Step 3: Create `public/src/components/SiteFooter.vue`**

```vue
<script setup></script>

<template>
  <footer class="site-footer">
    <div class="container">
      Агрегатор знижок і безкоштовних подій для учасників бойових дій України.
    </div>
  </footer>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.site-footer { border-top: 1px solid @border; color: @muted; margin-top: 32px; font-size: 14px; }
</style>
```

- [ ] **Step 4: Create `public/src/router/index.js`**

```js
import { createRouter, createWebHistory } from "vue-router";
import OffersView from "@/views/OffersView.vue";
import OfferDetailView from "@/views/OfferDetailView.vue";
import NotFoundView from "@/views/NotFoundView.vue";

const routes = [
  { path: "/", name: "offers", component: OffersView },
  { path: "/offers/:id", name: "offer", component: OfferDetailView },
  { path: "/:catchAll(.*)", name: "not-found", component: NotFoundView },
];

const router = createRouter({ history: createWebHistory(), routes });

export default router;
```

- [ ] **Step 5: Update `public/src/App.vue`**

```vue
<script setup>
import SiteHeader from "@/components/SiteHeader.vue";
import SiteFooter from "@/components/SiteFooter.vue";
</script>

<template>
  <SiteHeader />
  <main><router-view /></main>
  <SiteFooter />
</template>
```

- [ ] **Step 6: Update `public/src/main.js`**

```js
import { createApp } from "vue";
import App from "./App.vue";
import router from "./router";
import "./styles/base.less";

createApp(App).use(router).mount("#app");
```

- [ ] **Step 7: Rewrite `public/tests/smoke.test.js`** to mount with the router

```js
import { describe, it, expect, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import App from "@/App.vue";
import router from "@/router";

describe("App", () => {
  beforeEach(() => router.push("/"));

  it("renders header and footer around the router view", async () => {
    await router.isReady();
    const wrapper = mount(App, { global: { plugins: [router] } });
    await flushPromises();
    expect(wrapper.text()).toContain("Знижки для УБД");
    expect(wrapper.text()).toContain("учасників бойових дій");
  });
});
```

- [ ] **Step 8: Write the failing test — `public/tests/router/router.test.js`**

```js
import { describe, it, expect } from "vitest";
import router from "@/router";

describe("router", () => {
  it("resolves / to the offers route", () => {
    expect(router.resolve("/").name).toBe("offers");
  });
  it("resolves an offer detail path", () => {
    const r = router.resolve("/offers/5");
    expect(r.name).toBe("offer");
    expect(r.params.id).toBe("5");
  });
  it("resolves unknown paths to not-found", () => {
    expect(router.resolve("/nope/here").name).toBe("not-found");
  });
});
```

- [ ] **Step 9: Run the full suite**

Run: `cd public && npm run test`
Expected: all tests PASS (Tasks 1–5), output pristine.

- [ ] **Step 10: Commit**

```bash
git add public/src/router public/src/components/SiteHeader.vue public/src/components/SiteFooter.vue public/src/views public/src/App.vue public/src/main.js public/tests/smoke.test.js public/tests/router
git commit -m "feat(public): router, app shell (header/footer), view stubs"
```

---

### Task 6: OfferBadge and OfferCard

**Files:**
- Create: `public/src/components/OfferBadge.vue`, `public/src/components/OfferCard.vue`
- Test: `public/tests/components/OfferBadge.test.js`, `public/tests/components/OfferCard.test.js`

**Interfaces:**
- Consumes: `utils/format.js` `offerBadge`; `utils/placeholder.js` `placeholderDataUri`; `vue-router` (`router-link`).
- Produces:
  - `OfferBadge` — prop `offer`; renders a `<span class="badge badge--{kind}">{text}</span>` from `offerBadge(offer)`.
  - `OfferCard` — prop `offer`; a `router-link` to `{ name: "offer", params: { id: offer.id } }` wrapping: an `<img>` (`offer.image_url || placeholderDataUri(offer)`), `OfferBadge`, title, provider, location, and "для кого" tags (`offer.target_categories` names).

- [ ] **Step 1: Write the failing test — `public/tests/components/OfferBadge.test.js`**

```js
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import OfferBadge from "@/components/OfferBadge.vue";

describe("OfferBadge", () => {
  it("renders event badge", () => {
    const w = mount(OfferBadge, { props: { offer: { type: "event" } } });
    expect(w.text()).toBe("Подія");
    expect(w.get("span").classes()).toContain("badge--event");
  });
  it("renders percent discount", () => {
    const w = mount(OfferBadge, { props: { offer: { type: "discount", discount_type: "percent", discount_value: 50 } } });
    expect(w.text()).toBe("−50%");
    expect(w.get("span").classes()).toContain("badge--discount");
  });
});
```

- [ ] **Step 2: Write the failing test — `public/tests/components/OfferCard.test.js`**

```js
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import OfferCard from "@/components/OfferCard.vue";

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: "/", name: "offers", component: { template: "<div/>" } },
    { path: "/offers/:id", name: "offer", component: { template: "<div/>" } },
  ],
});

function mountCard(offer) {
  return mount(OfferCard, { props: { offer }, global: { plugins: [router] } });
}

describe("OfferCard", () => {
  it("uses the placeholder when image_url is empty and shows fields", () => {
    const w = mountCard({
      id: 3, type: "discount", discount_type: "free", title: "Безкоштовний вхід",
      provider: "Музей", location: "Львів", image_url: null,
      target_categories: [{ id: 1, name: "УБД" }], offer_categories: [],
    });
    const src = w.get("img").attributes("src");
    expect(src.startsWith("data:image/svg+xml,")).toBe(true);
    expect(w.text()).toContain("Безкоштовний вхід");
    expect(w.text()).toContain("Музей");
    expect(w.text()).toContain("УБД");
  });

  it("links to the offer detail route", () => {
    const w = mountCard({ id: 9, type: "event", title: "Подія", provider: "X", image_url: "https://x/y.png", target_categories: [] });
    const link = w.getComponent({ name: "RouterLink" });
    expect(link.props("to")).toEqual({ name: "offer", params: { id: 9 } });
    expect(w.get("img").attributes("src")).toBe("https://x/y.png");
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd public && npx vitest run tests/components/OfferBadge.test.js tests/components/OfferCard.test.js`
Expected: FAIL — components undefined.

- [ ] **Step 4: Create `public/src/components/OfferBadge.vue`**

```vue
<script setup>
import { computed } from "vue";
import { offerBadge } from "@/utils/format";

const props = defineProps({ offer: { type: Object, required: true } });
const badge = computed(() => offerBadge(props.offer));
</script>

<template>
  <span class="badge" :class="`badge--${badge.kind}`">{{ badge.text }}</span>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 13px; font-weight: 600; color: #fff; }
.badge--event { background: #6d28d9; }
.badge--free { background: #059669; }
.badge--discount { background: @brand; }
</style>
```

- [ ] **Step 5: Create `public/src/components/OfferCard.vue`**

```vue
<script setup>
import { computed } from "vue";
import { placeholderDataUri } from "@/utils/placeholder";
import OfferBadge from "@/components/OfferBadge.vue";

const props = defineProps({ offer: { type: Object, required: true } });
const image = computed(() => props.offer.image_url || placeholderDataUri(props.offer));
</script>

<template>
  <router-link class="card" :to="{ name: 'offer', params: { id: offer.id } }">
    <div class="card__media">
      <img :src="image" alt="" />
      <OfferBadge :offer="offer" class="card__badge" />
    </div>
    <div class="card__body">
      <h3 class="card__title">{{ offer.title }}</h3>
      <div class="card__provider">{{ offer.provider }}</div>
      <div v-if="offer.location" class="card__location">{{ offer.location }}</div>
      <div v-if="offer.target_categories?.length" class="card__tags">
        <span v-for="t in offer.target_categories" :key="t.id" class="tag">{{ t.name }}</span>
      </div>
    </div>
  </router-link>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.card { display: block; background: @card-bg; border: 1px solid @border; border-radius: @radius; overflow: hidden; color: @text; }
.card:hover { text-decoration: none; box-shadow: 0 4px 16px rgba(0,0,0,0.08); }
.card__media { position: relative; }
.card__media img { display: block; width: 100%; height: 180px; object-fit: cover; }
.card__badge { position: absolute; top: 8px; left: 8px; }
.card__body { padding: 12px; }
.card__title { margin: 0 0 4px; font-size: 16px; }
.card__provider { color: @muted; font-size: 14px; }
.card__location { color: @muted; font-size: 13px; margin-top: 4px; }
.card__tags { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 4px; }
.tag { font-size: 12px; background: #eef2f7; color: @muted; border-radius: 6px; padding: 1px 6px; }
</style>
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd public && npx vitest run tests/components/OfferBadge.test.js tests/components/OfferCard.test.js`
Expected: PASS (4 tests).

- [ ] **Step 7: Commit**

```bash
git add public/src/components/OfferBadge.vue public/src/components/OfferCard.vue public/tests/components/OfferBadge.test.js public/tests/components/OfferCard.test.js
git commit -m "feat(public): offer badge and offer card components"
```

---

### Task 7: OfferFilters dropdown panel

**Files:**
- Create: `public/src/components/OfferFilters.vue`
- Test: `public/tests/components/OfferFilters.test.js`

**Interfaces:**
- Consumes: `constants/enums.js` `OFFER_TYPES`.
- Produces: `OfferFilters` — props `modelValue` (current filters object, e.g. `{ type, target_category, offer_category, location, q }`), `targetCategories` (array), `offerCategories` (array). A "Фільтри" button (showing an active-filter count from `modelValue`) toggles a dropdown `panel`. The panel holds a local `draft` (seeded from `modelValue` when opened) with: type select, target-category select, offer-category select, location text, search text. **Застосувати** emits `apply` with a cleaned object (empty values dropped) and closes. **Скинути** emits `apply` with `{}` and closes. A backdrop click closes without applying. Exposes `{ open, draft, apply, reset, activeCount }` via `defineExpose`.

- [ ] **Step 1: Write the failing test — `public/tests/components/OfferFilters.test.js`**

```js
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import OfferFilters from "@/components/OfferFilters.vue";

function mountFilters(modelValue = {}) {
  return mount(OfferFilters, {
    props: {
      modelValue,
      targetCategories: [{ id: 1, name: "УБД" }],
      offerCategories: [{ id: 2, name: "Розваги" }],
    },
  });
}

describe("OfferFilters", () => {
  it("counts active filters from modelValue", () => {
    const w = mountFilters({ type: "discount", q: "кава" });
    expect(w.vm.activeCount).toBe(2);
  });

  it("apply emits cleaned filters and closes", async () => {
    const w = mountFilters({});
    w.vm.open = true;
    Object.assign(w.vm.draft, { type: "event", location: "", q: "музей" });
    w.vm.apply();
    expect(w.emitted().apply[0][0]).toEqual({ type: "event", q: "музей" });
    expect(w.vm.open).toBe(false);
  });

  it("reset emits empty filters", () => {
    const w = mountFilters({ type: "discount" });
    w.vm.reset();
    expect(w.emitted().apply[0][0]).toEqual({});
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd public && npx vitest run tests/components/OfferFilters.test.js`
Expected: FAIL — component undefined.

- [ ] **Step 3: Create `public/src/components/OfferFilters.vue`**

```vue
<script setup>
import { reactive, ref, computed, watch } from "vue";
import { OFFER_TYPES } from "@/constants/enums";

const props = defineProps({
  modelValue: { type: Object, default: () => ({}) },
  targetCategories: { type: Array, default: () => [] },
  offerCategories: { type: Array, default: () => [] },
});
const emit = defineEmits(["apply"]);

const open = ref(false);
const draft = reactive({ type: "", target_category: "", offer_category: "", location: "", q: "" });

function seed() {
  draft.type = props.modelValue.type || "";
  draft.target_category = props.modelValue.target_category || "";
  draft.offer_category = props.modelValue.offer_category || "";
  draft.location = props.modelValue.location || "";
  draft.q = props.modelValue.q || "";
}
watch(open, (isOpen) => { if (isOpen) seed(); });

const activeCount = computed(
  () => ["type", "target_category", "offer_category", "location", "q"].filter((k) => props.modelValue[k]).length
);

function clean() {
  const out = {};
  for (const k of ["type", "target_category", "offer_category", "location", "q"]) {
    if (draft[k]) out[k] = draft[k];
  }
  return out;
}

function apply() {
  emit("apply", clean());
  open.value = false;
}

function reset() {
  emit("apply", {});
  open.value = false;
}

defineExpose({ open, draft, apply, reset, activeCount });
</script>

<template>
  <div class="filters">
    <button class="filters__trigger" @click="open = !open">
      Фільтри<span v-if="activeCount" class="filters__count">{{ activeCount }}</span>
    </button>

    <div v-if="open" class="filters__backdrop" @click="open = false"></div>

    <div v-if="open" class="filters__panel">
      <label>Тип
        <select v-model="draft.type">
          <option value="">Усі</option>
          <option v-for="t in OFFER_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
        </select>
      </label>
      <label>Для кого
        <select v-model="draft.target_category">
          <option value="">Усі</option>
          <option v-for="c in targetCategories" :key="c.id" :value="String(c.id)">{{ c.name }}</option>
        </select>
      </label>
      <label>Тематика
        <select v-model="draft.offer_category">
          <option value="">Усі</option>
          <option v-for="c in offerCategories" :key="c.id" :value="String(c.id)">{{ c.name }}</option>
        </select>
      </label>
      <label>Локація
        <input v-model="draft.location" type="text" placeholder="Місто або «онлайн»" />
      </label>
      <label>Пошук
        <input v-model="draft.q" type="text" placeholder="Ключове слово" @keyup.enter="apply" />
      </label>
      <div class="filters__actions">
        <button class="btn btn--primary" @click="apply">Застосувати</button>
        <button class="btn" @click="reset">Скинути</button>
      </div>
    </div>
  </div>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.filters { position: relative; display: inline-block; }
.filters__trigger { padding: 8px 14px; border: 1px solid @border; border-radius: @radius; background: @bg; cursor: pointer; font-size: 15px; }
.filters__count { margin-left: 6px; background: @brand; color: #fff; border-radius: 999px; padding: 0 7px; font-size: 12px; }
.filters__backdrop { position: fixed; inset: 0; z-index: 10; }
.filters__panel { position: absolute; z-index: 11; top: calc(100% + 6px); left: 0; width: min(320px, 90vw); background: @bg; border: 1px solid @border; border-radius: @radius; box-shadow: 0 8px 28px rgba(0,0,0,0.12); padding: 14px; display: flex; flex-direction: column; gap: 10px; }
.filters__panel label { display: flex; flex-direction: column; gap: 4px; font-size: 14px; color: @muted; }
.filters__panel select, .filters__panel input { padding: 7px; border: 1px solid @border; border-radius: 8px; font-size: 15px; color: @text; }
.filters__actions { display: flex; gap: 8px; margin-top: 4px; }
.btn { padding: 8px 12px; border: 1px solid @border; border-radius: 8px; background: @bg; cursor: pointer; }
.btn--primary { background: @brand; color: #fff; border-color: @brand; }
@media (max-width: @bp-mobile) {
  .filters { display: block; }
  .filters__panel { width: 100%; }
}
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd public && npx vitest run tests/components/OfferFilters.test.js`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add public/src/components/OfferFilters.vue public/tests/components/OfferFilters.test.js
git commit -m "feat(public): filters dropdown panel"
```

---

### Task 8: OfferGrid and Pagination

**Files:**
- Create: `public/src/components/OfferGrid.vue`, `public/src/components/Pagination.vue`
- Test: `public/tests/components/OfferGrid.test.js`, `public/tests/components/Pagination.test.js`

**Interfaces:**
- Consumes: `OfferCard`; `vue-router` (OfferCard needs router in tests).
- Produces:
  - `OfferGrid` — props `offers` (array), `loading` (bool), `error` (string|null). Renders: when `loading` a loading message; else when `error` the error message; else when `offers` is empty an "Нічого не знайдено" message; else a grid of `OfferCard`.
  - `Pagination` — props `total` (number), `size` (number), `page` (number). Computes `totalPages = Math.ceil(total / size)`. Renders nothing when `totalPages <= 1`. Otherwise a prev button (disabled at `page <= 1`), a "Сторінка X з Y" label, and a next button (disabled at `page >= totalPages`). Emits `change` with the new page number.

- [ ] **Step 1: Write the failing test — `public/tests/components/OfferGrid.test.js`**

```js
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import OfferGrid from "@/components/OfferGrid.vue";

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: "/offers/:id", name: "offer", component: { template: "<div/>" } }],
});

function mountGrid(props) {
  return mount(OfferGrid, { props, global: { plugins: [router] } });
}

describe("OfferGrid", () => {
  it("shows loading state", () => {
    const w = mountGrid({ offers: [], loading: true, error: null });
    expect(w.text()).toContain("Завантаження");
  });
  it("shows error state", () => {
    const w = mountGrid({ offers: [], loading: false, error: "Ой" });
    expect(w.text()).toContain("Ой");
  });
  it("shows empty state", () => {
    const w = mountGrid({ offers: [], loading: false, error: null });
    expect(w.text()).toContain("Нічого не знайдено");
  });
  it("renders one card per offer", () => {
    const offers = [
      { id: 1, type: "discount", discount_type: "free", title: "A", provider: "P", target_categories: [] },
      { id: 2, type: "event", title: "B", provider: "Q", target_categories: [] },
    ];
    const w = mountGrid({ offers, loading: false, error: null });
    expect(w.findAllComponents({ name: "OfferCard" }).length).toBe(2);
  });
});
```

- [ ] **Step 2: Write the failing test — `public/tests/components/Pagination.test.js`**

```js
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import Pagination from "@/components/Pagination.vue";

describe("Pagination", () => {
  it("renders nothing for a single page", () => {
    const w = mount(Pagination, { props: { total: 10, size: 12, page: 1 } });
    expect(w.find("button").exists()).toBe(false);
  });

  it("emits the next page", async () => {
    const w = mount(Pagination, { props: { total: 40, size: 12, page: 1 } });
    await w.get("[data-test=next]").trigger("click");
    expect(w.emitted().change[0]).toEqual([2]);
  });

  it("disables prev on the first page and next on the last", () => {
    const first = mount(Pagination, { props: { total: 40, size: 12, page: 1 } });
    expect(first.get("[data-test=prev]").attributes("disabled")).toBeDefined();
    const last = mount(Pagination, { props: { total: 40, size: 12, page: 4 } });
    expect(last.get("[data-test=next]").attributes("disabled")).toBeDefined();
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd public && npx vitest run tests/components/OfferGrid.test.js tests/components/Pagination.test.js`
Expected: FAIL — components undefined.

- [ ] **Step 4: Create `public/src/components/OfferGrid.vue`**

```vue
<script setup>
import OfferCard from "@/components/OfferCard.vue";

defineProps({
  offers: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: String, default: null },
});
</script>

<template>
  <div class="grid-wrap">
    <p v-if="loading" class="state">Завантаження…</p>
    <p v-else-if="error" class="state state--error">{{ error }}</p>
    <p v-else-if="!offers.length" class="state">Нічого не знайдено. Спробуйте змінити або скинути фільтри.</p>
    <div v-else class="grid">
      <OfferCard v-for="o in offers" :key="o.id" :offer="o" />
    </div>
  </div>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.state { color: @muted; padding: 32px 0; text-align: center; }
.state--error { color: #b00020; }
@media (max-width: 900px) { .grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: @bp-mobile) { .grid { grid-template-columns: 1fr; } }
</style>
```

- [ ] **Step 5: Create `public/src/components/Pagination.vue`**

```vue
<script setup>
import { computed } from "vue";

const props = defineProps({
  total: { type: Number, default: 0 },
  size: { type: Number, default: 12 },
  page: { type: Number, default: 1 },
});
const emit = defineEmits(["change"]);

const totalPages = computed(() => Math.ceil(props.total / props.size));

function go(p) {
  if (p >= 1 && p <= totalPages.value && p !== props.page) emit("change", p);
}
</script>

<template>
  <nav v-if="totalPages > 1" class="pagination">
    <button data-test="prev" class="btn" :disabled="page <= 1" @click="go(page - 1)">← Назад</button>
    <span class="pagination__label">Сторінка {{ page }} з {{ totalPages }}</span>
    <button data-test="next" class="btn" :disabled="page >= totalPages" @click="go(page + 1)">Далі →</button>
  </nav>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.pagination { display: flex; align-items: center; justify-content: center; gap: 12px; margin: 24px 0; }
.pagination__label { color: @muted; font-size: 14px; }
.btn { padding: 8px 14px; border: 1px solid @border; border-radius: 8px; background: @bg; cursor: pointer; }
.btn:disabled { opacity: 0.5; cursor: default; }
</style>
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd public && npx vitest run tests/components/OfferGrid.test.js tests/components/Pagination.test.js`
Expected: PASS (7 tests).

- [ ] **Step 7: Commit**

```bash
git add public/src/components/OfferGrid.vue public/src/components/Pagination.vue public/tests/components/OfferGrid.test.js public/tests/components/Pagination.test.js
git commit -m "feat(public): offer grid and pagination"
```

---

### Task 9: OffersView (list page)

**Files:**
- Modify: `public/src/views/OffersView.vue` (replace stub)
- Test: `public/tests/views/OffersView.test.js`

**Interfaces:**
- Consumes: `composables/useOffers.js`, `composables/useDictionaries.js`; `components/OfferFilters.vue`, `components/OfferGrid.vue`, `components/Pagination.vue`; `vue-router` `useRoute`/`useRouter`.
- Produces: `OffersView` — on mount calls `dictionaries.load()`. Computes `currentFilters` from `route.query` (`type`, `target_category`, `offer_category`, `location`, `q`). `onApply(filters)` → `router.push({ name: "offers", query: { ...filters } })` (drops page → back to page 1). `onPage(page)` → `router.push({ name: "offers", query: { ...route.query, page } })`. Renders title, `OfferFilters` (`:model-value="currentFilters"`, dictionaries, `@apply`), `OfferGrid` (`:offers`, `:loading`, `:error` from `useOffers`), `Pagination` (`:total`, `:size`, `:page`, `@change="onPage"`).

- [ ] **Step 1: Write the failing test — `public/tests/views/OffersView.test.js`**

```js
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import OffersView from "@/views/OffersView.vue";

vi.mock("@/api/offers", () => ({
  list: vi.fn(() => Promise.resolve({ items: [{ id: 1, type: "event", title: "T", provider: "P", target_categories: [] }], total: 1, page: 1, size: 12 })),
}));
vi.mock("@/api/categories", () => ({
  listTarget: vi.fn(() => Promise.resolve([])),
  listOffer: vi.fn(() => Promise.resolve([])),
}));
import * as offers from "@/api/offers";

function makeRouter() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", name: "offers", component: OffersView },
      { path: "/offers/:id", name: "offer", component: { template: "<div/>" } },
    ],
  });
  return router;
}

describe("OffersView", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads offers on mount", async () => {
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    mount(OffersView, { global: { plugins: [router] } });
    await flushPromises();
    expect(offers.list).toHaveBeenCalledWith({ page: 1, size: 12 });
  });

  it("applying filters updates the query and refetches", async () => {
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    const wrapper = mount(OffersView, { global: { plugins: [router] } });
    await flushPromises();
    wrapper.getComponent({ name: "OfferFilters" }).vm.$emit("apply", { type: "discount", q: "кава" });
    await flushPromises();
    expect(router.currentRoute.value.query).toEqual({ type: "discount", q: "кава" });
    expect(offers.list).toHaveBeenLastCalledWith({ page: 1, size: 12, type: "discount", q: "кава" });
  });

  it("changing page updates the query", async () => {
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    const wrapper = mount(OffersView, { global: { plugins: [router] } });
    await flushPromises();
    wrapper.vm.onPage(2);
    await flushPromises();
    expect(router.currentRoute.value.query.page).toBe("2");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd public && npx vitest run tests/views/OffersView.test.js`
Expected: FAIL — stub has no behaviour.

- [ ] **Step 3: Replace `public/src/views/OffersView.vue`**

```vue
<script setup>
import { computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useOffers } from "@/composables/useOffers";
import { useDictionaries } from "@/composables/useDictionaries";
import OfferFilters from "@/components/OfferFilters.vue";
import OfferGrid from "@/components/OfferGrid.vue";
import Pagination from "@/components/Pagination.vue";

const route = useRoute();
const router = useRouter();
const { items, total, loading, error, size, page } = useOffers();
const { targetCategories, offerCategories, load: loadDicts } = useDictionaries();

onMounted(loadDicts);

const FILTER_KEYS = ["type", "target_category", "offer_category", "location", "q"];
const currentFilters = computed(() => {
  const f = {};
  for (const k of FILTER_KEYS) if (route.query[k]) f[k] = route.query[k];
  return f;
});

function onApply(filters) {
  router.push({ name: "offers", query: { ...filters } });
}

function onPage(p) {
  router.push({ name: "offers", query: { ...route.query, page: p } });
}

defineExpose({ onApply, onPage });
</script>

<template>
  <div class="container offers">
    <div class="offers__head">
      <h1>Знижки та події для УБД</h1>
      <OfferFilters
        :model-value="currentFilters"
        :target-categories="targetCategories"
        :offer-categories="offerCategories"
        @apply="onApply"
      />
    </div>
    <OfferGrid :offers="items" :loading="loading" :error="error" />
    <Pagination :total="total" :size="size" :page="page" @change="onPage" />
  </div>
</template>

<style scoped lang="less">
.offers__head { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; margin-bottom: 16px; }
.offers__head h1 { font-size: 24px; margin: 0; }
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd public && npx vitest run tests/views/OffersView.test.js`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add public/src/views/OffersView.vue public/tests/views/OffersView.test.js
git commit -m "feat(public): offers list page wiring filters, grid, pagination"
```

---

### Task 10: OfferDetailView, NotFound, and full-suite green

**Files:**
- Modify: `public/src/views/OfferDetailView.vue` (replace stub)
- Create: `public/README.md`
- Test: `public/tests/views/OfferDetailView.test.js`

**Interfaces:**
- Consumes: `api/offers.js` `get`; `utils/format.js` (`formatDate`, `enumLabel`); `utils/placeholder.js` `placeholderDataUri`; `components/OfferBadge.vue`; `vue-router` `useRoute`.
- Produces: `OfferDetailView` — reads `route.params.id`, calls `offers.get(id)` on mount into `offer`; `loading` while pending; on rejection sets `notFound = true`. Renders (success) image (`image_url` or placeholder), `OfferBadge`, title, provider, description, "для кого" tags, topic tags, location, validity period (`formatDate(valid_from)`–`formatDate(valid_until)` when present), contacts, and a "← до списку" link. On not-found shows a message + link home. Never shows `source_id`. Exposes `{ offer, loading, notFound }`.

- [ ] **Step 1: Write the failing test — `public/tests/views/OfferDetailView.test.js`**

```js
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import OfferDetailView from "@/views/OfferDetailView.vue";

vi.mock("@/api/offers", () => ({ get: vi.fn() }));
import * as offers from "@/api/offers";

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", name: "offers", component: { template: "<div/>" } },
      { path: "/offers/:id", name: "offer", component: OfferDetailView },
    ],
  });
}

async function mountAt(id) {
  const router = makeRouter();
  router.push(`/offers/${id}`);
  await router.isReady();
  const wrapper = mount(OfferDetailView, { global: { plugins: [router] } });
  await flushPromises();
  return wrapper;
}

describe("OfferDetailView", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads and renders an offer", async () => {
    offers.get.mockResolvedValue({
      id: 5, type: "discount", discount_type: "percent", discount_value: 30,
      title: "Знижка 30%", provider: "Кафе", description: "Опис", location: "Київ",
      valid_from: "2026-07-01", valid_until: "2026-08-01", contacts: "0501112233",
      image_url: null, target_categories: [{ id: 1, name: "УБД" }], offer_categories: [{ id: 2, name: "Кафе" }],
    });
    const w = await mountAt(5);
    expect(offers.get).toHaveBeenCalledWith("5");
    expect(w.text()).toContain("Знижка 30%");
    expect(w.text()).toContain("Кафе");
    expect(w.text()).toContain("0501112233");
    expect(w.text()).toContain("01.07.2026");
  });

  it("shows a not-found state when the offer is missing", async () => {
    offers.get.mockRejectedValue({ response: { status: 404 } });
    const w = await mountAt(999);
    expect(w.vm.notFound).toBe(true);
    expect(w.text()).toContain("не знайдено");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd public && npx vitest run tests/views/OfferDetailView.test.js`
Expected: FAIL — stub has no behaviour.

- [ ] **Step 3: Replace `public/src/views/OfferDetailView.vue`**

```vue
<script setup>
import { ref, computed, onMounted } from "vue";
import { useRoute } from "vue-router";
import * as offersApi from "@/api/offers";
import { formatDate } from "@/utils/format";
import { placeholderDataUri } from "@/utils/placeholder";
import OfferBadge from "@/components/OfferBadge.vue";

const route = useRoute();
const offer = ref(null);
const loading = ref(true);
const notFound = ref(false);

const image = computed(() =>
  offer.value ? offer.value.image_url || placeholderDataUri(offer.value) : ""
);
const period = computed(() => {
  if (!offer.value) return "";
  const from = formatDate(offer.value.valid_from);
  const to = formatDate(offer.value.valid_until);
  if (from && to) return `${from} – ${to}`;
  return from || to || "";
});

onMounted(async () => {
  try {
    offer.value = await offersApi.get(route.params.id);
  } catch {
    notFound.value = true;
  } finally {
    loading.value = false;
  }
});

defineExpose({ offer, loading, notFound });
</script>

<template>
  <div class="container detail">
    <p v-if="loading" class="state">Завантаження…</p>

    <div v-else-if="notFound" class="state">
      <h1>Оффер не знайдено</h1>
      <router-link :to="{ name: 'offers' }">← до списку</router-link>
    </div>

    <article v-else>
      <router-link :to="{ name: 'offers' }" class="back">← до списку</router-link>
      <div class="detail__media">
        <img :src="image" alt="" />
        <OfferBadge :offer="offer" class="detail__badge" />
      </div>
      <h1>{{ offer.title }}</h1>
      <div class="detail__provider">{{ offer.provider }}</div>
      <p v-if="offer.description" class="detail__desc">{{ offer.description }}</p>

      <div v-if="offer.target_categories?.length" class="detail__row">
        <span class="detail__label">Для кого:</span>
        <span v-for="t in offer.target_categories" :key="t.id" class="tag">{{ t.name }}</span>
      </div>
      <div v-if="offer.offer_categories?.length" class="detail__row">
        <span class="detail__label">Тематика:</span>
        <span v-for="c in offer.offer_categories" :key="c.id" class="tag">{{ c.name }}</span>
      </div>
      <div v-if="offer.location" class="detail__row"><span class="detail__label">Локація:</span> {{ offer.location }}</div>
      <div v-if="period" class="detail__row"><span class="detail__label">Діє:</span> {{ period }}</div>
      <div v-if="offer.contacts" class="detail__row"><span class="detail__label">Контакти:</span> {{ offer.contacts }}</div>
    </article>
  </div>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.back { display: inline-block; margin-bottom: 12px; }
.detail__media { position: relative; border-radius: @radius; overflow: hidden; margin-bottom: 12px; }
.detail__media img { width: 100%; max-height: 360px; object-fit: cover; display: block; }
.detail__badge { position: absolute; top: 12px; left: 12px; }
.detail__provider { color: @muted; margin-bottom: 12px; }
.detail__desc { line-height: 1.5; }
.detail__row { margin: 6px 0; }
.detail__label { color: @muted; margin-right: 6px; }
.tag { display: inline-block; font-size: 13px; background: #eef2f7; color: @muted; border-radius: 6px; padding: 1px 8px; margin-right: 4px; }
.state { text-align: center; padding: 48px 0; color: @muted; }
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd public && npx vitest run tests/views/OfferDetailView.test.js`
Expected: PASS (2 tests).

- [ ] **Step 5: Create `public/README.md`**

```markdown
# UBD Public

Vue 3 + Vite public site for the UBD discounts platform. Shows published offers
with a filter panel, pagination, and a detail view. No auth.

## Development

    npm install
    npm run dev        # http://localhost:5174, proxies /api → http://localhost:8000

The backend must be running on port 8000 (see ../backend).

## Tests

    npm run test       # Vitest, no backend required (API is mocked)
```

- [ ] **Step 6: Run the FULL suite**

Run: `cd public && npm run test`
Expected: ALL test files pass, output pristine.

- [ ] **Step 7: Commit**

```bash
git add public/src/views/OfferDetailView.vue public/README.md public/tests/views/OfferDetailView.test.js
git commit -m "feat(public): offer detail view; full suite green"
```

---

## Self-Review Notes

- **Spec coverage:**
  - Tech stack (Vue 3 / Vite / Router / axios / Less / Vitest, no Pinia, no UI lib) — Task 1.
  - Copied placeholder/format/enums + `offerBadge` — Task 2.
  - Open-endpoint API layer — Task 3.
  - `useDictionaries` (cached) + `useOffers` (query→params, reload on query change) — Task 4.
  - Router (list / detail / catch-all), app shell header+footer — Task 5.
  - OfferBadge + OfferCard (image/placeholder, link, tags) — Task 6.
  - OfferFilters dropdown panel (Фільтри button + count, Застосувати/Скинути, backdrop close) — Task 7.
  - OfferGrid (loading/empty/error/list) + Pagination — Task 8.
  - OffersView (filters↔URL, page↔URL, compose) — Task 9.
  - OfferDetailView (load by id, not-found, no source_id) + NotFound (Task 5) — Task 10.
  - Image placeholder reuse — Tasks 2, 6, 10.
  - Error/loading/empty handling — Tasks 8, 10.
  - Responsive Less — Tasks 6, 8 (grid), 7 (panel).
- **URL as source of truth:** `useOffers` watches `route.query`; `OffersView.onApply`/`onPage` only push to the router — no local filter state. Consistent across Tasks 4 and 9.
- **Category ids as strings in the URL:** `OfferFilters` binds `:value="String(c.id)"`, and query params are strings; the backend accepts them as `int` query params. Consistent.
- **Naming consistency:** `offers.list`/`offers.get`, `categories.listTarget`/`listOffer`, `useOffers`/`useDictionaries`, `offerBadge`, `placeholderDataUri`, event `apply` (filters) and `change` (pagination) — used identically across tasks.
- **No backend changes, no admin/internal endpoints, no auth** anywhere.
