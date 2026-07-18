# Admin UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the admin panel (`admin/`, Vue3/Element Plus) into the same light amber theme as the public site, as simply as possible, and make source URLs clickable in offer/moderation and source tables.

**Architecture:** Recolor Element Plus by overriding its `--el-*` CSS custom properties in one global stylesheet (no SCSS/build changes). Mirror the public design tokens into `admin/src/styles/variables.less`. Apply the UAF Memory display font only to headings/brand/nav; keep table/form body in `system-ui`. Restyle the two bespoke chrome surfaces (`AdminLayout`, `LoginView`) by hand. Add clickable `<el-link>`s where URLs are shown.

**Tech Stack:** Vue 3 (`<script setup>`), Element Plus ^2.7.0, Less, Vite, Vitest + @vue/test-utils.

## Global Constraints

- No backend/API/crawler changes. Styling + one presentational feature (clickable links) only.
- No new model fields, no new routes, no logic refactors in existing views.
- Color source of truth = the public token values in `public/src/styles/variables.less`. Use the exact hex values listed in Task 1.
- UAF Memory applies ONLY to headings/logo/nav labels. `body` stays `system-ui`. No `font-weight:800` anywhere (faces exist for 300/400/500/700/900 only).
- Semantic status colors (Element Plus success/warning/danger/info) stay default — do NOT recolor them to amber.
- Existing admin Vitest suite (69 tests) must stay green throughout. Public suite (52 tests) must stay green after Task 3.
- Element Plus imported as `element-plus/dist/index.css` (CSS-var theming) — do NOT switch to SCSS sources.
- All external links open in a new tab with `target="_blank"` and `rel="noopener noreferrer"`.
- Run admin commands from `admin/`; public commands from `public/`.

---

### Task 1: Design tokens + Element Plus theme override

**Files:**
- Modify (rewrite): `admin/src/styles/variables.less`
- Create: `admin/src/styles/element-theme.less`
- Modify: `admin/src/styles/global.less`

**Interfaces:**
- Produces: Less vars `@bg @surface @text @brand @divider @nav-muted @meta-muted @cream @dark @heading-weight @sidebar-width` (consumed by Tasks 2, 4, 5). `@brand` = `#E0982A`.

- [ ] **Step 1: Rewrite the token file**

Replace the entire contents of `admin/src/styles/variables.less` with:

```less
// UI-редизайн адмінки — світлий мінімалізм, бурштиновий акцент (дзеркало public-токенів)
@bg: #FAFAF9;            // тло контенту
@surface: #FFFFFF;      // сайдбар/топбар/картки
@text: #14110A;         // основний текст
@brand: #E0982A;        // бурштин (primary)
@divider: #E7E5E0;      // тонкі лінії
@nav-muted: #8A8578;    // неактивна навігація
@meta-muted: #7E7768;   // лейбли, мета
@cream: #F5F1E8;        // крем-панель (login-картка, активний пункт)
@dark: #211D16;         // темні акценти
@heading-weight: 900;   // вага заголовків UAF Memory (консистентно з public)
@sidebar-width: 220px;
```

- [ ] **Step 2: Create the Element Plus theme override**

Create `admin/src/styles/element-theme.less` with:

```less
// Перефарбування Element Plus primary → бурштин через CSS-змінні.
// Семантичні (success/warning/danger/info) НЕ чіпаємо — статуси лишаються скануваними.
:root {
  --el-color-primary: #E0982A;
  --el-color-primary-light-3: #E9B76A;
  --el-color-primary-light-5: #EFCB95;
  --el-color-primary-light-7: #F6E0BF;
  --el-color-primary-light-8: #F9EAD4;
  --el-color-primary-light-9: #FCF5EA;
  --el-color-primary-dark-2: #B37A22;
}
```

- [ ] **Step 3: Wire both into the global stylesheet**

Replace the entire contents of `admin/src/styles/global.less` with:

```less
@import "./variables.less";
@import "./element-theme.less";

html, body, #app { height: 100%; margin: 0; }
body { font-family: system-ui, sans-serif; color: @text; background: @bg; }
```

