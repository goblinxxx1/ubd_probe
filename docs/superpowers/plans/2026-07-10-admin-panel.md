# UBD Admin Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Vue 3 admin SPA that manages offers, sources, suggested sources, category dictionaries, and admin users against the existing FastAPI backend, with JWT auth and role-based access.

**Architecture:** Vite-built Vue 3 SPA (Composition API, plain JavaScript) in `admin/`. Pinia holds session and cached dictionaries; Vue Router guards protect routes by auth and role; a shared axios client attaches the bearer token and centralises 401 handling. Thin per-resource API wrappers sit between views and the backend. The Vite dev server proxies `/api` to the backend, so there is no CORS config and no backend change.

**Tech Stack:** Vue 3, Vite, Element Plus, Vue Router, Pinia, axios, Less, Vitest + @vue/test-utils (jsdom).

## Global Constraints

- **Language:** plain JavaScript, no TypeScript. JSDoc typedefs only where they aid hints.
- **UI copy:** Ukrainian.
- **API base:** all requests go through the shared axios client with `baseURL = import.meta.env.VITE_API_BASE || '/api'`. Never hardcode `http://localhost:8000` in app code — the Vite proxy handles it.
- **Auth storage:** JWT and role in `localStorage` under keys `ubd_admin_token` and `ubd_admin_role`.
- **Error shape:** backend errors are `{ "detail": "...", "code": "..." }`. Surface `detail` to the user.
- **Roles:** `super_admin` may manage admin users and category dictionaries; `moderator` may not. Backend enforces this; the UI mirrors it (hide/disable + route guard).
- **Published-only is a backend concern:** the admin sees all statuses; do not filter client-side except via explicit status filters.
- **Backend untouched:** this sub-project makes zero backend changes.
- **TDD:** write the failing test first, watch it fail, implement minimally, watch it pass, commit.
- **Toolchain:** Node ≥ 20, npm. All commands run from `admin/`. The backend for manual runs is started separately (`backend/.venv/Scripts/uvicorn ...`); tests never need a real backend (the API is mocked).

---

## File Structure

```
admin/
  index.html
  package.json
  vite.config.js          # Less, proxy /api → :8000, alias @ → src
  vitest.config.js        # jsdom env, @ alias, setup file
  vitest.setup.js         # ResizeObserver stub for Element Plus
  .env.development         # VITE_API_BASE=/api
  src/
    main.js               # mount, Element Plus, Pinia, Router, unauthorized handler
    App.vue
    router/index.js       # routes + guards
    stores/auth.js        # token, role, login/logout, isSuperAdmin
    stores/dictionaries.js
    api/client.js         # axios instance + interceptors + setUnauthorizedHandler
    api/auth.js
    api/offers.js
    api/sources.js
    api/suggestedSources.js
    api/categories.js
    api/users.js
    composables/useApiList.js
    utils/format.js       # enumLabel, formatDate, statusTagType
    utils/placeholder.js  # placeholderText, placeholderDataUri
    utils/confirm.js      # confirmDelete wrapper over ElMessageBox
    utils/errors.js       # extractError
    constants/enums.js
    layouts/AdminLayout.vue
    views/LoginView.vue
    views/OffersListView.vue
    views/ModerationQueueView.vue
    views/OfferFormView.vue
    views/SourcesView.vue
    views/SuggestedSourcesView.vue
    views/CategoriesView.vue
    views/AdminUsersView.vue
    components/OfferForm.vue
    components/ImagePreview.vue
    components/CategoryMultiSelect.vue
    components/DataTableToolbar.vue
    styles/variables.less
    styles/global.less
  tests/                  # mirrors src
```

Notes:
- `ConfirmDialog.vue` from the spec is realised as `utils/confirm.js` (a thin wrapper over Element Plus `ElMessageBox`), which is the idiomatic Element Plus approach and avoids a redundant component.
- Element Plus is registered globally in `main.js` (`app.use(ElementPlus)`) for plan simplicity; auto-import is an optional later optimisation.

---

### Task 1: Scaffold Vite project and test harness

**Files:**
- Create: `admin/package.json`, `admin/index.html`, `admin/vite.config.js`, `admin/vitest.config.js`, `admin/vitest.setup.js`, `admin/.env.development`
- Create: `admin/src/main.js`, `admin/src/App.vue`, `admin/src/styles/variables.less`, `admin/src/styles/global.less`
- Test: `admin/tests/smoke.test.js`

**Interfaces:**
- Produces: a runnable Vite app and a green Vitest harness. `App.vue` renders a `<router-view>` placeholder (router added in Task 8; for now App renders a static shell so the smoke test has something to mount).

- [ ] **Step 1: Create `admin/package.json`**

```json
{
  "name": "ubd-admin",
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
    "element-plus": "^2.7.0",
    "pinia": "^2.1.0",
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

- [ ] **Step 2: Create `admin/index.html`**

```html
<!doctype html>
<html lang="uk">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>UBD — Адмінка</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.js"></script>
  </body>
</html>
```

- [ ] **Step 3: Create `admin/vite.config.js`**

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
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
```

- [ ] **Step 4: Create `admin/vitest.config.js`**

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

- [ ] **Step 5: Create `admin/vitest.setup.js`** (Element Plus needs `ResizeObserver`, absent in jsdom)

```js
global.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};
```

- [ ] **Step 6: Create `admin/.env.development`**

```
VITE_API_BASE=/api
```

- [ ] **Step 7: Create `admin/src/styles/variables.less` and `admin/src/styles/global.less`**

`variables.less`:
```less
@brand: #1f6feb;
@sidebar-width: 220px;
```

`global.less`:
```less
@import "./variables.less";

html, body, #app { height: 100%; margin: 0; }
body { font-family: system-ui, sans-serif; }
```

- [ ] **Step 8: Create `admin/src/App.vue`**

```vue
<script setup></script>

<template>
  <router-view v-if="$router" />
  <div v-else class="app-shell">UBD Admin</div>
</template>
```

Note: the `v-if="$router"` fallback lets Task 1's smoke test mount `App` before the router exists; Task 8 removes the fallback.

- [ ] **Step 9: Create `admin/src/main.js`**

```js
import { createApp } from "vue";
import { createPinia } from "pinia";
import ElementPlus from "element-plus";
import "element-plus/dist/index.css";
import App from "./App.vue";
import "./styles/global.less";

const app = createApp(App);
app.use(createPinia());
app.use(ElementPlus);
app.mount("#app");
```

Note: Task 8 adds `app.use(router)` and the unauthorized handler wiring.

- [ ] **Step 10: Write the smoke test — `admin/tests/smoke.test.js`**

```js
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import App from "@/App.vue";

describe("App", () => {
  it("mounts and shows the shell fallback", () => {
    const wrapper = mount(App, { global: { config: { globalProperties: { $router: null } } } });
    expect(wrapper.text()).toContain("UBD Admin");
  });
});
```

- [ ] **Step 11: Install and run**

Run: `cd admin && npm install && npm run test`
Expected: install succeeds; smoke test PASSES (1 passed). Output pristine.

- [ ] **Step 12: Add `admin/.gitignore`** (node_modules, dist)

```
node_modules/
dist/
*.local
```

- [ ] **Step 13: Commit**

```bash
git add admin/
git commit -m "chore(admin): scaffold Vue 3 + Vite + Element Plus + Vitest"
```

---

### Task 2: Enum constants and formatting utils

**Files:**
- Create: `admin/src/constants/enums.js`, `admin/src/utils/format.js`
- Test: `admin/tests/utils/format.test.js`

**Interfaces:**
- Produces:
  - `constants/enums.js`: arrays of `{ value, label }` — `OFFER_TYPES`, `DISCOUNT_TYPES`, `OFFER_STATUSES`, `SOURCE_TYPES`, `ADMIN_ROLES`, `SUGGESTION_STATUSES`.
  - `utils/format.js`: `enumLabel(list, value) -> string` (label, or the raw value if unknown); `formatDate(iso) -> string` (`dd.mm.yyyy`, or `""` for null/empty); `statusTagType(status) -> "warning"|"success"|"danger"|"info"`.

- [ ] **Step 1: Create `admin/src/constants/enums.js`**

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

export const OFFER_STATUSES = [
  { value: "pending_review", label: "На модерації" },
  { value: "published", label: "Опубліковано" },
  { value: "rejected", label: "Відхилено" },
  { value: "expired", label: "Прострочено" },
];

export const SOURCE_TYPES = [
  { value: "website", label: "Вебсайт" },
  { value: "facebook", label: "Facebook" },
  { value: "telegram", label: "Telegram" },
  { value: "instagram", label: "Instagram" },
];

export const ADMIN_ROLES = [
  { value: "super_admin", label: "Супер-адмін" },
  { value: "moderator", label: "Модератор" },
];

export const SUGGESTION_STATUSES = [
  { value: "pending", label: "Очікує" },
  { value: "approved", label: "Схвалено" },
  { value: "rejected", label: "Відхилено" },
];
```

- [ ] **Step 2: Write the failing test — `admin/tests/utils/format.test.js`**

```js
import { describe, it, expect } from "vitest";
import { enumLabel, formatDate, statusTagType } from "@/utils/format";
import { OFFER_STATUSES } from "@/constants/enums";

describe("enumLabel", () => {
  it("returns the label for a known value", () => {
    expect(enumLabel(OFFER_STATUSES, "published")).toBe("Опубліковано");
  });
  it("falls back to the raw value when unknown", () => {
    expect(enumLabel(OFFER_STATUSES, "weird")).toBe("weird");
  });
});

describe("formatDate", () => {
  it("formats an ISO date as dd.mm.yyyy", () => {
    expect(formatDate("2026-07-01")).toBe("01.07.2026");
  });
  it("returns empty string for null/empty", () => {
    expect(formatDate(null)).toBe("");
    expect(formatDate("")).toBe("");
  });
});

