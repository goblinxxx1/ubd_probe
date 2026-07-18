# Both-Fronts Revision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the coherence + WCAG 2.1 AA accessibility findings across both frontends and restyle the plain public tails to the light amber design.

**Architecture:** Mostly token/CSS edits mirrored across `public/src/styles/variables.less` and `admin/src/styles/variables.less`; darken muted tokens and switch amber-as-text to the darker `@link`; add `:focus-visible`; recolor error to terracotta; add a `@radius-sm` token; restyle Pagination/OfferGrid states; and add a11y attributes (alt, aria) with focused tests.

**Tech Stack:** Vue 3 (`<script setup>`), Less, Element Plus ^2.7.0 (admin), Vitest + @vue/test-utils.

## Global Constraints

- No backend/API/crawler changes. No component logic changes, no new routes/pages.
- Color source of truth = `public/src/styles/variables.less`; `admin/src/styles/variables.less` mirrors shared tokens.
- All contrast replacement values are AA-verified (see audit `docs/superpowers/specs/2026-07-18-both-fronts-revision-audit.md`). Use these EXACT hex values:
  - `@nav-muted` → `#6E6A5E`; `@meta-muted` → `#6A6355`; `@placeholder` → `#736D58`; `@link` = `#8A5A1E`; `@danger`/error → `#C0492B`.
- Amber `@brand` `#E0982A` stays ONLY as fill/border/badge/logo — never as body/nav/link TEXT.
- Logo «УБД» / admin `.logo` stays amber (logotype exemption).
- `:focus-visible` outline = `2px solid @dark` (`#211D16`), `outline-offset: 2px`.
- Static header nav «Оффери · Про нас» stays as-is (no markup change).
- `@radius` (12px) stays for cards/panels; only small chrome uses `@radius-sm` (8px).
- Public Vitest suite green (52, → 56 after Task 5); admin Vitest suite green (77) throughout.
- Run public commands from `public/`; admin commands from `admin/`.

---

### Task 1: Public contrast tokens

**Files:**
- Modify: `public/src/styles/variables.less`
- Modify: `public/src/styles/base.less`

**Interfaces:** none (token value changes).

- [ ] **Step 1: Darken the three muted tokens**

In `public/src/styles/variables.less`, change exactly these three values (leave comments and other tokens intact):
- `@nav-muted: #8A8578;` → `@nav-muted: #6E6A5E;`
- `@meta-muted: #7E7768;` → `@meta-muted: #6A6355;`
- `@placeholder: #9A9382;` → `@placeholder: #736D58;`

(Do NOT change `@danger` here — that is Task 4.)

- [ ] **Step 2: Switch global link color from amber to @link**

In `public/src/styles/base.less`, line 7, change:
`a { color: @brand; text-decoration: none; }`
→ `a { color: @link; text-decoration: none; }`

- [ ] **Step 3: Run the public suite**

Run (from `public/`): `npm test`
Expected: 52 passed (styling only).

- [ ] **Step 4: Commit**

```bash
git add public/src/styles/variables.less public/src/styles/base.less
git commit -m "fix(public-ui): AA contrast — darken muted tokens, amber text -> @link"
```

---

### Task 2: Admin contrast tokens + active-nav

**Files:**
- Modify: `admin/src/styles/variables.less`
- Modify: `admin/src/layouts/AdminLayout.vue` (scoped `<style>` only)

**Interfaces:**
- Produces: `@link` token in admin (new), consumed by AdminLayout active-nav.

- [ ] **Step 1: Darken muted tokens + add @link**

In `admin/src/styles/variables.less`:
- `@nav-muted: #8A8578;` → `@nav-muted: #6E6A5E;`
- `@meta-muted: #7E7768;` → `@meta-muted: #6A6355;`
- Add a new line after `@dark: #211D16;`:
  `@link: #8A5A1E;         // темний бурштин для тексту-посилань (AA)`

- [ ] **Step 2: Active-nav amber text → @link**