- [ ] **Step 4: Run the admin suite to confirm no regression**

Run (from `admin/`): `npm test`
Expected: all 69 tests pass (styling change, no behavior change).

- [ ] **Step 5: Commit**

```bash
git add admin/src/styles/variables.less admin/src/styles/element-theme.less admin/src/styles/global.less
git commit -m "feat(admin-ui): amber Element Plus theme + mirrored tokens"
```

---

### Task 2: UAF Memory font (infrastructure + headings)

**Files:**
- Create: `admin/src/assets/fonts/UAFMemory-Light.woff2`, `-Regular.woff2`, `-Medium.woff2`, `-Bold.woff2`, `-Black.woff2` (copies of the public files)
- Create: `admin/src/styles/fonts.less`
- Modify: `admin/src/styles/global.less`

**Interfaces:**
- Consumes: `@heading-weight` from Task 1.
- Produces: `"UAF Memory"` font-family available app-wide; global `h1`/`h2` use it.

- [ ] **Step 1: Copy the font assets**

Copy the 5 woff2 files from `public/src/assets/fonts/` into `admin/src/assets/fonts/` (create the folder). Bash:

```bash
mkdir -p admin/src/assets/fonts
cp public/src/assets/fonts/UAFMemory-*.woff2 admin/src/assets/fonts/
ls admin/src/assets/fonts/
```

Expected: 5 files listed (Light, Regular, Medium, Bold, Black).

- [ ] **Step 2: Create `admin/src/styles/fonts.less`** (mirror of public)

```less
@font-face { font-family: "UAF Memory"; font-weight: 300; font-style: normal; font-display: swap;
  src: url("../assets/fonts/UAFMemory-Light.woff2") format("woff2"); }
@font-face { font-family: "UAF Memory"; font-weight: 400; font-style: normal; font-display: swap;
  src: url("../assets/fonts/UAFMemory-Regular.woff2") format("woff2"); }
@font-face { font-family: "UAF Memory"; font-weight: 500; font-style: normal; font-display: swap;
  src: url("../assets/fonts/UAFMemory-Medium.woff2") format("woff2"); }
@font-face { font-family: "UAF Memory"; font-weight: 700; font-style: normal; font-display: swap;
  src: url("../assets/fonts/UAFMemory-Bold.woff2") format("woff2"); }
@font-face { font-family: "UAF Memory"; font-weight: 900; font-style: normal; font-display: swap;
  src: url("../assets/fonts/UAFMemory-Black.woff2") format("woff2"); }
```

- [ ] **Step 3: Import fonts + apply to global headings**

Edit `admin/src/styles/global.less` to add the fonts import (after the element-theme import) and a heading rule. Full new contents:

```less
@import "./variables.less";
@import "./element-theme.less";
@import "./fonts.less";

html, body, #app { height: 100%; margin: 0; }
body { font-family: system-ui, sans-serif; color: @text; background: @bg; }
h1, h2 { font-family: "UAF Memory", system-ui, sans-serif; font-weight: @heading-weight; }
```

- [ ] **Step 4: Run the admin suite**

Run (from `admin/`): `npm test`
Expected: all 69 tests pass.

- [ ] **Step 5: Commit**

```bash
git add admin/src/assets/fonts admin/src/styles/fonts.less admin/src/styles/global.less
git commit -m "feat(admin-ui): load UAF Memory, apply to headings"
```

---

### Task 3: Normalize public `font-weight:800` → `900`

**Files:**
- Modify: `public/src/views/OfferDetailView.vue:93`
- Modify: `public/src/components/SiteHeader.vue:16`
- Modify: `public/src/components/OfferCard.vue:67`
- Modify: `public/src/components/OfferBadge.vue:18`

**Interfaces:** none (pure CSS value change; zero visual change — 800 already renders as the 900 face).

- [ ] **Step 1: Edit the four declarations**

In each file, change `font-weight: 800` to `font-weight: 900`:
- `public/src/views/OfferDetailView.vue:93` — `.detail__provider`
- `public/src/components/SiteHeader.vue:16` — `.brand`
- `public/src/components/OfferCard.vue:67` — card provider heading
- `public/src/components/OfferBadge.vue:18` — badge