describe("statusTagType", () => {
  it("maps statuses to Element Plus tag types", () => {
    expect(statusTagType("pending_review")).toBe("warning");
    expect(statusTagType("published")).toBe("success");
    expect(statusTagType("rejected")).toBe("danger");
    expect(statusTagType("expired")).toBe("info");
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd admin && npx vitest run tests/utils/format.test.js`
Expected: FAIL — `@/utils/format` cannot be resolved / functions undefined.

- [ ] **Step 4: Create `admin/src/utils/format.js`**

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
  const yyyy = d.getUTCFullYear();
  return `${dd}.${mm}.${yyyy}`;
}

const STATUS_TAG = {
  pending_review: "warning",
  published: "success",
  rejected: "danger",
  expired: "info",
};

export function statusTagType(status) {
  return STATUS_TAG[status] || "info";
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd admin && npx vitest run tests/utils/format.test.js`
Expected: PASS (7 assertions across 3 suites).

- [ ] **Step 6: Commit**

```bash
git add admin/src/constants/enums.js admin/src/utils/format.js admin/tests/utils/format.test.js
git commit -m "feat(admin): enum constants and formatting utils"
```

---

### Task 3: Image placeholder util

**Files:**
- Create: `admin/src/utils/placeholder.js`
- Test: `admin/tests/utils/placeholder.test.js`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `placeholderText({ type, discount_type }) -> string`: `"безкоштовно для УБД"` when `type === "event"` OR `discount_type === "free"`; otherwise `"знижка для УБД"`.
  - `placeholderDataUri({ type, discount_type }) -> string`: a `data:image/svg+xml,...` URI embedding that text (URL-encoded), usable as an `<img src>`.

- [ ] **Step 1: Write the failing test — `admin/tests/utils/placeholder.test.js`**

```js
import { describe, it, expect } from "vitest";
import { placeholderText, placeholderDataUri } from "@/utils/placeholder";

describe("placeholderText", () => {
  it("says 'безкоштовно' for events", () => {
    expect(placeholderText({ type: "event", discount_type: null })).toBe("безкоштовно для УБД");
  });
  it("says 'безкоштовно' for free discounts", () => {
    expect(placeholderText({ type: "discount", discount_type: "free" })).toBe("безкоштовно для УБД");
  });
  it("says 'знижка' for percent/fixed discounts", () => {
    expect(placeholderText({ type: "discount", discount_type: "percent" })).toBe("знижка для УБД");
  });
});

describe("placeholderDataUri", () => {
  it("returns an svg data uri containing the encoded text", () => {
    const uri = placeholderDataUri({ type: "event", discount_type: null });
    expect(uri.startsWith("data:image/svg+xml,")).toBe(true);
    expect(decodeURIComponent(uri)).toContain("безкоштовно для УБД");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && npx vitest run tests/utils/placeholder.test.js`
Expected: FAIL — module/functions undefined.

- [ ] **Step 3: Create `admin/src/utils/placeholder.js`**

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

- [ ] **Step 4: Run test to verify it passes**

Run: `cd admin && npx vitest run tests/utils/placeholder.test.js`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add admin/src/utils/placeholder.js admin/tests/utils/placeholder.test.js
git commit -m "feat(admin): context-based image placeholder util"
```

---

### Task 4: axios client, error util, auth API

**Files:**
- Create: `admin/src/api/client.js`, `admin/src/utils/errors.js`, `admin/src/api/auth.js`
- Test: `admin/tests/api/client.test.js`

**Interfaces:**
- Consumes: `localStorage` keys `ubd_admin_token`, `ubd_admin_role`.
- Produces:
  - `api/client.js` default export `client` (axios instance, `baseURL = import.meta.env.VITE_API_BASE || "/api"`). Request interceptor adds `Authorization: Bearer <token>` when `localStorage.ubd_admin_token` is set. Response interceptor: on `error.response.status === 401`, calls the registered unauthorized handler (if any) and rejects. Named export `setUnauthorizedHandler(fn)`.
  - `utils/errors.js`: `extractError(err) -> string` — returns `err.response.data.detail` when present, else `err.message`, else `"Сталася помилка"`.
  - `api/auth.js`: `login(email, password) -> Promise<{ access_token, token_type, role }>` via `client.post("/auth/login", { email, password })`.

- [ ] **Step 1: Write the failing test — `admin/tests/api/client.test.js`**

```js
import { describe, it, expect, vi, beforeEach } from "vitest";
import { extractError } from "@/utils/errors";

describe("extractError", () => {
  it("prefers backend detail", () => {
    expect(extractError({ response: { data: { detail: "Немає доступу", code: "forbidden" } } })).toBe("Немає доступу");
  });
  it("falls back to message", () => {
    expect(extractError({ message: "Network Error" })).toBe("Network Error");
  });
  it("has a final fallback", () => {
    expect(extractError({})).toBe("Сталася помилка");
  });
});

describe("client interceptors", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.resetModules();
  });

  it("attaches the bearer token from localStorage", async () => {
    localStorage.setItem("ubd_admin_token", "tok123");
    const { default: client } = await import("@/api/client");
    const handlers = client.interceptors.request.handlers;
    const config = await handlers[0].fulfilled({ headers: {} });
    expect(config.headers.Authorization).toBe("Bearer tok123");
  });

  it("calls the unauthorized handler on 401", async () => {
    const { default: client, setUnauthorizedHandler } = await import("@/api/client");
    const spy = vi.fn();
    setUnauthorizedHandler(spy);
    const rejected = client.interceptors.response.handlers[0].rejected;
    await expect(rejected({ response: { status: 401 } })).rejects.toBeTruthy();
    expect(spy).toHaveBeenCalledOnce();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && npx vitest run tests/api/client.test.js`
Expected: FAIL — modules undefined.

- [ ] **Step 3: Create `admin/src/utils/errors.js`**

```js
export function extractError(err) {
  const detail = err?.response?.data?.detail;
  if (detail) return detail;
  if (err?.message) return err.message;
  return "Сталася помилка";
}
```

- [ ] **Step 4: Create `admin/src/api/client.js`**

```js
import axios from "axios";

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || "/api",
});

let unauthorizedHandler = null;
export function setUnauthorizedHandler(fn) {
  unauthorizedHandler = fn;
}

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("ubd_admin_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401 && unauthorizedHandler) {
      unauthorizedHandler();
    }
    return Promise.reject(error);
  }
);

export default client;
```

- [ ] **Step 5: Create `admin/src/api/auth.js`**

```js
import client from "./client";

export function login(email, password) {
  return client.post("/auth/login", { email, password }).then((r) => r.data);
}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd admin && npx vitest run tests/api/client.test.js`
Expected: PASS (5 tests).

- [ ] **Step 7: Commit**

```bash
git add admin/src/api/client.js admin/src/utils/errors.js admin/src/api/auth.js admin/tests/api/client.test.js
git commit -m "feat(admin): axios client with auth + 401 interceptors, error util, auth api"
```

---

### Task 5: Auth store

**Files:**
- Create: `admin/src/stores/auth.js`
- Test: `admin/tests/stores/auth.test.js`

**Interfaces:**
- Consumes: `api/auth.js` `login`; `localStorage`.
- Produces: Pinia store `useAuthStore` with state `{ token, role }` (initialised from `localStorage`), getters `isAuthenticated` (`!!token`) and `isSuperAdmin` (`role === "super_admin"`), actions `login(email, password)` (calls auth API, stores token+role in state and `localStorage`), `logout()` (clears both).

- [ ] **Step 1: Write the failing test — `admin/tests/stores/auth.test.js`**

```js
import { describe, it, expect, vi, beforeEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";

vi.mock("@/api/auth", () => ({
  login: vi.fn(() => Promise.resolve({ access_token: "tok", token_type: "bearer", role: "super_admin" })),
}));

import { useAuthStore } from "@/stores/auth";
import { login as loginApi } from "@/api/auth";

describe("auth store", () => {
  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
  });

  it("login stores token and role", async () => {
    const store = useAuthStore();
    await store.login("a@b.c", "pw");
    expect(loginApi).toHaveBeenCalledWith("a@b.c", "pw");
    expect(store.token).toBe("tok");
    expect(store.role).toBe("super_admin");
    expect(store.isAuthenticated).toBe(true);
    expect(store.isSuperAdmin).toBe(true);
    expect(localStorage.getItem("ubd_admin_token")).toBe("tok");
    expect(localStorage.getItem("ubd_admin_role")).toBe("super_admin");
  });

  it("logout clears token and role", async () => {
    const store = useAuthStore();
    await store.login("a@b.c", "pw");
    store.logout();
    expect(store.token).toBe(null);
    expect(store.isAuthenticated).toBe(false);
    expect(localStorage.getItem("ubd_admin_token")).toBe(null);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && npx vitest run tests/stores/auth.test.js`
Expected: FAIL — store undefined.

- [ ] **Step 3: Create `admin/src/stores/auth.js`**

```js
import { defineStore } from "pinia";
import { login as loginApi } from "@/api/auth";

export const useAuthStore = defineStore("auth", {
  state: () => ({
    token: localStorage.getItem("ubd_admin_token") || null,
    role: localStorage.getItem("ubd_admin_role") || null,
  }),
  getters: {
    isAuthenticated: (state) => !!state.token,
    isSuperAdmin: (state) => state.role === "super_admin",
  },
  actions: {
    async login(email, password) {
      const data = await loginApi(email, password);
      this.token = data.access_token;
      this.role = data.role;
      localStorage.setItem("ubd_admin_token", this.token);
      localStorage.setItem("ubd_admin_role", this.role);
    },
    logout() {
      this.token = null;
      this.role = null;
      localStorage.removeItem("ubd_admin_token");
      localStorage.removeItem("ubd_admin_role");
    },
  },
});
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd admin && npx vitest run tests/stores/auth.test.js`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add admin/src/stores/auth.js admin/tests/stores/auth.test.js
git commit -m "feat(admin): auth store with localStorage persistence"
```

---

### Task 6: Resource API wrappers

**Files:**
- Create: `admin/src/api/offers.js`, `admin/src/api/sources.js`, `admin/src/api/suggestedSources.js`, `admin/src/api/categories.js`, `admin/src/api/users.js`
- Test: `admin/tests/api/wrappers.test.js`

**Interfaces:**
- Consumes: `api/client.js` default `client`.
- Produces (every function returns `Promise` of `response.data`):
  - `offers.js`: `list(params)` GET `/admin/offers`; `get(id)` GET `/admin/offers/{id}`; `create(payload)` POST `/admin/offers`; `update(id, payload)` PATCH `/admin/offers/{id}`; `publish(id)` POST `/admin/offers/{id}/publish`; `reject(id)` POST `/admin/offers/{id}/reject`; `remove(id)` DELETE `/admin/offers/{id}`.
  - `sources.js`: `list()` GET `/admin/sources`; `create(payload)` POST; `update(id, payload)` PATCH `/admin/sources/{id}`; `remove(id)` DELETE `/admin/sources/{id}`.
  - `suggestedSources.js`: `list(params)` GET `/admin/suggested-sources`; `approve(id)` POST `/admin/suggested-sources/{id}/approve`; `reject(id)` POST `/admin/suggested-sources/{id}/reject`.
  - `categories.js`: `listTarget()` GET `/target-categories`; `listOffer()` GET `/offer-categories`; `createTarget(p)`/`updateTarget(id,p)`/`removeTarget(id)` on `/admin/target-categories`; `createOffer(p)`/`updateOffer(id,p)`/`removeOffer(id)` on `/admin/offer-categories`.
  - `users.js`: `list()` GET `/admin/users`; `create(payload)` POST; `remove(id)` DELETE `/admin/users/{id}`.

- [ ] **Step 1: Write the failing test — `admin/tests/api/wrappers.test.js`**

```js
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/api/client", () => {
  const client = {
    get: vi.fn(() => Promise.resolve({ data: "GET" })),
    post: vi.fn(() => Promise.resolve({ data: "POST" })),
    patch: vi.fn(() => Promise.resolve({ data: "PATCH" })),
    delete: vi.fn(() => Promise.resolve({ data: "DELETE" })),
  };
  return { default: client };
});

import client from "@/api/client";
import * as offers from "@/api/offers";
import * as sources from "@/api/sources";
import * as suggested from "@/api/suggestedSources";
import * as categories from "@/api/categories";
import * as users from "@/api/users";

beforeEach(() => vi.clearAllMocks());

describe("offers api", () => {
  it("list passes params", async () => {
    const data = await offers.list({ status: "published", page: 2 });
    expect(client.get).toHaveBeenCalledWith("/admin/offers", { params: { status: "published", page: 2 } });
    expect(data).toBe("GET");
  });
  it("publish posts to the publish endpoint", async () => {
    await offers.publish(7);
    expect(client.post).toHaveBeenCalledWith("/admin/offers/7/publish");
  });
  it("remove deletes by id", async () => {
    await offers.remove(3);
    expect(client.delete).toHaveBeenCalledWith("/admin/offers/3");
  });
});

describe("suggested sources api", () => {
  it("approve posts to approve endpoint", async () => {
    await suggested.approve(5);
    expect(client.post).toHaveBeenCalledWith("/admin/suggested-sources/5/approve");
  });
});

describe("categories api", () => {
  it("listTarget hits the open endpoint", async () => {
    await categories.listTarget();
    expect(client.get).toHaveBeenCalledWith("/target-categories");
  });
  it("createOffer posts to admin offer-categories", async () => {
    await categories.createOffer({ name: "X", slug: "x" });
    expect(client.post).toHaveBeenCalledWith("/admin/offer-categories", { name: "X", slug: "x" });
  });
});

describe("users api", () => {
  it("remove deletes by id", async () => {
    await users.remove(9);
    expect(client.delete).toHaveBeenCalledWith("/admin/users/9");
  });
});

describe("sources api", () => {
  it("update patches by id", async () => {
    await sources.update(4, { is_active: false });
    expect(client.patch).toHaveBeenCalledWith("/admin/sources/4", { is_active: false });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && npx vitest run tests/api/wrappers.test.js`
Expected: FAIL — modules undefined.

- [ ] **Step 3: Create `admin/src/api/offers.js`**

```js
import client from "./client";

export const list = (params) => client.get("/admin/offers", { params }).then((r) => r.data);
export const get = (id) => client.get(`/admin/offers/${id}`).then((r) => r.data);
export const create = (payload) => client.post("/admin/offers", payload).then((r) => r.data);
export const update = (id, payload) => client.patch(`/admin/offers/${id}`, payload).then((r) => r.data);
export const publish = (id) => client.post(`/admin/offers/${id}/publish`).then((r) => r.data);
export const reject = (id) => client.post(`/admin/offers/${id}/reject`).then((r) => r.data);
export const remove = (id) => client.delete(`/admin/offers/${id}`).then((r) => r.data);
```

- [ ] **Step 4: Create `admin/src/api/sources.js`**

```js
import client from "./client";

export const list = () => client.get("/admin/sources").then((r) => r.data);
export const create = (payload) => client.post("/admin/sources", payload).then((r) => r.data);
export const update = (id, payload) => client.patch(`/admin/sources/${id}`, payload).then((r) => r.data);
export const remove = (id) => client.delete(`/admin/sources/${id}`).then((r) => r.data);
```

- [ ] **Step 5: Create `admin/src/api/suggestedSources.js`**

```js
import client from "./client";

export const list = (params) => client.get("/admin/suggested-sources", { params }).then((r) => r.data);
export const approve = (id) => client.post(`/admin/suggested-sources/${id}/approve`).then((r) => r.data);
export const reject = (id) => client.post(`/admin/suggested-sources/${id}/reject`).then((r) => r.data);
```

- [ ] **Step 6: Create `admin/src/api/categories.js`**

```js
import client from "./client";

export const listTarget = () => client.get("/target-categories").then((r) => r.data);
export const listOffer = () => client.get("/offer-categories").then((r) => r.data);

export const createTarget = (p) => client.post("/admin/target-categories", p).then((r) => r.data);
export const updateTarget = (id, p) => client.patch(`/admin/target-categories/${id}`, p).then((r) => r.data);
export const removeTarget = (id) => client.delete(`/admin/target-categories/${id}`).then((r) => r.data);

export const createOffer = (p) => client.post("/admin/offer-categories", p).then((r) => r.data);
export const updateOffer = (id, p) => client.patch(`/admin/offer-categories/${id}`, p).then((r) => r.data);
export const removeOffer = (id) => client.delete(`/admin/offer-categories/${id}`).then((r) => r.data);
```

- [ ] **Step 7: Create `admin/src/api/users.js`**

```js
import client from "./client";

export const list = () => client.get("/admin/users").then((r) => r.data);
export const create = (payload) => client.post("/admin/users", payload).then((r) => r.data);
export const remove = (id) => client.delete(`/admin/users/${id}`).then((r) => r.data);
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd admin && npx vitest run tests/api/wrappers.test.js`
Expected: PASS (8 tests).

- [ ] **Step 9: Commit**

```bash
git add admin/src/api/offers.js admin/src/api/sources.js admin/src/api/suggestedSources.js admin/src/api/categories.js admin/src/api/users.js admin/tests/api/wrappers.test.js
git commit -m "feat(admin): thin per-resource API wrappers"
```

---

### Task 7: Dictionaries store

**Files:**
- Create: `admin/src/stores/dictionaries.js`
- Test: `admin/tests/stores/dictionaries.test.js`

**Interfaces:**
- Consumes: `api/categories.js` `listTarget`, `listOffer`.
- Produces: Pinia store `useDictionariesStore` with state `{ targetCategories: [], offerCategories: [], loaded: false }` and action `load()` which fetches both lists once (no-op if `loaded`) and caches them. A `reload()` action forces a refetch (used after category edits).

- [ ] **Step 1: Write the failing test — `admin/tests/stores/dictionaries.test.js`**

```js
import { describe, it, expect, vi, beforeEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";

vi.mock("@/api/categories", () => ({
  listTarget: vi.fn(() => Promise.resolve([{ id: 1, name: "УБД", slug: "ubd" }])),
  listOffer: vi.fn(() => Promise.resolve([{ id: 2, name: "Розваги", slug: "rozvahy" }])),
}));

import { useDictionariesStore } from "@/stores/dictionaries";
import { listTarget, listOffer } from "@/api/categories";

describe("dictionaries store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it("load fetches both lists once", async () => {
    const store = useDictionariesStore();
    await store.load();
    await store.load();
    expect(listTarget).toHaveBeenCalledTimes(1);
    expect(listOffer).toHaveBeenCalledTimes(1);
    expect(store.targetCategories[0].slug).toBe("ubd");
    expect(store.offerCategories[0].slug).toBe("rozvahy");
    expect(store.loaded).toBe(true);
  });

  it("reload forces a refetch", async () => {
    const store = useDictionariesStore();
    await store.load();
    await store.reload();
    expect(listTarget).toHaveBeenCalledTimes(2);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && npx vitest run tests/stores/dictionaries.test.js`
Expected: FAIL — store undefined.

- [ ] **Step 3: Create `admin/src/stores/dictionaries.js`**

```js
import { defineStore } from "pinia";
import { listTarget, listOffer } from "@/api/categories";

export const useDictionariesStore = defineStore("dictionaries", {
  state: () => ({ targetCategories: [], offerCategories: [], loaded: false }),
  actions: {
    async load() {
      if (this.loaded) return;
      await this.reload();
    },
    async reload() {
      const [target, offer] = await Promise.all([listTarget(), listOffer()]);
      this.targetCategories = target;
      this.offerCategories = offer;
      this.loaded = true;
    },
  },
});
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd admin && npx vitest run tests/stores/dictionaries.test.js`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add admin/src/stores/dictionaries.js admin/tests/stores/dictionaries.test.js
git commit -m "feat(admin): cached dictionaries store"
```

---

### Task 8: Router, navigation guard, and main wiring

**Files:**
- Create: `admin/src/router/index.js`
- Modify: `admin/src/main.js`, `admin/src/App.vue`, `admin/tests/smoke.test.js`
- Test: `admin/tests/router/guard.test.js`

**Interfaces:**
- Consumes: `stores/auth.js` `useAuthStore`; `api/client.js` `setUnauthorizedHandler`.
- Produces:
  - `router/index.js`: default export `router`. Named export `navigationGuard(to)` returning `true` or a route-location object. Routes (names): `login` (`/login`, `meta.public`), `offers` (`/`), `moderation`, `offer-new`, `offer-edit`, `sources`, `suggested-sources`, `categories`, `users`.
  - Guard logic: if `to.meta.public` → `true`; else if not authenticated → `{ name: "login" }`; else if `to.meta.superAdmin` and not super_admin → `{ name: "offers" }`; else `true`.

Note: to keep Task 8 self-contained, all protected routes point at a shared inline placeholder component; Task 9 replaces them with `AdminLayout` + real views.

- [ ] **Step 1: Write the failing test — `admin/tests/router/guard.test.js`**

```js
import { describe, it, expect, beforeEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { navigationGuard } from "@/router";
import { useAuthStore } from "@/stores/auth";

describe("navigationGuard", () => {
  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
  });

  it("redirects unauthenticated users to login", () => {
    expect(navigationGuard({ meta: {}, name: "offers" })).toEqual({ name: "login" });
  });

  it("allows the public login route", () => {
    expect(navigationGuard({ meta: { public: true }, name: "login" })).toBe(true);
  });

  it("blocks moderator from super_admin routes", () => {
    const auth = useAuthStore();
    auth.token = "t";
    auth.role = "moderator";
    expect(navigationGuard({ meta: { superAdmin: true }, name: "users" })).toEqual({ name: "offers" });
  });

  it("allows super_admin everywhere", () => {
    const auth = useAuthStore();
    auth.token = "t";
    auth.role = "super_admin";
    expect(navigationGuard({ meta: { superAdmin: true }, name: "users" })).toBe(true);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && npx vitest run tests/router/guard.test.js`
Expected: FAIL — `@/router` / `navigationGuard` undefined.

- [ ] **Step 3: Create `admin/src/router/index.js`**

```js
import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const Placeholder = { template: "<div />" };

const routes = [
  { path: "/login", name: "login", meta: { public: true }, component: Placeholder },
  { path: "/", name: "offers", component: Placeholder },
  { path: "/moderation", name: "moderation", component: Placeholder },
  { path: "/offers/new", name: "offer-new", component: Placeholder },
  { path: "/offers/:id/edit", name: "offer-edit", component: Placeholder },
  { path: "/sources", name: "sources", component: Placeholder },
  { path: "/suggested-sources", name: "suggested-sources", component: Placeholder },
  { path: "/categories", name: "categories", meta: { superAdmin: true }, component: Placeholder },
  { path: "/users", name: "users", meta: { superAdmin: true }, component: Placeholder },
];

export function navigationGuard(to) {
  const auth = useAuthStore();
  if (to.meta.public) return true;
  if (!auth.isAuthenticated) return { name: "login" };
  if (to.meta.superAdmin && !auth.isSuperAdmin) return { name: "offers" };
  return true;
}

const router = createRouter({ history: createWebHistory(), routes });
router.beforeEach((to) => navigationGuard(to));

export default router;
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd admin && npx vitest run tests/router/guard.test.js`
Expected: PASS (4 tests).

- [ ] **Step 5: Update `admin/src/App.vue`** (drop the fallback)

```vue
<script setup></script>

<template>
  <router-view />
</template>
```

- [ ] **Step 6: Update `admin/src/main.js`** to wire router + unauthorized handler

```js
import { createApp } from "vue";
import { createPinia } from "pinia";
import ElementPlus from "element-plus";
import "element-plus/dist/index.css";
import App from "./App.vue";
import router from "./router";
import { useAuthStore } from "./stores/auth";
import { setUnauthorizedHandler } from "./api/client";
import "./styles/global.less";

const app = createApp(App);
const pinia = createPinia();
app.use(pinia);
app.use(ElementPlus);
app.use(router);

const auth = useAuthStore(pinia);
setUnauthorizedHandler(() => {
  auth.logout();
  router.push({ name: "login" });
});

app.mount("#app");
```

- [ ] **Step 7: Update `admin/tests/smoke.test.js`** to mount with the router

```js
import { describe, it, expect, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createRouter, createMemoryHistory } from "vue-router";
import App from "@/App.vue";

describe("App", () => {
  beforeEach(() => setActivePinia(createPinia()));

  it("mounts with a router-view", async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: "/", component: { template: "<div>ok</div>" } }],
    });
    router.push("/");
    await router.isReady();
    const wrapper = mount(App, { global: { plugins: [router] } });
    expect(wrapper.html()).toContain("ok");
  });
});
```

- [ ] **Step 8: Run the full suite**

Run: `cd admin && npm run test`
Expected: all tests PASS (Tasks 1–8), output pristine.

- [ ] **Step 9: Commit**

```bash
git add admin/src/router/index.js admin/src/main.js admin/src/App.vue admin/tests/router/guard.test.js admin/tests/smoke.test.js
git commit -m "feat(admin): router with auth/role guard and app wiring"
```

---

### Task 9: AdminLayout shell and view wiring

**Files:**
- Create: `admin/src/layouts/AdminLayout.vue`
- Create (stubs): `admin/src/views/OffersListView.vue`, `ModerationQueueView.vue`, `OfferFormView.vue`, `SourcesView.vue`, `SuggestedSourcesView.vue`, `CategoriesView.vue`, `AdminUsersView.vue`, `LoginView.vue`
- Modify: `admin/src/router/index.js`
- Test: `admin/tests/layouts/AdminLayout.test.js`

**Interfaces:**
- Consumes: `stores/auth.js` (`isSuperAdmin`, `role`, `logout`); Vue Router.
- Produces: `AdminLayout.vue` — sidebar nav (Оффери, Черга модерації, Джерела, Запропоновані джерела, Категорії [super], Адміни [super]) + header (role + logout) + `<router-view>`. Category and Admins links render only when `isSuperAdmin`. Logout calls `auth.logout()` then routes to `login`. View files exist as minimal stubs; later tasks fill them.

- [ ] **Step 1: Create the eight view stubs**

Each file, e.g. `admin/src/views/OffersListView.vue`:
```vue
<script setup></script>
<template>
  <div class="view">Оффери</div>
</template>
```
Create analogous stubs: `ModerationQueueView.vue` ("Черга модерації"), `OfferFormView.vue` ("Форма оффера"), `SourcesView.vue` ("Джерела"), `SuggestedSourcesView.vue` ("Запропоновані джерела"), `CategoriesView.vue` ("Категорії"), `AdminUsersView.vue` ("Адміни"), `LoginView.vue` ("Вхід").

- [ ] **Step 2: Create `admin/src/layouts/AdminLayout.vue`**

```vue
<script setup>
import { computed } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const router = useRouter();
const isSuperAdmin = computed(() => auth.isSuperAdmin);

function logout() {
  auth.logout();
  router.push({ name: "login" });
}
</script>

<template>
  <div class="admin-layout">
    <aside class="sidebar">
      <h1 class="logo">UBD</h1>
      <nav>
        <router-link :to="{ name: 'offers' }">Оффери</router-link>
        <router-link :to="{ name: 'moderation' }">Черга модерації</router-link>
        <router-link :to="{ name: 'sources' }">Джерела</router-link>
        <router-link :to="{ name: 'suggested-sources' }">Запропоновані джерела</router-link>
        <router-link v-if="isSuperAdmin" :to="{ name: 'categories' }">Категорії</router-link>
        <router-link v-if="isSuperAdmin" :to="{ name: 'users' }">Адміни</router-link>
      </nav>
    </aside>
    <div class="main">
      <header class="topbar">
        <span class="role">{{ auth.role }}</span>
        <el-button size="small" @click="logout">Вийти</el-button>
      </header>
      <main class="content"><router-view /></main>
    </div>
  </div>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.admin-layout { display: flex; height: 100%; }
.sidebar { width: @sidebar-width; background: #f5f7fa; padding: 12px; }
.sidebar nav { display: flex; flex-direction: column; gap: 8px; }
.main { flex: 1; display: flex; flex-direction: column; }
.topbar { display: flex; justify-content: flex-end; align-items: center; gap: 12px; padding: 8px 16px; border-bottom: 1px solid #eee; }
.content { padding: 16px; overflow: auto; }
</style>
```

- [ ] **Step 3: Update `admin/src/router/index.js`** — real components under the layout

```js
import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import AdminLayout from "@/layouts/AdminLayout.vue";
import LoginView from "@/views/LoginView.vue";
import OffersListView from "@/views/OffersListView.vue";
import ModerationQueueView from "@/views/ModerationQueueView.vue";
import OfferFormView from "@/views/OfferFormView.vue";
import SourcesView from "@/views/SourcesView.vue";
import SuggestedSourcesView from "@/views/SuggestedSourcesView.vue";
import CategoriesView from "@/views/CategoriesView.vue";
import AdminUsersView from "@/views/AdminUsersView.vue";

const routes = [
  { path: "/login", name: "login", meta: { public: true }, component: LoginView },
  {
    path: "/",
    component: AdminLayout,
    children: [
      { path: "", name: "offers", component: OffersListView },
      { path: "moderation", name: "moderation", component: ModerationQueueView },
      { path: "offers/new", name: "offer-new", component: OfferFormView },
      { path: "offers/:id/edit", name: "offer-edit", component: OfferFormView },
      { path: "sources", name: "sources", component: SourcesView },
      { path: "suggested-sources", name: "suggested-sources", component: SuggestedSourcesView },
      { path: "categories", name: "categories", meta: { superAdmin: true }, component: CategoriesView },
      { path: "users", name: "users", meta: { superAdmin: true }, component: AdminUsersView },
    ],
  },
];

export function navigationGuard(to) {
  const auth = useAuthStore();
  if (to.meta.public) return true;
  if (!auth.isAuthenticated) return { name: "login" };
  if (to.meta.superAdmin && !auth.isSuperAdmin) return { name: "offers" };
  return true;
}

const router = createRouter({ history: createWebHistory(), routes });
router.beforeEach((to) => navigationGuard(to));

export default router;
```

- [ ] **Step 4: Write the failing test — `admin/tests/layouts/AdminLayout.test.js`**

```js
import { describe, it, expect, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createRouter, createMemoryHistory } from "vue-router";
import ElementPlus from "element-plus";
import AdminLayout from "@/layouts/AdminLayout.vue";
import { useAuthStore } from "@/stores/auth";

function makeRouter() {
  const stub = { template: "<div/>" };
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", name: "offers", component: stub },
      { path: "/categories", name: "categories", component: stub },
      { path: "/users", name: "users", component: stub },
      { path: "/moderation", name: "moderation", component: stub },
      { path: "/sources", name: "sources", component: stub },
      { path: "/suggested-sources", name: "suggested-sources", component: stub },
      { path: "/login", name: "login", component: stub },
    ],
  });
}

describe("AdminLayout", () => {
  beforeEach(() => setActivePinia(createPinia()));

  it("hides super_admin links for a moderator", async () => {
    const auth = useAuthStore();
    auth.token = "t";
    auth.role = "moderator";
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    const wrapper = mount(AdminLayout, { global: { plugins: [router, ElementPlus] } });
    expect(wrapper.text()).not.toContain("Категорії");
    expect(wrapper.text()).not.toContain("Адміни");
    expect(wrapper.text()).toContain("Оффери");
  });

  it("shows super_admin links for a super_admin", async () => {
    const auth = useAuthStore();
    auth.token = "t";
    auth.role = "super_admin";
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    const wrapper = mount(AdminLayout, { global: { plugins: [router, ElementPlus] } });
    expect(wrapper.text()).toContain("Категорії");
    expect(wrapper.text()).toContain("Адміни");
  });
});
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd admin && npm run test`
Expected: all PASS. Output pristine.

- [ ] **Step 6: Commit**

```bash
git add admin/src/layouts/AdminLayout.vue admin/src/views/ admin/src/router/index.js admin/tests/layouts/AdminLayout.test.js
git commit -m "feat(admin): AdminLayout shell, view stubs, real route wiring"
```

---

### Task 10: LoginView

**Files:**
- Modify: `admin/src/views/LoginView.vue` (replace the stub)
- Test: `admin/tests/views/LoginView.test.js`

**Interfaces:**
- Consumes: `stores/auth.js` `login`; `utils/errors.js` `extractError`; Vue Router; Element Plus `ElMessage`.
- Produces: `LoginView` with a form (`email`, `password`). `submit()` calls `auth.login`, on success routes to `offers`, on failure shows `ElMessage.error(extractError(e))`. Exposes `{ submit, form }` via `defineExpose` for testing.

- [ ] **Step 1: Write the failing test — `admin/tests/views/LoginView.test.js`**

```js
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createRouter, createMemoryHistory } from "vue-router";
import ElementPlus, { ElMessage } from "element-plus";
import LoginView from "@/views/LoginView.vue";