In `admin/src/layouts/AdminLayout.vue`, in the scoped style, change the active-nav rule from:
`.sidebar nav a.router-link-active { color: @brand; background: @cream; border-left-color: @brand; }`
→
`.sidebar nav a.router-link-active { color: @link; background: @cream; border-left-color: @link; }`

(Leave `.logo` amber — logotype. Leave inactive `.sidebar nav a` using `@nav-muted` — now darker via Step 1. Do not touch script/template.)

- [ ] **Step 3: Run the admin suite**

Run (from `admin/`): `npm test`
Expected: 77 passed (AdminLayout tests assert text/visibility — unaffected).

- [ ] **Step 4: Commit**

```bash
git add admin/src/styles/variables.less admin/src/layouts/AdminLayout.vue
git commit -m "fix(admin-ui): AA contrast — darken muted tokens, active-nav -> @link"
```

---

### Task 3: Visible focus styles (both fronts)

**Files:**
- Modify: `public/src/styles/base.less`
- Modify: `admin/src/layouts/AdminLayout.vue` (scoped `<style>` only)

**Interfaces:** none (CSS).

- [ ] **Step 1: Public global focus-visible**

In `public/src/styles/base.less`, append after the existing `a:hover` rule (before `.container`):

```less
a:focus-visible,
button:focus-visible,
select:focus-visible,
input:focus-visible,
[tabindex]:not([tabindex="-1"]):focus-visible {
  outline: 2px solid @dark;
  outline-offset: 2px;
}
```

- [ ] **Step 2: Admin sidebar nav focus-visible**

In `admin/src/layouts/AdminLayout.vue` scoped style, add after the `.sidebar nav a.router-link-active` rule:

```less
.sidebar nav a:focus-visible { outline: 2px solid @dark; outline-offset: 2px; }
```

(Element Plus controls carry their own focus styles; only the custom sidebar links need this.)

- [ ] **Step 3: Run both suites**

Run (from `public/`): `npm test` → 52 passed.
Run (from `admin/`): `npm test` → 77 passed.

- [ ] **Step 4: Commit**

```bash
git add public/src/styles/base.less admin/src/layouts/AdminLayout.vue
git commit -m "feat(ui): visible :focus-visible outlines on custom controls"
```

---

### Task 4: Public tails restyle (terracotta, @radius-sm, Pagination, states, h1)

**Files:**
- Modify: `public/src/styles/variables.less`
- Modify: `public/src/components/Pagination.vue` (scoped `<style>`)
- Modify: `public/src/components/OfferFilters.vue` (scoped `<style>`)
- Modify: `public/src/components/OfferGrid.vue` (scoped `<style>`)
- Modify: `public/src/views/OffersView.vue` (scoped `<style>`)

**Interfaces:**
- Produces: `@radius-sm` token consumed by Pagination/OfferFilters.

- [ ] **Step 1: Error → terracotta + add @radius-sm token**

In `public/src/styles/variables.less`:
- `@danger: #b00020;` → `@danger: #C0492B;`
- Add after `@radius: 12px;`:
  `@radius-sm: 8px;        // дрібне chrome (кнопки, інпути, пагінація)`

- [ ] **Step 2: Pagination restyle**

In `public/src/components/Pagination.vue` scoped style, replace the `.btn` rules:
```less
.btn { padding: 8px 14px; border: 1px solid @border; border-radius: 8px; background: @bg; cursor: pointer; }
.btn:disabled { opacity: 0.5; cursor: default; }
```
with:
```less
.btn { padding: 8px 14px; border: 1px solid @border; border-radius: @radius-sm; background: @bg; cursor: pointer; color: @text; }
.btn:not(:disabled):hover { background: @cream; border-color: @link; }
.btn:disabled { opacity: 0.5; cursor: default; }
```

- [ ] **Step 3: OfferFilters — hardcoded 8px radius → @radius-sm**

In `public/src/components/OfferFilters.vue` scoped style, change the three `border-radius: 8px;` occurrences to `border-radius: @radius-sm;` (in `.filters__trigger`, in `.filters__panel select, .filters__panel input`, and in `.btn`). Leave `.filters__panel { border-radius: @radius; }` (12px) unchanged. Leave `.filters__count { border-radius: 999px; }` unchanged.