- [ ] **Step 2: Confirm no 800 remains**

Run: `git grep -n "font-weight: 800" public/ ; git grep -n "font-weight:800" public/`
Expected: no output.

- [ ] **Step 3: Run the public suite**

Run (from `public/`): `npm test`
Expected: all 52 tests pass (styling only).

- [ ] **Step 4: Commit**

```bash
git add public/src/views/OfferDetailView.vue public/src/components/SiteHeader.vue public/src/components/OfferCard.vue public/src/components/OfferBadge.vue
git commit -m "style(public-ui): normalize font-weight 800->900 (explicit face)"
```

---

### Task 4: Restyle `AdminLayout` chrome

**Files:**
- Modify: `admin/src/layouts/AdminLayout.vue` (`<style>` block + `.logo` class; template structure unchanged)
- Test: `admin/tests/layouts/AdminLayout.test.js` (already exists — must stay green)

**Interfaces:**
- Consumes: tokens from Task 1; `"UAF Memory"` from Task 2.
- Do NOT change the template's links, `el-badge`, `logout()`, or `defineExpose`. Style-only edits plus adding `class` hooks already present (`.logo`, `.sidebar nav a`).

- [ ] **Step 1: Confirm current layout tests pass (baseline)**

Run (from `admin/`): `npx vitest run tests/layouts/AdminLayout.test.js`
Expected: 2 tests pass.

- [ ] **Step 2: Replace the `<style scoped>` block**

In `admin/src/layouts/AdminLayout.vue`, replace the entire `<style scoped lang="less">…</style>` block with:

```less
@import "@/styles/variables.less";
.admin-layout { display: flex; height: 100%; }
.sidebar { width: @sidebar-width; background: @surface; border-right: 1px solid @divider; padding: 16px 12px; }
.logo { font-family: "UAF Memory", system-ui, sans-serif; font-weight: @heading-weight; font-size: 26px; color: @brand; margin: 0 0 16px; letter-spacing: -.3px; }
.sidebar nav { display: flex; flex-direction: column; gap: 4px; }
.sidebar nav a { font-family: "UAF Memory", system-ui, sans-serif; font-weight: 500; text-decoration: none; color: @nav-muted; padding: 8px 10px; border-radius: 8px; border-left: 3px solid transparent; }
.sidebar nav a:hover { color: @text; background: @cream; }
.sidebar nav a.router-link-active { color: @brand; background: @cream; border-left-color: @brand; }
.main { flex: 1; display: flex; flex-direction: column; background: @bg; }
.topbar { display: flex; justify-content: flex-end; align-items: center; gap: 12px; padding: 10px 16px; background: @surface; border-bottom: 1px solid @divider; }
.topbar .role { color: @meta-muted; font-size: 13px; text-transform: uppercase; letter-spacing: .3px; }
.content { padding: 20px; overflow: auto; }
```

Note: the topbar's `.role` span currently has no class. In the template, change `<span class="role">` — it already has `class="role"` (line 44). No template edit needed. Leave everything else in the template as-is.

- [ ] **Step 3: Run the layout tests**

Run (from `admin/`): `npx vitest run tests/layouts/AdminLayout.test.js`
Expected: 2 tests pass (text/role-visibility assertions unaffected by styling).

- [ ] **Step 4: Run the full admin suite**

Run (from `admin/`): `npm test`
Expected: all 69 tests pass.

- [ ] **Step 5: Commit**

```bash
git add admin/src/layouts/AdminLayout.vue
git commit -m "feat(admin-ui): light amber sidebar/topbar chrome"
```

---

### Task 5: Restyle `LoginView` chrome

**Files:**
- Modify: `admin/src/views/LoginView.vue` (`<style scoped>` + wrap heading; template logic unchanged)
- Test: `admin/tests/views/LoginView.test.js` (must stay green)

**Interfaces:**
- Consumes: tokens from Task 1; `"UAF Memory"` from Task 2.
- Do NOT change `submit()`, `form`, or `defineExpose`.

- [ ] **Step 1: Confirm current login tests pass (baseline)**