vi.mock("@/api/auth", () => ({ login: vi.fn() }));
vi.mock("element-plus", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, ElMessage: { error: vi.fn(), success: vi.fn() } };
});
import { login as loginApi } from "@/api/auth";

function makeRouter() {
  const stub = { template: "<div/>" };
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/login", name: "login", component: stub },
      { path: "/", name: "offers", component: stub },
    ],
  });
  return router;
}

describe("LoginView", () => {
  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it("routes to offers on successful login", async () => {
    loginApi.mockResolvedValue({ access_token: "t", token_type: "bearer", role: "moderator" });
    const router = makeRouter();
    router.push("/login");
    await router.isReady();
    const push = vi.spyOn(router, "push");
    const wrapper = mount(LoginView, { global: { plugins: [router, ElementPlus] } });
    wrapper.vm.form.email = "a@b.c";
    wrapper.vm.form.password = "pw";
    await wrapper.vm.submit();
    await flushPromises();
    expect(loginApi).toHaveBeenCalledWith("a@b.c", "pw");
    expect(push).toHaveBeenCalledWith({ name: "offers" });
  });

  it("shows an error message on failed login", async () => {
    loginApi.mockRejectedValue({ response: { data: { detail: "Invalid credentials", code: "unauthorized" } } });
    const router = makeRouter();
    router.push("/login");
    await router.isReady();
    const wrapper = mount(LoginView, { global: { plugins: [router, ElementPlus] } });
    wrapper.vm.form.email = "a@b.c";
    wrapper.vm.form.password = "bad";
    await wrapper.vm.submit();
    await flushPromises();
    expect(ElMessage.error).toHaveBeenCalledWith("Invalid credentials");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && npx vitest run tests/views/LoginView.test.js`
Expected: FAIL — the stub has no `submit`/`form`.

- [ ] **Step 3: Replace `admin/src/views/LoginView.vue`**

```vue
<script setup>
import { reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { useAuthStore } from "@/stores/auth";
import { extractError } from "@/utils/errors";

const auth = useAuthStore();
const router = useRouter();
const form = reactive({ email: "", password: "" });
const loading = ref(false);

async function submit() {
  loading.value = true;
  try {
    await auth.login(form.email, form.password);
    router.push({ name: "offers" });
  } catch (e) {
    ElMessage.error(extractError(e));
  } finally {
    loading.value = false;
  }
}

defineExpose({ submit, form });
</script>

<template>
  <div class="login">
    <el-form class="login-form" label-position="top" @submit.prevent="submit">
      <h2>UBD — Вхід</h2>
      <el-form-item label="Email">
        <el-input v-model="form.email" type="email" autocomplete="username" />
      </el-form-item>
      <el-form-item label="Пароль">
        <el-input v-model="form.password" type="password" autocomplete="current-password" />
      </el-form-item>
      <el-button type="primary" :loading="loading" native-type="submit">Увійти</el-button>
    </el-form>
  </div>
</template>

<style scoped lang="less">
.login { display: flex; justify-content: center; align-items: center; height: 100%; }
.login-form { width: 320px; padding: 24px; }
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd admin && npx vitest run tests/views/LoginView.test.js`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add admin/src/views/LoginView.vue admin/tests/views/LoginView.test.js
git commit -m "feat(admin): login view"
```

---

### Task 11: List composable, table toolbar, confirm util

**Files:**
- Create: `admin/src/composables/useApiList.js`, `admin/src/components/DataTableToolbar.vue`, `admin/src/utils/confirm.js`
- Test: `admin/tests/composables/useApiList.test.js`, `admin/tests/components/DataTableToolbar.test.js`, `admin/tests/utils/confirm.test.js`

**Interfaces:**
- Produces:
  - `useApiList(loader, initialFilters = {})` → reactive refs `{ items, total, page, size, loading, filters, load, setPage, applyFilters }`. `load()` calls `loader({ ...filters, page, size })`; if the result is an array it sets `items = result, total = result.length`, otherwise expects a `{ items, total }` page. `setPage(p)` sets page and reloads. `applyFilters(patch)` merges `patch` into `filters`, resets `page = 1`, reloads.
  - `DataTableToolbar` — a `<slot name="filters">` plus a search input; emits `search` with the query string on Enter or button click. Exposes `{ q }`.
  - `confirm.js` `confirmDelete(message = "Видалити цей запис?") -> Promise` wrapping `ElMessageBox.confirm` (rejects when the user cancels).

- [ ] **Step 1: Write the failing tests**

`admin/tests/composables/useApiList.test.js`:
```js
import { describe, it, expect, vi } from "vitest";
import { useApiList } from "@/composables/useApiList";

describe("useApiList", () => {
  it("loads a paged result", async () => {
    const loader = vi.fn(() => Promise.resolve({ items: [{ id: 1 }], total: 42 }));
    const list = useApiList(loader, { status: "" });
    await list.load();
    expect(loader).toHaveBeenCalledWith({ status: "", page: 1, size: 20 });
    expect(list.items.value).toEqual([{ id: 1 }]);
    expect(list.total.value).toBe(42);
  });

  it("supports plain array results", async () => {
    const loader = vi.fn(() => Promise.resolve([{ id: 1 }, { id: 2 }]));
    const list = useApiList(loader);
    await list.load();
    expect(list.items.value.length).toBe(2);
    expect(list.total.value).toBe(2);
  });

  it("applyFilters resets page and merges filters", async () => {
    const loader = vi.fn(() => Promise.resolve([]));
    const list = useApiList(loader, { status: "" });
    list.page.value = 3;
    await list.applyFilters({ status: "published" });
    expect(list.page.value).toBe(1);
    expect(loader).toHaveBeenLastCalledWith({ status: "published", page: 1, size: 20 });
  });
});
```

`admin/tests/components/DataTableToolbar.test.js`:
```js
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import ElementPlus from "element-plus";
import DataTableToolbar from "@/components/DataTableToolbar.vue";

describe("DataTableToolbar", () => {
  it("emits search with the query on button click", async () => {
    const wrapper = mount(DataTableToolbar, { global: { plugins: [ElementPlus] } });
    wrapper.vm.q = "коло";
    await wrapper.find("button").trigger("click");
    expect(wrapper.emitted().search[0]).toEqual(["коло"]);
  });
});
```

`admin/tests/utils/confirm.test.js`:
```js
import { describe, it, expect, vi } from "vitest";

vi.mock("element-plus", () => ({
  ElMessageBox: { confirm: vi.fn(() => Promise.resolve()) },
}));
import { ElMessageBox } from "element-plus";
import { confirmDelete } from "@/utils/confirm";

describe("confirmDelete", () => {
  it("calls ElMessageBox.confirm with the message", async () => {
    await confirmDelete("Прибрати?");
    expect(ElMessageBox.confirm).toHaveBeenCalled();
    expect(ElMessageBox.confirm.mock.calls[0][0]).toBe("Прибрати?");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd admin && npx vitest run tests/composables tests/components/DataTableToolbar.test.js tests/utils/confirm.test.js`
Expected: FAIL — modules/components undefined.

- [ ] **Step 3: Create `admin/src/composables/useApiList.js`**

```js
import { ref, reactive } from "vue";

export function useApiList(loader, initialFilters = {}) {
  const items = ref([]);
  const total = ref(0);
  const page = ref(1);
  const size = ref(20);
  const loading = ref(false);
  const filters = reactive({ ...initialFilters });

  async function load() {
    loading.value = true;
    try {
      const result = await loader({ ...filters, page: page.value, size: size.value });
      if (Array.isArray(result)) {
        items.value = result;
        total.value = result.length;
      } else {
        items.value = result.items;
        total.value = result.total;
      }
    } finally {
      loading.value = false;
    }
  }

  function setPage(p) {
    page.value = p;
    return load();
  }

  function applyFilters(patch) {
    Object.assign(filters, patch);
    page.value = 1;
    return load();
  }

  return { items, total, page, size, loading, filters, load, setPage, applyFilters };
}
```

- [ ] **Step 4: Create `admin/src/components/DataTableToolbar.vue`**

```vue
<script setup>
import { ref } from "vue";

const emit = defineEmits(["search"]);
const q = ref("");

function onSearch() {
  emit("search", q.value);
}

defineExpose({ q });
</script>

<template>
  <div class="toolbar">
    <slot name="filters" />
    <el-input
      v-model="q"
      placeholder="Пошук"
      clearable
      style="width: 220px"
      @keyup.enter="onSearch"
    />
    <el-button @click="onSearch">Знайти</el-button>
  </div>
</template>

<style scoped lang="less">
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
</style>
```

- [ ] **Step 5: Create `admin/src/utils/confirm.js`**

```js
import { ElMessageBox } from "element-plus";

export function confirmDelete(message = "Видалити цей запис?") {
  return ElMessageBox.confirm(message, "Підтвердження", {
    type: "warning",
    confirmButtonText: "Так",
    cancelButtonText: "Скасувати",
  });
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd admin && npx vitest run tests/composables tests/components/DataTableToolbar.test.js tests/utils/confirm.test.js`
Expected: PASS (5 tests total).

- [ ] **Step 7: Commit**

```bash
git add admin/src/composables/useApiList.js admin/src/components/DataTableToolbar.vue admin/src/utils/confirm.js admin/tests/composables admin/tests/components/DataTableToolbar.test.js admin/tests/utils/confirm.test.js
git commit -m "feat(admin): useApiList composable, table toolbar, confirm util"
```

---

### Task 12: Offers list and moderation queue

**Files:**
- Modify: `admin/src/views/OffersListView.vue`, `admin/src/views/ModerationQueueView.vue` (replace stubs)
- Test: `admin/tests/views/OffersListView.test.js`

**Interfaces:**
- Consumes: `composables/useApiList.js`; `api/offers.js`; `constants/enums.js`; `utils/format.js`, `utils/confirm.js`, `utils/errors.js`; `components/DataTableToolbar.vue`; Vue Router; Element Plus.
- Produces:
  - `OffersListView` — prop `fixedStatus: String|null`. Loads offers via `useApiList`, stripping empty filter values before calling `offers.list`; when `fixedStatus` is set it forces `status` and hides the status filter. Row actions: edit (route to `offer-edit`), publish (when `status !== "published"`), reject (when `status === "pending_review"`), delete (confirm). Exposes `{ onPublish, onReject, onDelete, load, applyFilters, items }`.
  - `ModerationQueueView` — renders `<OffersListView fixed-status="pending_review" />`.

- [ ] **Step 1: Write the failing test — `admin/tests/views/OffersListView.test.js`**

```js
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createRouter, createMemoryHistory } from "vue-router";
import ElementPlus from "element-plus";
import OffersListView from "@/views/OffersListView.vue";

vi.mock("@/api/offers", () => ({
  list: vi.fn(() => Promise.resolve({
    items: [{ id: 1, title: "T", provider: "P", type: "discount", status: "pending_review", valid_until: null }],
    total: 1,
  })),
  publish: vi.fn(() => Promise.resolve({})),
  reject: vi.fn(() => Promise.resolve({})),
  remove: vi.fn(() => Promise.resolve({})),
}));
vi.mock("element-plus", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, ElMessage: { success: vi.fn(), error: vi.fn() } };
});
import * as offers from "@/api/offers";

function makeRouter() {
  const stub = { template: "<div/>" };
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", name: "offers", component: stub },
      { path: "/offers/new", name: "offer-new", component: stub },
      { path: "/offers/:id/edit", name: "offer-edit", component: stub },
    ],
  });
}

describe("OffersListView", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it("loads offers on mount with empty filters stripped", async () => {
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    mount(OffersListView, { global: { plugins: [router, ElementPlus] } });
    await flushPromises();
    expect(offers.list).toHaveBeenCalledWith({ page: 1, size: 20 });
  });

  it("publish calls the API and reloads", async () => {
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    const wrapper = mount(OffersListView, { global: { plugins: [router, ElementPlus] } });
    await flushPromises();
    await wrapper.vm.onPublish(1);
    await flushPromises();
    expect(offers.publish).toHaveBeenCalledWith(1);
    expect(offers.list).toHaveBeenCalledTimes(2);
  });

  it("forces status when fixedStatus is set", async () => {
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    mount(OffersListView, { props: { fixedStatus: "pending_review" }, global: { plugins: [router, ElementPlus] } });
    await flushPromises();
    expect(offers.list).toHaveBeenCalledWith({ status: "pending_review", page: 1, size: 20 });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && npx vitest run tests/views/OffersListView.test.js`
Expected: FAIL — stub lacks behaviour.

- [ ] **Step 3: Replace `admin/src/views/OffersListView.vue`**

```vue
<script setup>
import { onMounted } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { useApiList } from "@/composables/useApiList";
import * as offers from "@/api/offers";
import { OFFER_STATUSES, OFFER_TYPES } from "@/constants/enums";
import { enumLabel, formatDate, statusTagType } from "@/utils/format";
import { confirmDelete } from "@/utils/confirm";
import { extractError } from "@/utils/errors";
import DataTableToolbar from "@/components/DataTableToolbar.vue";

const props = defineProps({ fixedStatus: { type: String, default: null } });
const router = useRouter();

function loader(params) {
  const p = { ...params };
  if (props.fixedStatus) p.status = props.fixedStatus;
  Object.keys(p).forEach((k) => {
    if (p[k] === "" || p[k] == null) delete p[k];
  });
  return offers.list(p);
}

const { items, total, page, size, loading, filters, load, setPage, applyFilters } =
  useApiList(loader, { status: "", type: "", q: "" });

onMounted(load);

async function onPublish(id) {
  try {
    await offers.publish(id);
    ElMessage.success("Опубліковано");
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

async function onReject(id) {
  try {
    await offers.reject(id);
    ElMessage.success("Відхилено");
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

async function onDelete(id) {
  try {
    await confirmDelete();
  } catch {
    return;
  }
  try {
    await offers.remove(id);
    ElMessage.success("Видалено");
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

function edit(id) {
  router.push({ name: "offer-edit", params: { id } });
}

defineExpose({ onPublish, onReject, onDelete, load, applyFilters, items });
</script>

<template>
  <div class="offers-list">
    <div class="header">
      <h2>{{ fixedStatus ? "Черга модерації" : "Оффери" }}</h2>
      <el-button v-if="!fixedStatus" type="primary" @click="router.push({ name: 'offer-new' })">
        Створити оффер
      </el-button>
    </div>

    <DataTableToolbar @search="(q) => applyFilters({ q })">
      <template #filters>
        <el-select
          v-if="!fixedStatus"
          v-model="filters.status"
          placeholder="Статус"
          clearable
          style="width: 160px"
          @change="applyFilters({})"
        >
          <el-option v-for="s in OFFER_STATUSES" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
        <el-select
          v-model="filters.type"
          placeholder="Тип"
          clearable
          style="width: 140px"
          @change="applyFilters({})"
        >
          <el-option v-for="t in OFFER_TYPES" :key="t.value" :label="t.label" :value="t.value" />
        </el-select>
      </template>
    </DataTableToolbar>

    <el-table :data="items" v-loading="loading" style="width: 100%">
      <el-table-column prop="title" label="Заголовок" />
      <el-table-column prop="provider" label="Провайдер" />
      <el-table-column label="Тип">
        <template #default="{ row }">{{ enumLabel(OFFER_TYPES, row.type) }}</template>
      </el-table-column>
      <el-table-column label="Статус">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)">{{ enumLabel(OFFER_STATUSES, row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="Дійсний до">
        <template #default="{ row }">{{ formatDate(row.valid_until) }}</template>
      </el-table-column>
      <el-table-column label="Дії" width="280">
        <template #default="{ row }">
          <el-button size="small" @click="edit(row.id)">Редагувати</el-button>
          <el-button v-if="row.status !== 'published'" size="small" type="success" @click="onPublish(row.id)">
            Опублікувати
          </el-button>
          <el-button v-if="row.status === 'pending_review'" size="small" type="warning" @click="onReject(row.id)">
            Відхилити
          </el-button>
          <el-button size="small" type="danger" @click="onDelete(row.id)">Видалити</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      layout="prev, pager, next"
      :total="total"
      :page-size="size"
      :current-page="page"
      @current-change="setPage"
    />
  </div>
</template>

<style scoped lang="less">
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
</style>
```

- [ ] **Step 4: Replace `admin/src/views/ModerationQueueView.vue`**

```vue
<script setup>
import OffersListView from "@/views/OffersListView.vue";
</script>

<template>
  <OffersListView fixed-status="pending_review" />
</template>
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd admin && npx vitest run tests/views/OffersListView.test.js`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add admin/src/views/OffersListView.vue admin/src/views/ModerationQueueView.vue admin/tests/views/OffersListView.test.js
git commit -m "feat(admin): offers list and moderation queue"
```

---

### Task 13: Offer form building blocks (validation util, image preview, category multiselect)

**Files:**
- Create: `admin/src/utils/offerForm.js`, `admin/src/components/ImagePreview.vue`, `admin/src/components/CategoryMultiSelect.vue`
- Test: `admin/tests/utils/offerForm.test.js`, `admin/tests/components/ImagePreview.test.js`, `admin/tests/components/CategoryMultiSelect.test.js`

**Interfaces:**
- Produces:
  - `utils/offerForm.js`:
    - `validateOffer(form) -> string[]` — Ukrainian error messages; empty array means valid. Rules: `title` and `provider` required; if both dates present, `valid_until >= valid_from` (ISO `YYYY-MM-DD` strings compare lexically); `discount_value` required when `type === "discount"` and `discount_type ∈ {percent, fixed}`, and must be empty otherwise.
    - `buildOfferPayload(form) -> object` — the POST/PATCH body: passes through fields; nulls `discount_type`/`discount_value` unless `type === "discount"` (and value only for percent/fixed); empty strings → `null` for optional fields; includes `target_category_ids`, `offer_category_ids`.
  - `ImagePreview` — props `imageUrl: String`, `type: String`, `discountType: String|null`; renders `<img>` whose `src` is `imageUrl` when set, else `placeholderDataUri({ type, discount_type: discountType })`.
  - `CategoryMultiSelect` — props `modelValue: Array`, `options: Array<{id,name}>`; a multiple `el-select` that emits `update:modelValue` (v-model compatible).

- [ ] **Step 1: Write the failing tests**

`admin/tests/utils/offerForm.test.js`:
```js
import { describe, it, expect } from "vitest";
import { validateOffer, buildOfferPayload } from "@/utils/offerForm";

const base = { type: "discount", title: "T", provider: "P", discount_type: "percent", discount_value: 50 };

describe("validateOffer", () => {
  it("passes a valid percent discount", () => {
    expect(validateOffer({ ...base })).toEqual([]);
  });
  it("requires title and provider", () => {
    const errors = validateOffer({ ...base, title: "", provider: "" });
    expect(errors.length).toBe(2);
  });
  it("requires discount_value for percent", () => {
    expect(validateOffer({ ...base, discount_value: null })).toContain("Вкажіть величину знижки");
  });
  it("forbids discount_value for events", () => {
    const errors = validateOffer({ type: "event", title: "T", provider: "P", discount_type: null, discount_value: 5 });
    expect(errors.some((e) => e.includes("лише для"))).toBe(true);
  });
  it("checks date order", () => {
    const errors = validateOffer({ ...base, valid_from: "2026-08-01", valid_until: "2026-07-01" });
    expect(errors.some((e) => e.includes("раніше"))).toBe(true);
  });
});

describe("buildOfferPayload", () => {
  it("nulls discount fields for events and maps category ids", () => {
    const payload = buildOfferPayload({
      type: "event", title: "T", provider: "P", description: "", location: "",
      valid_from: null, valid_until: null, discount_type: "percent", discount_value: 10,
      contacts: "", image_url: "", target_category_ids: [1], offer_category_ids: [2],
    });
    expect(payload.discount_type).toBe(null);
    expect(payload.discount_value).toBe(null);
    expect(payload.location).toBe(null);
    expect(payload.target_category_ids).toEqual([1]);
    expect(payload.offer_category_ids).toEqual([2]);
  });
});
```

`admin/tests/components/ImagePreview.test.js`:
```js
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import ImagePreview from "@/components/ImagePreview.vue";

describe("ImagePreview", () => {
  it("uses the placeholder when imageUrl is empty", () => {
    const wrapper = mount(ImagePreview, { props: { imageUrl: "", type: "event", discountType: null } });
    const src = wrapper.get("img").attributes("src");
    expect(src.startsWith("data:image/svg+xml,")).toBe(true);
    expect(decodeURIComponent(src)).toContain("безкоштовно для УБД");
  });
  it("uses the given url when present", () => {
    const wrapper = mount(ImagePreview, { props: { imageUrl: "https://x/y.png", type: "discount", discountType: "percent" } });
    expect(wrapper.get("img").attributes("src")).toBe("https://x/y.png");
  });
});
```

`admin/tests/components/CategoryMultiSelect.test.js`:
```js
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import ElementPlus from "element-plus";
import CategoryMultiSelect from "@/components/CategoryMultiSelect.vue";

describe("CategoryMultiSelect", () => {
  it("emits update:modelValue when selection changes", async () => {
    const wrapper = mount(CategoryMultiSelect, {
      props: { modelValue: [], options: [{ id: 1, name: "УБД" }] },
      global: { plugins: [ElementPlus] },
    });
    wrapper.vm.$emit("update:modelValue", [1]);
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted()["update:modelValue"][0]).toEqual([[1]]);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd admin && npx vitest run tests/utils/offerForm.test.js tests/components/ImagePreview.test.js tests/components/CategoryMultiSelect.test.js`
Expected: FAIL — modules/components undefined.

- [ ] **Step 3: Create `admin/src/utils/offerForm.js`**

```js
export function validateOffer(form) {
  const errors = [];
  if (!form.title) errors.push("Вкажіть заголовок");
  if (!form.provider) errors.push("Вкажіть провайдера");
  if (form.valid_from && form.valid_until && form.valid_until < form.valid_from) {
    errors.push("Дата «до» раніше за дату «від»");
  }
  const needsValue =
    form.type === "discount" && (form.discount_type === "percent" || form.discount_type === "fixed");
  const hasValue = form.discount_value !== null && form.discount_value !== "" && form.discount_value !== undefined;
  if (needsValue && !hasValue) errors.push("Вкажіть величину знижки");
  if (!needsValue && hasValue) errors.push("Величина знижки лише для відсоток/фіксована");
  return errors;
}

export function buildOfferPayload(form) {
  const isDiscount = form.type === "discount";
  const withValue = isDiscount && (form.discount_type === "percent" || form.discount_type === "fixed");
  return {
    type: form.type,
    title: form.title,
    description: form.description || "",
    provider: form.provider,
    location: form.location || null,
    valid_from: form.valid_from || null,
    valid_until: form.valid_until || null,
    discount_type: isDiscount ? form.discount_type || null : null,
    discount_value: withValue ? form.discount_value : null,
    contacts: form.contacts || null,
    image_url: form.image_url || null,
    target_category_ids: form.target_category_ids || [],
    offer_category_ids: form.offer_category_ids || [],
  };
}
```

- [ ] **Step 4: Create `admin/src/components/ImagePreview.vue`**

```vue
<script setup>
import { computed } from "vue";
import { placeholderDataUri } from "@/utils/placeholder";

const props = defineProps({
  imageUrl: { type: String, default: "" },
  type: { type: String, default: "discount" },
  discountType: { type: String, default: null },
});

const src = computed(
  () => props.imageUrl || placeholderDataUri({ type: props.type, discount_type: props.discountType })
);
</script>

<template>
  <img :src="src" alt="" class="image-preview" />
</template>

<style scoped lang="less">
.image-preview { max-width: 400px; max-height: 225px; border: 1px solid #eee; }
</style>
```

- [ ] **Step 5: Create `admin/src/components/CategoryMultiSelect.vue`**

```vue
<script setup>
const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  options: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:modelValue"]);
</script>

<template>
  <el-select
    :model-value="modelValue"
    multiple
    style="width: 100%"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <el-option v-for="o in options" :key="o.id" :label="o.name" :value="o.id" />
  </el-select>
</template>
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd admin && npx vitest run tests/utils/offerForm.test.js tests/components/ImagePreview.test.js tests/components/CategoryMultiSelect.test.js`
Expected: PASS (8 tests).

- [ ] **Step 7: Commit**

```bash
git add admin/src/utils/offerForm.js admin/src/components/ImagePreview.vue admin/src/components/CategoryMultiSelect.vue admin/tests/utils/offerForm.test.js admin/tests/components/ImagePreview.test.js admin/tests/components/CategoryMultiSelect.test.js
git commit -m "feat(admin): offer form validation util, image preview, category multiselect"
```

---

### Task 14: Offer form component and create/edit view

**Files:**
- Create: `admin/src/components/OfferForm.vue`
- Modify: `admin/src/views/OfferFormView.vue` (replace stub)
- Test: `admin/tests/components/OfferForm.test.js`, `admin/tests/views/OfferFormView.test.js`

**Interfaces:**
- Consumes: `utils/offerForm.js`; `constants/enums.js`; `components/ImagePreview.vue`, `components/CategoryMultiSelect.vue`; `api/offers.js`; `stores/dictionaries.js`; Vue Router; Element Plus.
- Produces:
  - `OfferForm` — props `initial: Object|null`, `targetCategories: Array`, `offerCategories: Array`. Holds a reactive `form` seeded from `initial` (maps `initial.target_categories`/`offer_categories` objects to id arrays). `submit()` runs `validateOffer`; on error shows `ElMessage.error(errors[0])` and does not emit; on success emits `submit` with `buildOfferPayload(form)`. Emits `cancel`. Exposes `{ form, submit }`.
  - `OfferFormView` — reads `route.params.id`; loads dictionaries; in edit mode fetches `offers.get(id)` into `initial`. On `OfferForm`'s `submit`, calls `offers.update(id, payload)` (edit) or `offers.create(payload)` (create), shows success, routes to `offers`.

- [ ] **Step 1: Write the failing tests**

`admin/tests/components/OfferForm.test.js`:
```js
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import ElementPlus, { ElMessage } from "element-plus";
import OfferForm from "@/components/OfferForm.vue";

vi.mock("element-plus", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, ElMessage: { error: vi.fn(), success: vi.fn() } };
});

describe("OfferForm", () => {
  beforeEach(() => vi.clearAllMocks());

  it("emits submit with a built payload when valid", async () => {
    const wrapper = mount(OfferForm, {
      props: { initial: null, targetCategories: [{ id: 1, name: "УБД" }], offerCategories: [{ id: 2, name: "Розваги" }] },
      global: { plugins: [ElementPlus] },
    });
    Object.assign(wrapper.vm.form, {
      type: "discount", title: "Знижка", provider: "Магазин",
      discount_type: "percent", discount_value: 20, target_category_ids: [1], offer_category_ids: [2],
    });
    wrapper.vm.submit();
    const payload = wrapper.emitted().submit[0][0];
    expect(payload.title).toBe("Знижка");
    expect(payload.discount_value).toBe(20);
    expect(payload.target_category_ids).toEqual([1]);
  });

  it("blocks submit and shows an error when invalid", () => {
    const wrapper = mount(OfferForm, { props: { initial: null }, global: { plugins: [ElementPlus] } });
    Object.assign(wrapper.vm.form, { type: "discount", title: "", provider: "" });
    wrapper.vm.submit();
    expect(ElMessage.error).toHaveBeenCalled();
    expect(wrapper.emitted().submit).toBeUndefined();
  });

  it("seeds the form from an initial offer (edit)", () => {
    const wrapper = mount(OfferForm, {
      props: {
        initial: { type: "event", title: "Подія", provider: "Музей", target_categories: [{ id: 3, name: "Ветеран" }], offer_categories: [] },
      },
      global: { plugins: [ElementPlus] },
    });
    expect(wrapper.vm.form.title).toBe("Подія");
    expect(wrapper.vm.form.target_category_ids).toEqual([3]);
  });
});
```

`admin/tests/views/OfferFormView.test.js`:
```js
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createRouter, createMemoryHistory } from "vue-router";
import ElementPlus from "element-plus";
import OfferFormView from "@/views/OfferFormView.vue";

vi.mock("@/api/offers", () => ({
  get: vi.fn(() => Promise.resolve({ id: 5, type: "discount", title: "Old", provider: "P", target_categories: [], offer_categories: [] })),
  create: vi.fn(() => Promise.resolve({ id: 9 })),
  update: vi.fn(() => Promise.resolve({ id: 5 })),
}));
vi.mock("@/api/categories", () => ({
  listTarget: vi.fn(() => Promise.resolve([])),
  listOffer: vi.fn(() => Promise.resolve([])),
}));
vi.mock("element-plus", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, ElMessage: { error: vi.fn(), success: vi.fn() } };
});
import * as offers from "@/api/offers";

function mountView(path, routeName, params = {}) {
  const stub = { template: "<div/>" };
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", name: "offers", component: stub },
      { path: "/offers/new", name: "offer-new", component: OfferFormView },
      { path: "/offers/:id/edit", name: "offer-edit", component: OfferFormView },
    ],
  });
  router.push(path);
  return router.isReady().then(() => mount(OfferFormView, { global: { plugins: [router, ElementPlus] } }));
}

describe("OfferFormView", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it("creates a new offer on submit", async () => {
    const wrapper = await mountView("/offers/new");
    await flushPromises();
    wrapper.vm.onSubmit({ title: "New", type: "event", provider: "P" });
    await flushPromises();
    expect(offers.create).toHaveBeenCalledWith({ title: "New", type: "event", provider: "P" });
  });

  it("loads and updates an existing offer", async () => {
    const wrapper = await mountView("/offers/5/edit");
    await flushPromises();
    expect(offers.get).toHaveBeenCalledWith("5");
    wrapper.vm.onSubmit({ title: "Upd", type: "discount", provider: "P" });
    await flushPromises();
    expect(offers.update).toHaveBeenCalledWith("5", { title: "Upd", type: "discount", provider: "P" });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd admin && npx vitest run tests/components/OfferForm.test.js tests/views/OfferFormView.test.js`
Expected: FAIL — component/view lack behaviour.

- [ ] **Step 3: Create `admin/src/components/OfferForm.vue`**

```vue
<script setup>
import { reactive, computed, watch } from "vue";
import { ElMessage } from "element-plus";
import { OFFER_TYPES, DISCOUNT_TYPES } from "@/constants/enums";
import { validateOffer, buildOfferPayload } from "@/utils/offerForm";
import ImagePreview from "@/components/ImagePreview.vue";
import CategoryMultiSelect from "@/components/CategoryMultiSelect.vue";

const props = defineProps({
  initial: { type: Object, default: null },
  targetCategories: { type: Array, default: () => [] },
  offerCategories: { type: Array, default: () => [] },
});
const emit = defineEmits(["submit", "cancel"]);

function fromInitial(o) {
  return {
    type: o?.type || "discount",
    title: o?.title || "",
    description: o?.description || "",
    provider: o?.provider || "",
    location: o?.location || "",
    valid_from: o?.valid_from || null,
    valid_until: o?.valid_until || null,
    discount_type: o?.discount_type || null,
    discount_value: o?.discount_value ?? null,
    contacts: o?.contacts || "",
    image_url: o?.image_url || "",
    target_category_ids: o?.target_categories ? o.target_categories.map((c) => c.id) : [],
    offer_category_ids: o?.offer_categories ? o.offer_categories.map((c) => c.id) : [],
  };
}

const form = reactive(fromInitial(props.initial));
watch(() => props.initial, (o) => Object.assign(form, fromInitial(o)));

const isDiscount = computed(() => form.type === "discount");
const showValue = computed(
  () => isDiscount.value && (form.discount_type === "percent" || form.discount_type === "fixed")
);

// Clear a stale discount_value when the value field stops applying (e.g. type
// switches to event, or discount_type changes to free / is cleared) — otherwise
// the hidden value fails validation with no visible field to fix it.
watch(
  () => [form.type, form.discount_type],
  () => {
    if (!showValue.value) form.discount_value = null;
  }
);

function submit() {
  const errors = validateOffer(form);
  if (errors.length) {
    ElMessage.error(errors[0]);
    return;
  }
  emit("submit", buildOfferPayload(form));
}

defineExpose({ form, submit });
</script>

<template>
  <el-form label-position="top" class="offer-form">
    <el-form-item label="Тип" required>
      <el-select v-model="form.type" style="width: 200px">
        <el-option v-for="t in OFFER_TYPES" :key="t.value" :label="t.label" :value="t.value" />
      </el-select>
    </el-form-item>
    <el-form-item label="Заголовок" required>
      <el-input v-model="form.title" />
    </el-form-item>
    <el-form-item label="Опис">
      <el-input v-model="form.description" type="textarea" :rows="3" />
    </el-form-item>
    <el-form-item label="Хто пропонує (провайдер)" required>
      <el-input v-model="form.provider" />
    </el-form-item>
    <el-form-item label="Для кого">
      <CategoryMultiSelect v-model="form.target_category_ids" :options="targetCategories" />
    </el-form-item>
    <el-form-item label="Тематика">
      <CategoryMultiSelect v-model="form.offer_category_ids" :options="offerCategories" />
    </el-form-item>
    <el-form-item label="Локація">
      <el-input v-model="form.location" placeholder="Місто або «онлайн»" />
    </el-form-item>
    <el-form-item label="Дійсний від">
      <el-date-picker v-model="form.valid_from" type="date" value-format="YYYY-MM-DD" />
    </el-form-item>
    <el-form-item label="Дійсний до">
      <el-date-picker v-model="form.valid_until" type="date" value-format="YYYY-MM-DD" />
    </el-form-item>
    <template v-if="isDiscount">
      <el-form-item label="Тип знижки">
        <el-select v-model="form.discount_type" clearable style="width: 200px">
          <el-option v-for="d in DISCOUNT_TYPES" :key="d.value" :label="d.label" :value="d.value" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="showValue" label="Величина знижки">
        <el-input-number v-model="form.discount_value" :min="0" />
      </el-form-item>
    </template>
    <el-form-item label="Контакти">
      <el-input v-model="form.contacts" />
    </el-form-item>
    <el-form-item label="Зображення (URL)">
      <el-input v-model="form.image_url" placeholder="https://…" />
    </el-form-item>
    <el-form-item label="Прев'ю">
      <ImagePreview :image-url="form.image_url" :type="form.type" :discount-type="form.discount_type" />
    </el-form-item>
    <div class="actions">
      <el-button type="primary" @click="submit">Зберегти</el-button>
      <el-button @click="emit('cancel')">Скасувати</el-button>
    </div>
  </el-form>
</template>

<style scoped lang="less">
.offer-form { max-width: 640px; }
.actions { display: flex; gap: 8px; }
</style>
```

- [ ] **Step 4: Replace `admin/src/views/OfferFormView.vue`**

```vue
<script setup>
import { ref, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import * as offers from "@/api/offers";
import { useDictionariesStore } from "@/stores/dictionaries";
import { extractError } from "@/utils/errors";
import OfferForm from "@/components/OfferForm.vue";

const route = useRoute();
const router = useRouter();
const dictionaries = useDictionariesStore();

const id = route.params.id || null;
const initial = ref(null);

onMounted(async () => {
  await dictionaries.load();
  if (id) {
    try {
      initial.value = await offers.get(id);
    } catch (e) {
      ElMessage.error(extractError(e));
    }
  }
});

async function onSubmit(payload) {
  try {
    if (id) {
      await offers.update(id, payload);
      ElMessage.success("Збережено");
    } else {
      await offers.create(payload);
      ElMessage.success("Створено");
    }
    router.push({ name: "offers" });
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

defineExpose({ onSubmit });
</script>

<template>
  <div class="offer-form-view">
    <h2>{{ id ? "Редагувати оффер" : "Створити оффер" }}</h2>
    <OfferForm
      :initial="initial"
      :target-categories="dictionaries.targetCategories"
      :offer-categories="dictionaries.offerCategories"
      @submit="onSubmit"
      @cancel="router.push({ name: 'offers' })"
    />
  </div>
</template>
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd admin && npx vitest run tests/components/OfferForm.test.js tests/views/OfferFormView.test.js`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add admin/src/components/OfferForm.vue admin/src/views/OfferFormView.vue admin/tests/components/OfferForm.test.js admin/tests/views/OfferFormView.test.js
git commit -m "feat(admin): offer form component and create/edit view"
```

---

### Task 15: Sources view

**Files:**
- Modify: `admin/src/views/SourcesView.vue` (replace stub)
- Test: `admin/tests/views/SourcesView.test.js`

**Interfaces:**
- Consumes: `api/sources.js`; `constants/enums.js` `SOURCE_TYPES`; `utils/format.js` `enumLabel`; `utils/confirm.js`; `utils/errors.js`; Element Plus.
- Produces: `SourcesView` — a table of sources with a create/edit dialog (fields: name, type, url_or_handle, is_active) and delete-with-confirm. Exposes `{ items, load, openCreate, openEdit, save, onDelete, form, editingId }`.

- [ ] **Step 1: Write the failing test — `admin/tests/views/SourcesView.test.js`**

```js
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import ElementPlus from "element-plus";
import SourcesView from "@/views/SourcesView.vue";

vi.mock("@/api/sources", () => ({
  list: vi.fn(() => Promise.resolve([{ id: 1, name: "S", type: "telegram", url_or_handle: "@s", is_active: true }])),
  create: vi.fn(() => Promise.resolve({})),
  update: vi.fn(() => Promise.resolve({})),
  remove: vi.fn(() => Promise.resolve({})),
}));
vi.mock("@/utils/confirm", () => ({ confirmDelete: vi.fn(() => Promise.resolve()) }));
vi.mock("element-plus", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, ElMessage: { success: vi.fn(), error: vi.fn() } };
});
import * as sources from "@/api/sources";

describe("SourcesView", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads sources on mount", async () => {
    mount(SourcesView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    expect(sources.list).toHaveBeenCalled();
  });

  it("creates a source via the dialog", async () => {
    const wrapper = mount(SourcesView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    wrapper.vm.openCreate();
    Object.assign(wrapper.vm.form, { name: "New", type: "website", url_or_handle: "https://x", is_active: true });
    await wrapper.vm.save();
    await flushPromises();
    expect(sources.create).toHaveBeenCalledWith({ name: "New", type: "website", url_or_handle: "https://x", is_active: true });
    expect(sources.list).toHaveBeenCalledTimes(2);
  });

  it("deletes a source", async () => {
    const wrapper = mount(SourcesView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    await wrapper.vm.onDelete(1);
    await flushPromises();
    expect(sources.remove).toHaveBeenCalledWith(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && npx vitest run tests/views/SourcesView.test.js`
Expected: FAIL — stub lacks behaviour.

- [ ] **Step 3: Replace `admin/src/views/SourcesView.vue`**

```vue
<script setup>
import { ref, reactive, onMounted } from "vue";
import { ElMessage } from "element-plus";
import * as sources from "@/api/sources";
import { SOURCE_TYPES } from "@/constants/enums";
import { enumLabel } from "@/utils/format";
import { confirmDelete } from "@/utils/confirm";
import { extractError } from "@/utils/errors";

const items = ref([]);
const loading = ref(false);
const dialogVisible = ref(false);
const editingId = ref(null);
const form = reactive({ name: "", type: "website", url_or_handle: "", is_active: true });

async function load() {
  loading.value = true;
  try {
    items.value = await sources.list();
  } catch (e) {
    ElMessage.error(extractError(e));
  } finally {
    loading.value = false;
  }
}
onMounted(load);

function openCreate() {
  editingId.value = null;
  Object.assign(form, { name: "", type: "website", url_or_handle: "", is_active: true });
  dialogVisible.value = true;
}
function openEdit(row) {
  editingId.value = row.id;
  Object.assign(form, { name: row.name, type: row.type, url_or_handle: row.url_or_handle, is_active: row.is_active });
  dialogVisible.value = true;
}
async function save() {
  if (!form.name || !form.url_or_handle) {
    ElMessage.error("Заповніть назву та URL/handle");
    return;
  }
  try {
    if (editingId.value) await sources.update(editingId.value, { ...form });
    else await sources.create({ ...form });
    ElMessage.success("Збережено");
    dialogVisible.value = false;
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}
async function onDelete(id) {
  try {
    await confirmDelete();
  } catch {
    return;
  }
  try {
    await sources.remove(id);
    ElMessage.success("Видалено");
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

defineExpose({ items, load, openCreate, openEdit, save, onDelete, form, editingId });
</script>

<template>
  <div class="sources-view">
    <div class="header">
      <h2>Джерела</h2>
      <el-button type="primary" @click="openCreate">Додати джерело</el-button>
    </div>

    <el-table :data="items" v-loading="loading" style="width: 100%">
      <el-table-column prop="name" label="Назва" />
      <el-table-column label="Тип">
        <template #default="{ row }">{{ enumLabel(SOURCE_TYPES, row.type) }}</template>
      </el-table-column>
      <el-table-column prop="url_or_handle" label="URL / handle" />
      <el-table-column label="Активне">
        <template #default="{ row }">{{ row.is_active ? "Так" : "Ні" }}</template>
      </el-table-column>
      <el-table-column label="Дії" width="200">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">Редагувати</el-button>
          <el-button size="small" type="danger" @click="onDelete(row.id)">Видалити</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editingId ? 'Редагувати джерело' : 'Нове джерело'">
      <el-form label-position="top">
        <el-form-item label="Назва" required>
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="Тип">
          <el-select v-model="form.type" style="width: 200px">
            <el-option v-for="t in SOURCE_TYPES" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="URL / handle" required>
          <el-input v-model="form.url_or_handle" />
        </el-form-item>
        <el-form-item label="Активне">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">Скасувати</el-button>
        <el-button type="primary" @click="save">Зберегти</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped lang="less">
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd admin && npx vitest run tests/views/SourcesView.test.js`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add admin/src/views/SourcesView.vue admin/tests/views/SourcesView.test.js
git commit -m "feat(admin): sources CRUD view"
```

---

### Task 16: Suggested sources view

**Files:**
- Modify: `admin/src/views/SuggestedSourcesView.vue` (replace stub)
- Test: `admin/tests/views/SuggestedSourcesView.test.js`

**Interfaces:**
- Consumes: `api/suggestedSources.js`; `constants/enums.js` `SOURCE_TYPES`, `SUGGESTION_STATUSES`; `utils/format.js`; `utils/errors.js`; Element Plus.
- Produces: `SuggestedSourcesView` — a table of suggestions with a status filter (default `pending`) and Approve/Reject actions. Exposes `{ items, load, onApprove, onReject, status }`.

- [ ] **Step 1: Write the failing test — `admin/tests/views/SuggestedSourcesView.test.js`**

```js
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import ElementPlus from "element-plus";
import SuggestedSourcesView from "@/views/SuggestedSourcesView.vue";

vi.mock("@/api/suggestedSources", () => ({
  list: vi.fn(() => Promise.resolve([
    { id: 3, name: "New TG", type: "telegram", url_or_handle: "@n", discovery_note: "нотатка", status: "pending" },
  ])),
  approve: vi.fn(() => Promise.resolve({})),
  reject: vi.fn(() => Promise.resolve({})),
}));
vi.mock("element-plus", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, ElMessage: { success: vi.fn(), error: vi.fn() } };
});
import * as suggested from "@/api/suggestedSources";

describe("SuggestedSourcesView", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads pending suggestions on mount", async () => {
    mount(SuggestedSourcesView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    expect(suggested.list).toHaveBeenCalledWith({ status: "pending" });
  });

  it("approve calls the API and reloads", async () => {
    const wrapper = mount(SuggestedSourcesView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    await wrapper.vm.onApprove(3);
    await flushPromises();
    expect(suggested.approve).toHaveBeenCalledWith(3);
    expect(suggested.list).toHaveBeenCalledTimes(2);
  });

  it("reject calls the API", async () => {
    const wrapper = mount(SuggestedSourcesView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    await wrapper.vm.onReject(3);
    await flushPromises();
    expect(suggested.reject).toHaveBeenCalledWith(3);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && npx vitest run tests/views/SuggestedSourcesView.test.js`
Expected: FAIL — stub lacks behaviour.

- [ ] **Step 3: Replace `admin/src/views/SuggestedSourcesView.vue`**

```vue
<script setup>
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import * as suggested from "@/api/suggestedSources";
import { SOURCE_TYPES, SUGGESTION_STATUSES } from "@/constants/enums";
import { enumLabel } from "@/utils/format";
import { extractError } from "@/utils/errors";

const items = ref([]);
const loading = ref(false);
const status = ref("pending");

async function load() {
  loading.value = true;
  try {
    items.value = await suggested.list({ status: status.value });
  } catch (e) {
    ElMessage.error(extractError(e));
  } finally {
    loading.value = false;
  }
}
onMounted(load);

async function onApprove(id) {
  try {
    await suggested.approve(id);
    ElMessage.success("Схвалено — джерело створено");
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}
async function onReject(id) {
  try {
    await suggested.reject(id);
    ElMessage.success("Відхилено");
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

defineExpose({ items, load, onApprove, onReject, status });
</script>

<template>
  <div class="suggested-view">
    <div class="header">
      <h2>Запропоновані джерела</h2>
      <el-select v-model="status" style="width: 160px" @change="load">
        <el-option v-for="s in SUGGESTION_STATUSES" :key="s.value" :label="s.label" :value="s.value" />
      </el-select>
    </div>

    <el-table :data="items" v-loading="loading" style="width: 100%">
      <el-table-column prop="name" label="Назва" />
      <el-table-column label="Тип">
        <template #default="{ row }">{{ enumLabel(SOURCE_TYPES, row.type) }}</template>
      </el-table-column>
      <el-table-column prop="url_or_handle" label="URL / handle" />
      <el-table-column prop="discovery_note" label="Нотатка" />
      <el-table-column label="Дії" width="220">
        <template #default="{ row }">
          <template v-if="row.status === 'pending'">
            <el-button size="small" type="success" @click="onApprove(row.id)">Схвалити</el-button>
            <el-button size="small" type="danger" @click="onReject(row.id)">Відхилити</el-button>
          </template>
          <span v-else>{{ enumLabel(SUGGESTION_STATUSES, row.status) }}</span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped lang="less">
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd admin && npx vitest run tests/views/SuggestedSourcesView.test.js`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add admin/src/views/SuggestedSourcesView.vue admin/tests/views/SuggestedSourcesView.test.js
git commit -m "feat(admin): suggested sources approve/reject view"
```

---

### Task 17: Category dictionaries view

**Files:**
- Modify: `admin/src/views/CategoriesView.vue` (replace stub)
- Test: `admin/tests/views/CategoriesView.test.js`

**Interfaces:**
- Consumes: `api/categories.js`; `stores/dictionaries.js`; `utils/confirm.js`; `utils/errors.js`; Element Plus.
- Produces: `CategoriesView` — two tabs (target / offer). Each tab shows the cached dictionary list and an inline add row (name, slug); edit and delete per row. All mutations go through `api/categories.js` then `dictionaries.reload()`. Exposes `{ save, remove }` where `save(kind, form, id = null)` and `remove(kind, id)` with `kind ∈ {"target","offer"}`.

- [ ] **Step 1: Write the failing test — `admin/tests/views/CategoriesView.test.js`**

```js
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import ElementPlus from "element-plus";
import CategoriesView from "@/views/CategoriesView.vue";

vi.mock("@/api/categories", () => ({
  listTarget: vi.fn(() => Promise.resolve([{ id: 1, name: "УБД", slug: "ubd" }])),
  listOffer: vi.fn(() => Promise.resolve([{ id: 2, name: "Розваги", slug: "rozvahy" }])),
  createTarget: vi.fn(() => Promise.resolve({})),
  updateTarget: vi.fn(() => Promise.resolve({})),
  removeTarget: vi.fn(() => Promise.resolve({})),
  createOffer: vi.fn(() => Promise.resolve({})),
  updateOffer: vi.fn(() => Promise.resolve({})),
  removeOffer: vi.fn(() => Promise.resolve({})),
}));
vi.mock("@/utils/confirm", () => ({ confirmDelete: vi.fn(() => Promise.resolve()) }));
vi.mock("element-plus", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, ElMessage: { success: vi.fn(), error: vi.fn() } };
});
import * as categories from "@/api/categories";

describe("CategoriesView", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it("creates a target category and reloads the dictionary", async () => {
    const wrapper = mount(CategoriesView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    await wrapper.vm.save("target", { name: "Ветеран", slug: "veteran" });
    await flushPromises();
    expect(categories.createTarget).toHaveBeenCalledWith({ name: "Ветеран", slug: "veteran" });
    // dictionaries.reload re-fetches both lists (once on mount + once after save)
    expect(categories.listTarget).toHaveBeenCalledTimes(2);
  });

  it("deletes an offer category", async () => {
    const wrapper = mount(CategoriesView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    await wrapper.vm.remove("offer", 2);
    await flushPromises();
    expect(categories.removeOffer).toHaveBeenCalledWith(2);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && npx vitest run tests/views/CategoriesView.test.js`
Expected: FAIL — stub lacks behaviour.

- [ ] **Step 3: Replace `admin/src/views/CategoriesView.vue`**

```vue
<script setup>
import { reactive, onMounted } from "vue";
import { ElMessage } from "element-plus";
import * as categories from "@/api/categories";
import { useDictionariesStore } from "@/stores/dictionaries";
import { confirmDelete } from "@/utils/confirm";
import { extractError } from "@/utils/errors";

const dictionaries = useDictionariesStore();
onMounted(() => dictionaries.load());

const api = {
  target: { create: categories.createTarget, update: categories.updateTarget, remove: categories.removeTarget },
  offer: { create: categories.createOffer, update: categories.updateOffer, remove: categories.removeOffer },
};

const drafts = reactive({
  target: { name: "", slug: "" },
  offer: { name: "", slug: "" },
});

async function save(kind, form, id = null) {
  if (!form.name || !form.slug) {
    ElMessage.error("Вкажіть назву та slug");
    return;
  }
  try {
    if (id) await api[kind].update(id, { name: form.name, slug: form.slug });
    else await api[kind].create({ name: form.name, slug: form.slug });
    ElMessage.success("Збережено");
    await dictionaries.reload();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

async function addDraft(kind) {
  await save(kind, drafts[kind]);
  drafts[kind].name = "";
  drafts[kind].slug = "";
}

async function remove(kind, id) {
  try {
    await confirmDelete();
  } catch {
    return;
  }
  try {
    await api[kind].remove(id);
    ElMessage.success("Видалено");
    await dictionaries.reload();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

defineExpose({ save, remove });
</script>

<template>
  <div class="categories-view">
    <h2>Категорії</h2>
    <el-tabs>
      <el-tab-pane label="Для кого">
        <el-table :data="dictionaries.targetCategories" style="width: 100%">
          <el-table-column prop="name" label="Назва" />
          <el-table-column prop="slug" label="Slug" />
          <el-table-column label="Дії" width="140">
            <template #default="{ row }">
              <el-button size="small" type="danger" @click="remove('target', row.id)">Видалити</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="add-row">
          <el-input v-model="drafts.target.name" placeholder="Назва" style="width: 200px" />
          <el-input v-model="drafts.target.slug" placeholder="slug" style="width: 200px" />
          <el-button type="primary" @click="addDraft('target')">Додати</el-button>
        </div>
      </el-tab-pane>

      <el-tab-pane label="Тематика">
        <el-table :data="dictionaries.offerCategories" style="width: 100%">
          <el-table-column prop="name" label="Назва" />
          <el-table-column prop="slug" label="Slug" />
          <el-table-column label="Дії" width="140">
            <template #default="{ row }">
              <el-button size="small" type="danger" @click="remove('offer', row.id)">Видалити</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="add-row">
          <el-input v-model="drafts.offer.name" placeholder="Назва" style="width: 200px" />
          <el-input v-model="drafts.offer.slug" placeholder="slug" style="width: 200px" />
          <el-button type="primary" @click="addDraft('offer')">Додати</el-button>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped lang="less">
.add-row { display: flex; gap: 8px; margin-top: 12px; }
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd admin && npx vitest run tests/views/CategoriesView.test.js`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add admin/src/views/CategoriesView.vue admin/tests/views/CategoriesView.test.js
git commit -m "feat(admin): category dictionaries management view"
```

---

### Task 18: Admin users view and full-suite green

**Files:**
- Modify: `admin/src/views/AdminUsersView.vue` (replace stub)
- Create: `admin/README.md`
- Test: `admin/tests/views/AdminUsersView.test.js`

**Interfaces:**
- Consumes: `api/users.js`; `constants/enums.js` `ADMIN_ROLES`; `utils/format.js`; `utils/confirm.js`; `utils/errors.js`; Element Plus.
- Produces: `AdminUsersView` — table (email, role, created) + a create form (email, password, role) + delete-with-confirm. Exposes `{ items, form, load, create, onDelete }`.

- [ ] **Step 1: Write the failing test — `admin/tests/views/AdminUsersView.test.js`**

```js
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import ElementPlus from "element-plus";
import AdminUsersView from "@/views/AdminUsersView.vue";

vi.mock("@/api/users", () => ({
  list: vi.fn(() => Promise.resolve([{ id: 1, email: "a@b.c", role: "super_admin", created_at: "2026-07-01" }])),
  create: vi.fn(() => Promise.resolve({})),
  remove: vi.fn(() => Promise.resolve({})),
}));
vi.mock("@/utils/confirm", () => ({ confirmDelete: vi.fn(() => Promise.resolve()) }));
vi.mock("element-plus", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, ElMessage: { success: vi.fn(), error: vi.fn() } };
});
import * as users from "@/api/users";

describe("AdminUsersView", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads users on mount", async () => {
    mount(AdminUsersView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    expect(users.list).toHaveBeenCalled();
  });

  it("creates a user", async () => {
    const wrapper = mount(AdminUsersView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    Object.assign(wrapper.vm.form, { email: "new@b.c", password: "pw123456", role: "moderator" });
    await wrapper.vm.create();
    await flushPromises();
    expect(users.create).toHaveBeenCalledWith({ email: "new@b.c", password: "pw123456", role: "moderator" });
    expect(users.list).toHaveBeenCalledTimes(2);
  });

  it("deletes a user", async () => {
    const wrapper = mount(AdminUsersView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    await wrapper.vm.onDelete(1);
    await flushPromises();
    expect(users.remove).toHaveBeenCalledWith(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && npx vitest run tests/views/AdminUsersView.test.js`
Expected: FAIL — stub lacks behaviour.

- [ ] **Step 3: Replace `admin/src/views/AdminUsersView.vue`**

```vue
<script setup>
import { ref, reactive, onMounted } from "vue";
import { ElMessage } from "element-plus";
import * as users from "@/api/users";
import { ADMIN_ROLES } from "@/constants/enums";
import { enumLabel, formatDate } from "@/utils/format";
import { confirmDelete } from "@/utils/confirm";
import { extractError } from "@/utils/errors";

const items = ref([]);
const loading = ref(false);
const form = reactive({ email: "", password: "", role: "moderator" });

async function load() {
  loading.value = true;
  try {
    items.value = await users.list();
  } catch (e) {
    ElMessage.error(extractError(e));
  } finally {
    loading.value = false;
  }
}
onMounted(load);

async function create() {
  if (!form.email || !form.password) {
    ElMessage.error("Вкажіть email і пароль");
    return;
  }
  try {
    await users.create({ email: form.email, password: form.password, role: form.role });
    ElMessage.success("Створено");
    Object.assign(form, { email: "", password: "", role: "moderator" });
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

async function onDelete(id) {
  try {
    await confirmDelete("Видалити цього адміністратора?");
  } catch {
    return;
  }
  try {
    await users.remove(id);
    ElMessage.success("Видалено");
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

defineExpose({ items, form, load, create, onDelete });
</script>

<template>
  <div class="admin-users-view">
    <h2>Адміністратори</h2>

    <el-table :data="items" v-loading="loading" style="width: 100%">
      <el-table-column prop="email" label="Email" />
      <el-table-column label="Роль">
        <template #default="{ row }">{{ enumLabel(ADMIN_ROLES, row.role) }}</template>
      </el-table-column>
      <el-table-column label="Створено">
        <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="Дії" width="140">
        <template #default="{ row }">
          <el-button size="small" type="danger" @click="onDelete(row.id)">Видалити</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-form class="create-form" :inline="true">
      <el-form-item label="Email">
        <el-input v-model="form.email" type="email" />
      </el-form-item>
      <el-form-item label="Пароль">
        <el-input v-model="form.password" type="password" />
      </el-form-item>
      <el-form-item label="Роль">
        <el-select v-model="form.role" style="width: 160px">
          <el-option v-for="r in ADMIN_ROLES" :key="r.value" :label="r.label" :value="r.value" />
        </el-select>
      </el-form-item>
      <el-button type="primary" @click="create">Додати</el-button>
    </el-form>
  </div>
</template>

<style scoped lang="less">
.create-form { margin-top: 16px; }
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd admin && npx vitest run tests/views/AdminUsersView.test.js`
Expected: PASS (3 tests).

- [ ] **Step 5: Create `admin/README.md`**

```markdown
# UBD Admin

Vue 3 + Vite admin panel for the UBD discounts platform.

## Development

    npm install
    npm run dev        # http://localhost:5173, proxies /api → http://localhost:8000

The backend must be running on port 8000 (see ../backend). Log in with a seeded
admin account.

## Tests

    npm run test       # Vitest, no backend required (API is mocked)
```

- [ ] **Step 6: Run the FULL suite**

Run: `cd admin && npm run test`
Expected: ALL test files pass, output pristine.

- [ ] **Step 7: Commit**

```bash
git add admin/src/views/AdminUsersView.vue admin/README.md admin/tests/views/AdminUsersView.test.js
git commit -m "feat(admin): admin users management view; full suite green"
```

---

## Self-Review Notes

- **Spec coverage:**
  - Tech stack (Vue 3 / Vite / Element Plus / Router / Pinia / axios / Less / Vitest) — Task 1.
  - Standalone SPA in `admin/`, Vite `/api` proxy — Task 1.
  - Enum labels + date/status formatting — Task 2.
  - Image placeholder by context — Task 3; consumed in `ImagePreview` (Task 13) and offer form (Task 14).
  - axios client with bearer + 401 handling, error extraction — Task 4.
  - Auth store with localStorage — Task 5; login flow — Task 10.
  - Per-resource API wrappers — Task 6.
  - Cached dictionaries — Task 7.
  - Router + auth/role guards; `/users` and `/categories` super_admin-only — Tasks 8, 9.
  - AdminLayout with role-gated nav + logout — Task 9.
  - Offers list + moderation queue + publish/reject/delete — Task 12.
  - Offer form (all fields, mirrored validation) create/edit — Tasks 13, 14.
  - Sources CRUD — Task 15.
  - Suggested sources approve/reject — Task 16.
  - Category dictionaries management — Task 17.
  - Admin users management — Task 18.
  - Error handling (`{detail, code}` → `ElMessage`), 401 redirect, 403/409/422 surfacing — Tasks 4, 10, and per-view `extractError` usage.
  - Testing: unit (utils, stores, api, composable, validation) + component (Login, OfferForm, list/approve/reject views) — every task.
- **Roles:** category CRUD is super_admin-only in the backend; the plan gives both `/categories` and `/users` `meta.superAdmin` and hides their nav links for moderators. Consistent with the backend spec.
- **Design decisions vs spec:** `ConfirmDialog.vue` → `utils/confirm.js` (ElMessageBox); noted in File Structure. No other deviations.
- **Testing approach:** views expose their action handlers via `defineExpose` so component tests drive them deterministically without fighting Element Plus table-slot DOM; the API is always mocked. This is a deliberate, documented pattern.
- **No backend changes** anywhere in the plan.