- [ ] **Step 4: OfferGrid states as a panel**

In `public/src/components/OfferGrid.vue` scoped style, replace:
```less
.state { color: @muted; padding: 32px 0; text-align: center; }
.state--error { color: @danger; }
```
with:
```less
.state {
  color: @meta-muted; text-align: center; padding: 28px;
  background: @card-bg; border: 1px solid @divider; border-radius: @radius;
}
.state--error { color: @danger; }
```
(Markup and text unchanged — the existing `<p class="state">` just gains panel styling.)

- [ ] **Step 5: OffersView h1 weight**

In `public/src/views/OffersView.vue` scoped style, change:
`.offers__head h1 { font-size: 24px; margin: 0; }`
→ `.offers__head h1 { font-size: 24px; margin: 0; font-weight: 700; }`

- [ ] **Step 6: Run the public suite**

Run (from `public/`): `npm test`
Expected: 52 passed (CSS/token only; OfferGrid text + Pagination behavior unchanged).

- [ ] **Step 7: Commit**

```bash
git add public/src/styles/variables.less public/src/components/Pagination.vue public/src/components/OfferFilters.vue public/src/components/OfferGrid.vue public/src/views/OffersView.vue
git commit -m "feat(public-ui): terracotta error, @radius-sm, pagination/states restyle, h1 weight"
```

---

### Task 5: a11y attributes — alt + aria (TDD)

**Files:**
- Modify: `public/src/components/OfferCard.vue` (template)
- Modify: `public/src/views/OfferDetailView.vue` (template)
- Modify: `public/src/components/OfferFilters.vue` (template)
- Modify: `public/src/components/Pagination.vue` (template)
- Test: `public/tests/components/OfferCard.test.js`, `public/tests/views/OfferDetailView.test.js`, `public/tests/components/OfferFilters.test.js`, `public/tests/components/Pagination.test.js`

**Interfaces:** none (presentational attributes).

- [ ] **Step 1: Write failing tests**

Add to `public/tests/components/OfferCard.test.js` (inside `describe`):
```javascript
  it("sets the photo alt to the provider name", () => {
    const w = mountCard({ id: 7, type: "discount", title: "T", provider: "Кав'ярня Львів", description: "d", image_url: null, target_categories: [] });
    expect(w.get("img.card__photo").attributes("alt")).toBe("Кав'ярня Львів");
  });
```

Add to `public/tests/views/OfferDetailView.test.js` (inside `describe`):
```javascript
  it("sets the detail photo alt to the provider name", async () => {
    offers.get.mockResolvedValue({
      id: 8, type: "discount", discount_type: "percent", discount_value: 10,
      title: "T", provider: "Салон Краси", description: "d", location: "Київ",
      valid_from: "2026-07-01", valid_until: "2026-08-01",
      image_url: "https://x/y.png", target_categories: [], offer_categories: [],
    });
    const w = await mountAt(8);
    expect(w.get("img.detail__photo").attributes("alt")).toBe("Салон Краси");
  });
```

Add to `public/tests/components/OfferFilters.test.js` (inside `describe`):
```javascript
  it("reflects open state via aria-expanded and links the panel via aria-controls", async () => {
    const w = mountFilters({});
    const trigger = w.get(".filters__trigger");
    expect(trigger.attributes("aria-expanded")).toBe("false");
    expect(trigger.attributes("aria-controls")).toBe("filters-panel");
    w.vm.open = true;
    await w.vm.$nextTick();
    expect(w.get(".filters__trigger").attributes("aria-expanded")).toBe("true");
    expect(w.get("#filters-panel").exists()).toBe(true);
  });
```

Add to `public/tests/components/Pagination.test.js` (inside `describe`):
```javascript
  it("labels the pagination nav", () => {
    const w = mount(Pagination, { props: { total: 40, size: 12, page: 1 } });
    expect(w.get("nav.pagination").attributes("aria-label")).toBe("Пагінація");
  });
```