Run (from `admin/`): `npx vitest run tests/views/LoginView.test.js`
Expected: existing tests pass.

- [ ] **Step 2: Replace the `<style scoped>` block**

In `admin/src/views/LoginView.vue`, replace the `<style scoped lang="less">…</style>` block with:

```less
@import "@/styles/variables.less";
.login { display: flex; justify-content: center; align-items: center; height: 100%; background: @bg; }
.login-form { width: 320px; padding: 28px 24px; background: @cream; border: 1px solid @divider; border-radius: 12px; }
.login-form h2 { margin: 0 0 18px; color: @text; }
.login-form .el-button { width: 100%; }
```

The `<h2>UBD — Вхід</h2>` in the template already picks up UAF Memory via the global `h2` rule (Task 2) — no template change required.

- [ ] **Step 3: Run the login tests**

Run (from `admin/`): `npx vitest run tests/views/LoginView.test.js`
Expected: tests pass.

- [ ] **Step 4: Run the full admin suite**

Run (from `admin/`): `npm test`
Expected: all 69 tests pass.

- [ ] **Step 5: Commit**

```bash
git add admin/src/views/LoginView.vue
git commit -m "feat(admin-ui): light amber login card"
```

---

### Task 6: Clickable source links in offers / moderation table

**Files:**
- Modify: `admin/src/views/OffersListView.vue` (add a "Джерело" column before the "Дії" column)
- Test: `admin/tests/views/OffersListView.test.js` (add one test)

**Interfaces:**
- Consumes: offer rows may carry `site_url` and `article_url` (strings or null). No API change.
- Produces: a table column rendering `<el-link>` for present URLs.

- [ ] **Step 1: Write the failing test**

Add this test to `admin/tests/views/OffersListView.test.js` (inside the `describe`), after the existing tests:

```javascript
  it("renders a clickable source link when site_url is present", async () => {
    offers.list.mockResolvedValueOnce({
      items: [{ id: 1, title: "T", provider: "P", type: "discount", status: "published", valid_until: null, site_url: "https://shop.example", article_url: null }],
      total: 1,
    });
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    const wrapper = mount(OffersListView, { global: { plugins: [router, ElementPlus] } });
    await flushPromises();
    const link = wrapper.find('a[href="https://shop.example"]');
    expect(link.exists()).toBe(true);
    expect(link.attributes("target")).toBe("_blank");
    expect(link.attributes("rel")).toContain("noopener");
  });
```

- [ ] **Step 2: Run it to confirm it fails**

Run (from `admin/`): `npx vitest run tests/views/OffersListView.test.js -t "clickable source link"`
Expected: FAIL (no matching `<a>` — column not added yet).

- [ ] **Step 3: Add the "Джерело" column**

In `admin/src/views/OffersListView.vue`, insert a new column immediately before the `<el-table-column label="Дії" width="280">` column:

```html
      <el-table-column label="Джерело" width="140">
        <template #default="{ row }">
          <el-link
            v-if="row.site_url"
            :href="row.site_url"
            type="primary"
            target="_blank"
            rel="noopener noreferrer"
          >Сайт ↗</el-link>
          <el-link
            v-if="row.article_url"
            :href="row.article_url"
            type="primary"
            target="_blank"
            rel="noopener noreferrer"
            style="margin-left: 8px"
          >Стаття ↗</el-link>
          <span v-if="!row.site_url && !row.article_url" style="color: var(--el-text-color-placeholder)">—</span>
        </template>
      </el-table-column>
```

- [ ] **Step 4: Run the new test**

Run (from `admin/`): `npx vitest run tests/views/OffersListView.test.js -t "clickable source link"`
Expected: PASS.

- [ ] **Step 5: Run the full admin suite**

Run (from `admin/`): `npm test`
Expected: all 70 tests pass (69 + new).

- [ ] **Step 6: Commit**

```bash
git add admin/src/views/OffersListView.vue admin/tests/views/OffersListView.test.js
git commit -m "feat(admin-ui): clickable source links in offers/moderation table"
```

---

### Task 7: Clickable URL links in source tables

**Files:**
- Modify: `admin/src/views/SourcesView.vue` (make `url_or_handle` column a link for `type === "website"`)
- Modify: `admin/src/views/SuggestedSourcesView.vue` (same)
- Test: `admin/tests/views/SourcesView.test.js` (add one test), `admin/tests/views/SuggestedSourcesView.test.js` (add one test)

**Interfaces:**
- Consumes: source rows carry `type` and `url_or_handle`. `type === "website"` ⇒ `url_or_handle` is an http URL.
- Produces: `<el-link>` for website rows; plain text for social handles.

- [ ] **Step 1: Write the failing SourcesView test**

Add to `admin/tests/views/SourcesView.test.js` inside the `describe`:

```javascript
  it("renders url_or_handle as a link for website sources, plain text otherwise", async () => {
    sources.list.mockResolvedValueOnce([
      { id: 1, name: "W", type: "website", url_or_handle: "https://site.example", is_active: true },
      { id: 2, name: "T", type: "telegram", url_or_handle: "@chan", is_active: true },
    ]);
    const wrapper = mount(SourcesView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    const link = wrapper.find('a[href="https://site.example"]');
    expect(link.exists()).toBe(true);
    expect(link.attributes("target")).toBe("_blank");
    expect(wrapper.text()).toContain("@chan");
    expect(wrapper.find('a[href="@chan"]').exists()).toBe(false);
  });
```

- [ ] **Step 2: Run it to confirm it fails**

Run (from `admin/`): `npx vitest run tests/views/SourcesView.test.js -t "renders url_or_handle as a link"`
Expected: FAIL (no matching `<a>`).

- [ ] **Step 3: Update the SourcesView column**

In `admin/src/views/SourcesView.vue`, replace the line
`<el-table-column prop="url_or_handle" label="URL / handle" />`
with:

```html
      <el-table-column label="URL / handle">
        <template #default="{ row }">
          <el-link
            v-if="row.type === 'website'"
            :href="row.url_or_handle"
            type="primary"
            target="_blank"
            rel="noopener noreferrer"
          >{{ row.url_or_handle }}</el-link>
          <span v-else>{{ row.url_or_handle }}</span>
        </template>
      </el-table-column>
```

- [ ] **Step 4: Run the SourcesView test**

Run (from `admin/`): `npx vitest run tests/views/SourcesView.test.js -t "renders url_or_handle as a link"`
Expected: PASS.

- [ ] **Step 5: Write the failing SuggestedSourcesView test**

Add to `admin/tests/views/SuggestedSourcesView.test.js` inside the `describe` (mirror the mock helper already used in that file — it mocks `@/api/suggestedSources`). Use `suggested.list.mockResolvedValueOnce`:

```javascript
  it("renders url_or_handle as a link for website suggestions, plain text otherwise", async () => {
    suggested.list.mockResolvedValueOnce([
      { id: 1, name: "W", type: "website", url_or_handle: "https://found.example", discovery_note: "", status: "pending" },
      { id: 2, name: "I", type: "instagram", url_or_handle: "@insta", discovery_note: "", status: "pending" },
    ]);
    const wrapper = mount(SuggestedSourcesView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    const link = wrapper.find('a[href="https://found.example"]');
    expect(link.exists()).toBe(true);
    expect(link.attributes("target")).toBe("_blank");
    expect(wrapper.text()).toContain("@insta");
    expect(wrapper.find('a[href="@insta"]').exists()).toBe(false);
  });
```

Note: verify the test file's existing imports expose `suggested` (i.e. `import * as suggested from "@/api/suggestedSources"`) and `SuggestedSourcesView`, `mount`, `flushPromises`, `ElementPlus`. If `suggested` is not imported, add `import * as suggested from "@/api/suggestedSources";` next to the existing mock.

- [ ] **Step 6: Run it to confirm it fails**

Run (from `admin/`): `npx vitest run tests/views/SuggestedSourcesView.test.js -t "renders url_or_handle as a link"`
Expected: FAIL.

- [ ] **Step 7: Update the SuggestedSourcesView column**