- [ ] **Step 2: Run tests to confirm they fail**

Run (from `public/`): `npx vitest run tests/components/OfferCard.test.js tests/views/OfferDetailView.test.js tests/components/OfferFilters.test.js tests/components/Pagination.test.js -t "alt|aria|labels the pagination"`
Expected: the 4 new tests FAIL (attributes not present yet).

- [ ] **Step 3: OfferCard photo alt**

In `public/src/components/OfferCard.vue`, line 24, change:
`<img class="card__photo" :src="image" alt="" />`
→ `<img class="card__photo" :src="image" :alt="offer.provider" />`

- [ ] **Step 4: OfferDetailView photo alt**

In `public/src/views/OfferDetailView.vue`, line 57, change:
`<img v-if="offer.image_url" class="detail__photo" :src="offer.image_url" alt="" />`
→ `<img v-if="offer.image_url" class="detail__photo" :src="offer.image_url" :alt="offer.provider" />`

- [ ] **Step 5: OfferFilters aria (disclosure)**

In `public/src/components/OfferFilters.vue`:
- Change the trigger button opening tag:
  `<button class="filters__trigger" @click="open = !open">`
  → `<button class="filters__trigger" :aria-expanded="open" aria-controls="filters-panel" @click="open = !open">`
- Add `id="filters-panel"` to the panel div:
  `<div v-if="open" class="filters__panel">`
  → `<div v-if="open" id="filters-panel" class="filters__panel">`

- [ ] **Step 6: Pagination nav aria-label**

In `public/src/components/Pagination.vue`, change:
`<nav v-if="totalPages > 1" class="pagination">`
→ `<nav v-if="totalPages > 1" class="pagination" aria-label="Пагінація">`

- [ ] **Step 7: Run the new tests, then the full suite**

Run (from `public/`): `npx vitest run tests/components/OfferCard.test.js tests/views/OfferDetailView.test.js tests/components/OfferFilters.test.js tests/components/Pagination.test.js -t "alt|aria|labels the pagination"`
Expected: 4 new tests PASS.
Run (from `public/`): `npm test`
Expected: 56 passed (52 + 4 new).

- [ ] **Step 8: Commit**

```bash
git add public/src/components/OfferCard.vue public/src/views/OfferDetailView.vue public/src/components/OfferFilters.vue public/src/components/Pagination.vue public/tests/components/OfferCard.test.js public/tests/views/OfferDetailView.test.js public/tests/components/OfferFilters.test.js public/tests/components/Pagination.test.js
git commit -m "feat(public-ui): a11y — provider alt text, filters aria, pagination aria-label"
```

---

## Self-Review

**Spec coverage:**
- Batch 1 (contrast tokens): public → Task 1, admin (+@link, active-nav) → Task 2. ✓
- Batch 2 (focus-visible): Task 3. ✓
- Batch 3 (terracotta, @radius-sm, Pagination, OfferGrid states, h1): Task 4. ✓
- Batch 4 (alt=provider, filters aria, pagination aria-label): Task 5. ✓
- Static-nav left as-is: no task touches SiteHeader.vue. ✓
- Logo stays amber: no task changes `.brand b` / admin `.logo`. ✓

**Placeholder scan:** No TBD/TODO; every step has exact edits + commands + expected output.

**Type/name consistency:** Hex values match Global Constraints across tasks (`#6E6A5E`, `#6A6355`, `#736D58`, `#8A5A1E`, `#C0492B`). `@radius-sm` defined in Task 4 Step 1 before use in Steps 2–3. `@link` added to admin in Task 2 Step 1 before use in Step 2. `#filters-panel` id matches between OfferFilters template (Task 5 Step 5) and its test/aria-controls. Test-count progression 52→56 (public), admin stays 77.

**Note (implementer):** `@muted` alias — public `variables.less` defines `@muted: @meta-muted;`; OfferGrid Step 4 replaces `@muted` usage with `@meta-muted` directly (both resolve to `#6A6355` after Task 1); harmless and explicit.