In `admin/src/views/SuggestedSourcesView.vue`, replace the line
`<el-table-column prop="url_or_handle" label="URL / handle" />`
with:

```html
      <el-table-column label="URL / handle">
        <template #default="{ row }">
          <el-link
            v-if="row.type === 'website'"
            :href="row.url_or_handle"
            type="primary"
            target="_blank"
            rel="noopener noreferrer"
          >{{ row.url_or_handle }}</el-link>
          <span v-else>{{ row.url_or_handle }}</span>
        </template>
      </el-table-column>
```

- [ ] **Step 8: Run both source tests + full suite**

Run (from `admin/`): `npx vitest run tests/views/SuggestedSourcesView.test.js -t "renders url_or_handle as a link"`
Expected: PASS.
Run (from `admin/`): `npm test`
Expected: all 72 tests pass (70 + 2 new).

- [ ] **Step 9: Commit**

```bash
git add admin/src/views/SourcesView.vue admin/src/views/SuggestedSourcesView.vue admin/tests/views/SourcesView.test.js admin/tests/views/SuggestedSourcesView.test.js
git commit -m "feat(admin-ui): clickable website URLs in source tables"
```

---

### Task 8: Light table touches + browser visual verification

**Files:**
- Modify: `admin/src/styles/global.less` (light table header/hover touches)
- (No test file — verification via full suite + browser)

**Interfaces:** consumes tokens from Task 1.

- [ ] **Step 1: Add light table touches**

Append to `admin/src/styles/global.less` (after the existing rules):

```less
// Легкі теплі штрихи таблиць (не важкі override-и)
.el-table th.el-table__cell { background: @cream; }
.el-table tr:hover > td.el-table__cell { background: @bg; }
```

- [ ] **Step 2: Run the full admin suite**

Run (from `admin/`): `npm test`
Expected: all 72 tests pass.

- [ ] **Step 3: Browser visual verification**

Start the dev server (from `admin/`): `npm run dev`. In the browser check, at minimum:
- Login page: light bg, cream card, amber "Увійти" button, UAF Memory heading.
- After login: white sidebar with thin divider, amber "UBD" logo in UAF Memory, amber active-nav indicator.
- Offers/Moderation table: amber primary buttons, semantic status tags (published=success/green, pending=warning, rejected=danger), a clickable "Сайт ↗" link that opens the source in a new tab, cream table header.
- Sources / Suggested sources: website rows show a clickable URL; social handles show plain text.
- Forms/dialogs (offer form, source dialog): amber focus rings and primary buttons; body text stays system-ui and readable.

Record what was checked. If a surface looks off, fix the relevant Task's styles and re-verify.

- [ ] **Step 4: Commit**

```bash
git add admin/src/styles/global.less
git commit -m "feat(admin-ui): light table header/hover touches"
```

---

## Self-Review

**Spec coverage:**
- A. Tokens → Task 1. ✓
- B. Font (headings only) → Task 2 + applied in Tasks 4/5. ✓
- C. public 800→900 → Task 3. ✓
- D. Chrome (AdminLayout + LoginView) → Tasks 4, 5. ✓
- E. Clickable links (offers/moderation + sources) → Tasks 6, 7. ✓
- F. Light table touches → Task 8. ✓
- Semantic statuses untouched → guaranteed by only overriding `--el-color-primary*` in Task 1; verified in Task 8 browser check. ✓
- All 8 views styled via theme → automatic (Task 1 CSS vars); bespoke surfaces hand-styled (Tasks 4/5). ✓

**Placeholder scan:** No TBD/TODO; all code blocks concrete; every step has exact command + expected output.

**Type consistency:** Token names identical across Tasks 1/2/4/5 (`@brand @surface @cream @divider @nav-muted @meta-muted @heading-weight @sidebar-width @bg @text`). `el-link` attribute set (`:href`, `type`, `target`, `rel`) identical across Tasks 6/7. Test count progression 69→70 (Task 6)→72 (Task 7) consistent.

**Note for implementer (article_url):** admin `OFFER_TYPES` = discount/event only (no "news" type); `site_url`/`article_url` are independent optional fields — the offers column renders whichever is present, not gated by type.
