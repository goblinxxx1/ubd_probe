# UI-редизайн публічного сайту — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перевести публічний фронтенд (`public/`) зі старої синьо-білої палітри на світлий мінімалізм із бурштиновим акцентом і шрифтом UAF Memory, за спекою `docs/superpowers/specs/2026-07-16-ui-redesign-public-design.md`.

**Architecture:** Зміни ізольовані у `public/`: спершу оновлюємо дизайн-токени (`variables.less`), далі покомпонентно — бейдж, картка (переструктурування), хедер/фільтри/футер, сторінка-деталь. Логіка й API не змінюються; більшість наявних тестів поведінкові й лишаються зеленими, кілька доповнюємо під нову структуру. Бекенд і crawler не чіпаємо.

**Tech Stack:** Vue 3 (Composition API, чистий JavaScript), Vite, Less (без UI-бібліотеки), Vitest + @vue/test-utils.

## Global Constraints

- Гілка: `feat/ui-redesign` (вже створена від `main`).
- Скоуп: тільки `public/`. Бекенд/crawler/адмінка — поза скоупом.
- Шрифт `"UAF Memory"` — уже підключений (`public/src/styles/fonts.less`), окремо не додавати.
- Логіку `offerBadge()` у `public/src/utils/format.js` **не змінювати** (тільки стилі бейджа).
- Мапінг полів (інверсія): `provider`=герой, `title`=текст біля бейджа, `description`=блок опису, `target_categories`=чипи «Для кого», `offer_categories`+`location`=футер-мета.
- Клас `card__link` на посиланнях джерел **зберегти** (наявні тести на нього спираються).
- Фото на картці: `offer.image_url` з фолбеком `placeholderDataUri(offer)`; невеликий thumbnail `border-radius:9px`, висота прив'язана до рядка героя (~24–26px), не звисає нижче тексту.
- Усі команди виконувати з теки `public/`.
- Ціль тестів: зелений Vitest без регресій (наразі 43 passed).

---

### Task 1: Дизайн-токени (палітра)

**Files:**
- Modify: `public/src/styles/variables.less` (повна заміна)

**Interfaces:**
- Produces: Less-змінні `@bg @header-bg @text @brand @card-bg @card-border @radius @divider @nav-muted @meta-muted @desc-muted @placeholder @whom-bg @whom-border @chip-bg @chip-text @link @dark @badge-discount-bg @badge-discount-text @badge-free-bg @badge-free-text @badge-event-bg @badge-event-text` + сумісні аліаси `@muted @border @danger @bp-mobile @maxw` (щоб не зламати компоненти, які не чіпаємо: `OfferGrid`, `Pagination`, `NotFoundView`, `OffersView`).

- [ ] **Step 1: Замінити вміст `public/src/styles/variables.less`**

```less
// UI-редизайн — світлий мінімалізм, бурштиновий акцент
@bg: #FAFAF9;            // тло сайту
@header-bg: #FFFFFF;     // тло хедера
@text: #14110A;         // основний текст
@brand: #E0982A;        // бурштин (primary)
@card-bg: #F5F1E8;      // крем-картка
@card-border: #2A2620;  // темна рамка картки (2px)
@radius: 12px;
@divider: #E7E5E0;      // тонкі лінії
@nav-muted: #8A8578;    // навігація
@meta-muted: #7E7768;   // футер-мета, лейбли
@desc-muted: #6A6355;   // текст опису
@placeholder: #9A9382;  // курсивний [опис]
@whom-bg: #EBE5D6;      // панель «для кого»
@whom-border: #D6CDB9;
@chip-bg: #2A2620;      // чипи категорій
@chip-text: #F3EFE4;
@link: #8A5A1E;         // посилання «Сайт →»
@dark: #211D16;         // активні фільтри, бейдж події

// Badge
@badge-discount-bg: #E0982A;
@badge-discount-text: #221806;
@badge-free-bg: #DDE7D5;
@badge-free-text: #221806;
@badge-event-bg: #211D16;
@badge-event-text: #E0982A;

// Сумісні аліаси (компоненти, які не переписуємо)
@muted: @meta-muted;
@border: @divider;
@danger: #b00020;
@bp-mobile: 640px;
@maxw: 1100px;
```

- [ ] **Step 2: Прогнати весь тест-набір — переконатися, що Less компілюється й немає регресій**

Run: `npm run test`
Expected: PASS (усі наявні тести зелені; зміна значень токенів не впливає на поведінкові перевірки).

- [ ] **Step 3: Commit**

```bash
git add public/src/styles/variables.less
git commit -m "feat(public-ui): new light/amber design tokens"
```

---

### Task 2: Бейдж (`OfferBadge`) — стилі + вертикальне центрування

**Files:**
- Modify: `public/src/components/OfferBadge.vue` (тільки `<style>`)
- Test: `public/tests/components/OfferBadge.test.js`

**Interfaces:**
- Consumes: `offerBadge(offer)` → `{ text, kind }`, kind ∈ `discount|free|event` (без змін).
- Produces: `<span class="badge badge--{kind}">` з вертикально центрованим текстом.

- [ ] **Step 1: Додати failing-тест на бейдж «безкоштовно»**

У `public/tests/components/OfferBadge.test.js` додати всередині `describe`:

```js
  it("renders free badge", () => {
    const w = mount(OfferBadge, { props: { offer: { type: "discount", discount_type: "free" } } });
    expect(w.text()).toBe("Безкоштовно");
    expect(w.get("span").classes()).toContain("badge--free");
  });
```

- [ ] **Step 2: Прогнати тест бейджа — переконатися, що новий проходить, а решта не зламана**

Run: `npx vitest run tests/components/OfferBadge.test.js`
Expected: PASS (логіка `offerBadge` вже повертає `kind:"free"` для `discount_type:"free"`).

- [ ] **Step 3: Замінити `<style scoped>` у `public/src/components/OfferBadge.vue`**

```html
<style scoped lang="less">
@import "@/styles/variables.less";
.badge {
  display: inline-flex; align-items: center; justify-content: center;
  padding: 3px 9px; border-radius: 5px;
  font-size: 13px; font-weight: 800; line-height: 1; letter-spacing: -.2px;
}
.badge--discount { background: @badge-discount-bg; color: @badge-discount-text; }
.badge--free { background: @badge-free-bg; color: @badge-free-text; }
.badge--event { background: @badge-event-bg; color: @badge-event-text; }
</style>
```

(Вертикальне центрування — через `inline-flex; align-items:center; line-height:1`.)

- [ ] **Step 4: Прогнати тести бейджа**

Run: `npx vitest run tests/components/OfferBadge.test.js`
Expected: PASS (3 тести: event, percent, free).

- [ ] **Step 5: Commit**

```bash
git add public/src/components/OfferBadge.vue public/tests/components/OfferBadge.test.js
git commit -m "feat(public-ui): restyle badge (amber/sage/dark, centered text)"
```

---

### Task 3: Картка оффера (`OfferCard`) — переструктурування

**Files:**
- Modify: `public/src/components/OfferCard.vue` (повний перепис template + style; script майже без змін, +`meta`)
- Test: `public/tests/components/OfferCard.test.js`

**Interfaces:**
- Consumes: `placeholderDataUri(offer)`, `<OfferBadge :offer>`.
- Produces: DOM-структура з `.card__provider` (RouterLink→`offer`), `.card__photo` (`<img>`), `.card__dtext`, `.card__desc`/`.card__desc-empty`, `.card__whom` (умовно), `.chip`, `.card__meta`, `.card__link`.

- [ ] **Step 1: Оновити/доповнити тести картки**

Замінити вміст `public/tests/components/OfferCard.test.js` на:

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
  it("uses the placeholder photo when image_url is empty and shows fields", () => {
    const w = mountCard({
      id: 3, type: "discount", discount_type: "free", title: "на все меню",
      provider: "Музей", description: "", location: "Львів", image_url: null,
      target_categories: [{ id: 1, name: "УБД" }], offer_categories: [{ id: 2, name: "Кафе" }],
    });
    const src = w.get("img.card__photo").attributes("src");
    expect(src.startsWith("data:image/svg+xml,")).toBe(true);
    expect(w.text()).toContain("на все меню");
    expect(w.text()).toContain("Музей");
    expect(w.text()).toContain("УБД");
  });

  it("provider links to the offer detail route; photo uses image_url", () => {
    const w = mountCard({ id: 9, type: "event", title: "Подія", provider: "X", description: "d", image_url: "https://x/y.png", target_categories: [] });
    const link = w.getComponent({ name: "RouterLink" });
    expect(link.props("to")).toEqual({ name: "offer", params: { id: 9 } });
    expect(w.get("img.card__photo").attributes("src")).toBe("https://x/y.png");
  });

  it("shows the description when present", () => {
    const w = mountCard({ id: 4, type: "discount", title: "T", provider: "P", description: "Крафтова бургерна", image_url: null, target_categories: [] });
    expect(w.text()).toContain("Крафтова бургерна");
    expect(w.find(".card__desc-empty").exists()).toBe(false);
  });

  it("shows the [опис] placeholder when description is empty", () => {
    const w = mountCard({ id: 4, type: "discount", title: "T", provider: "P", description: "", image_url: null, target_categories: [] });
    expect(w.get(".card__desc-empty").text()).toBe("[опис]");
  });

  it("hides the «Для кого» panel when there are no target categories", () => {
    const w = mountCard({ id: 4, type: "discount", title: "T", provider: "P", description: "d", image_url: null, target_categories: [] });
    expect(w.find(".card__whom").exists()).toBe(false);
  });

  it("renders Сайт + Новина links when present", () => {
    const w = mountCard({
      id: 1, type: "discount", title: "T", provider: "Кафе", description: "d",
      site_url: "https://cafe.example", article_url: "https://cafe.example/news",
      image_url: null, target_categories: [],
    });
    const hrefs = w.findAll("a.card__link").map((a) => a.attributes("href"));
    expect(hrefs).toContain("https://cafe.example");
    expect(hrefs).toContain("https://cafe.example/news");
  });

  it("omits links when absent", () => {
    const w = mountCard({
      id: 2, type: "discount", title: "T", provider: "Кафе", description: "d",
      site_url: null, article_url: null, image_url: null, target_categories: [],
    });
    expect(w.findAll("a.card__link").length).toBe(0);
  });

  it("renders a link pair per offer_link source", () => {
    const w = mountCard({
      id: 5, type: "discount", title: "T", provider: "X", description: "d", image_url: null,
      target_categories: [],
      links: [
        { provider: "Agg1", site_url: "https://agg1", article_url: "https://agg1/p" },
        { provider: "Agg2", site_url: "https://agg2", article_url: "https://agg2/p" },
      ],
    });
    const hrefs = w.findAll("a.card__link").map((a) => a.attributes("href"));
    expect(hrefs).toContain("https://agg1");
    expect(hrefs).toContain("https://agg2");
    expect(hrefs).toContain("https://agg1/p");
    expect(hrefs).toContain("https://agg2/p");
  });
});
```

- [ ] **Step 2: Прогнати тести картки — переконатися, що падають (нова структура ще не реалізована)**

Run: `npx vitest run tests/components/OfferCard.test.js`
Expected: FAIL (напр. `.card__desc-empty` / `img.card__photo` не знайдено).

- [ ] **Step 3: Переписати `public/src/components/OfferCard.vue`**

```html
<script setup>
import { computed } from "vue";
import { placeholderDataUri } from "@/utils/placeholder";
import OfferBadge from "@/components/OfferBadge.vue";

const props = defineProps({ offer: { type: Object, required: true } });
const image = computed(() => props.offer.image_url || placeholderDataUri(props.offer));
const sourceLinks = computed(() =>
  props.offer.links?.length
    ? props.offer.links
    : (props.offer.site_url || props.offer.article_url
        ? [{ site_url: props.offer.site_url, article_url: props.offer.article_url }]
        : [])
);
const meta = computed(() =>
  [props.offer.offer_categories?.[0]?.name, props.offer.location].filter(Boolean).join(" · ")
);
</script>

<template>
  <div class="card">
    <div class="card__top">
      <router-link class="card__provider" :to="{ name: 'offer', params: { id: offer.id } }">{{ offer.provider }}</router-link>
      <img class="card__photo" :src="image" alt="" />
    </div>

    <div class="card__discount">
      <OfferBadge :offer="offer" />
      <span v-if="offer.title" class="card__dtext">{{ offer.title }}</span>
    </div>

    <p class="card__desc">
      <template v-if="offer.description">{{ offer.description }}</template>
      <span v-else class="card__desc-empty">[опис]</span>
    </p>

    <div v-if="offer.target_categories?.length" class="card__whom">
      <div class="card__whom-label">Для кого</div>
      <div class="card__chips">
        <span v-for="t in offer.target_categories" :key="t.id" class="chip">{{ t.name }}</span>
      </div>
    </div>

    <div class="card__foot">
      <span class="card__meta">{{ meta }}</span>
      <span v-if="sourceLinks.length" class="card__links">
        <template v-for="(l, i) in sourceLinks" :key="i">
          <a v-if="l.site_url" class="card__link" :href="l.site_url"
             target="_blank" rel="noopener">Сайт{{ sourceLinks.length > 1 ? ' ' + (i + 1) : '' }}</a>
          <a v-if="l.article_url" class="card__link" :href="l.article_url"
             target="_blank" rel="noopener">Новина{{ sourceLinks.length > 1 ? ' ' + (i + 1) : '' }}</a>
        </template>
      </span>
    </div>
  </div>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.card {
  display: flex; flex-direction: column;
  background: @card-bg; border: 2px solid @card-border; border-radius: @radius;
  padding: 14px; color: @text;
}
.card__top { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.card__provider {
  font-weight: 800; font-size: 24px; line-height: .95; letter-spacing: -.3px; color: @text;
}
.card__provider:hover { text-decoration: none; color: @link; }
.card__photo {
  width: 26px; height: 26px; flex: none; object-fit: cover; border-radius: 9px;
}
.card__discount { display: flex; align-items: center; gap: 8px; margin-top: 10px; }
.card__dtext { font-size: 12px; }
.card__desc { font-size: 11.5px; line-height: 1.45; color: @desc-muted; margin: 10px 0 0; }
.card__desc-empty { color: @placeholder; font-style: italic; }
.card__whom {
  background: @whom-bg; border: 1px solid @whom-border; border-radius: 8px; padding: 7px 9px; margin-top: 11px;
}
.card__whom-label {
  font-size: 8px; text-transform: uppercase; letter-spacing: 1.5px; color: @meta-muted;
  font-weight: 700; margin-bottom: 5px;
}
.card__chips { display: flex; flex-wrap: wrap; gap: 4px; }
.chip {
  font-size: 10.5px; font-weight: 600; padding: 2px 8px; border-radius: 999px;
  background: @chip-bg; color: @chip-text;
}
.card__foot {
  display: flex; justify-content: space-between; align-items: center; gap: 8px;
  margin-top: 12px; padding-top: 10px; border-top: 1px solid @card-border;
}
.card__meta { font-size: 9.5px; text-transform: uppercase; letter-spacing: 1px; color: @meta-muted; }
.card__links { display: flex; gap: 10px; flex-wrap: wrap; }
.card__link { font-size: 11px; font-weight: 700; color: @link; }
</style>
```

- [ ] **Step 4: Прогнати тести картки**

Run: `npx vitest run tests/components/OfferCard.test.js`
Expected: PASS (усі 8 тестів).

- [ ] **Step 5: Commit**

```bash
git add public/src/components/OfferCard.vue public/tests/components/OfferCard.test.js
git commit -m "feat(public-ui): restructure offer card (provider hero, photo, whom panel)"
```

---

### Task 4: Хедер, фільтри, футер — рестайл

**Files:**
- Modify: `public/src/components/SiteHeader.vue`
- Modify: `public/src/components/SiteFooter.vue`
- Modify: `public/src/components/OfferFilters.vue` (тільки `<template>` бренду не стосується; тут — `<style>`)

**Interfaces:**
- Consumes: токени з Task 1.
- Produces: білий хедер із брендом «Знижки для **УБД**» (текст лишається «Знижки для УБД»), світлий футер, фільтри в новій палітрі. Поведінка фільтрів (`activeCount/apply/reset`, dropdown) — без змін.

- [ ] **Step 1: Переписати `public/src/components/SiteHeader.vue`**

```html
<script setup></script>

<template>
  <header class="site-header">
    <div class="container site-header__inner">
      <router-link :to="{ name: 'offers' }" class="brand">Знижки для <b>УБД</b></router-link>
      <nav class="nav">Оффери · Про нас</nav>
    </div>
  </header>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.site-header { background: @header-bg; border-bottom: 1px solid @divider; }
.site-header__inner { display: flex; align-items: center; justify-content: space-between; }
.brand { font-weight: 800; font-size: 19px; letter-spacing: -.3px; color: @text; }
.brand:hover { text-decoration: none; }
.brand b { color: @brand; }
.nav { font-size: 12px; color: @nav-muted; text-transform: uppercase; letter-spacing: 1.5px; }
</style>
```

(Навігація — статичний текст, як у мокапі; окремої сторінки «Про нас» немає, роути не додаємо — YAGNI.)

- [ ] **Step 2: Переписати `<style scoped>` у `public/src/components/SiteFooter.vue`** (template без змін)

```html
<style scoped lang="less">
@import "@/styles/variables.less";
.site-footer { border-top: 1px solid @divider; color: @meta-muted; margin-top: 32px; font-size: 13px; }
</style>
```

- [ ] **Step 3: Замінити `<style scoped>` у `public/src/components/OfferFilters.vue`** (script/template без змін)

```html
<style scoped lang="less">
@import "@/styles/variables.less";
.filters { position: relative; display: inline-block; }
.filters__trigger {
  padding: 6px 12px; border: 1px solid @divider; border-radius: 8px; background: @header-bg;
  cursor: pointer; font-size: 13px; color: @text; text-transform: uppercase; letter-spacing: .5px;
}
.filters__count { margin-left: 6px; background: @brand; color: @badge-discount-text; border-radius: 999px; padding: 0 7px; font-size: 12px; font-weight: 700; }
.filters__backdrop { position: fixed; inset: 0; z-index: 10; }
.filters__panel {
  position: absolute; z-index: 11; top: calc(100% + 6px); left: 0; width: min(320px, 90vw);
  background: @header-bg; border: 1px solid @divider; border-radius: @radius;
  box-shadow: 0 8px 28px rgba(0,0,0,0.10); padding: 14px; display: flex; flex-direction: column; gap: 10px;
}
.filters__panel label { display: flex; flex-direction: column; gap: 4px; font-size: 14px; color: @meta-muted; }
.filters__panel select, .filters__panel input { padding: 7px; border: 1px solid @divider; border-radius: 8px; font-size: 15px; color: @text; }
.filters__actions { display: flex; gap: 8px; margin-top: 4px; }
.btn { padding: 8px 12px; border: 1px solid @divider; border-radius: 8px; background: @header-bg; cursor: pointer; color: @text; }
.btn--primary { background: @dark; color: @chip-text; border-color: @dark; }
@media (max-width: @bp-mobile) {
  .filters { display: block; }
  .filters__panel { width: 100%; }
}
</style>
```

- [ ] **Step 4: Прогнати тести хедера/фільтрів і весь набір**

Run: `npm run test`
Expected: PASS (текст бренду лишився «Знижки для УБД»; поведінка фільтрів незмінна).

- [ ] **Step 5: Commit**

```bash
git add public/src/components/SiteHeader.vue public/src/components/SiteFooter.vue public/src/components/OfferFilters.vue
git commit -m "feat(public-ui): restyle header, footer, filters to light/amber"
```

---

### Task 5: Сторінка-деталь оффера (`OfferDetailView`)

**Files:**
- Modify: `public/src/views/OfferDetailView.vue`
- Test: `public/tests/views/OfferDetailView.test.js` (перевірити, доповнення за потреби)

**Interfaces:**
- Consumes: `offersApi.get`, `formatDate`, `<OfferBadge>`.
- Produces: `.detail__provider` (герой), `.detail__dtext`, `.detail__desc`, `.detail__whom`, `.detail__row`, посилання джерел. Фото `image_url` лише коли присутнє (без плейсхолдера).

- [ ] **Step 1: Переписати `public/src/views/OfferDetailView.vue`**

```html
<script setup>
import { ref, computed, onMounted } from "vue";
import { useRoute } from "vue-router";
import * as offersApi from "@/api/offers";
import { formatDate } from "@/utils/format";
import OfferBadge from "@/components/OfferBadge.vue";

const route = useRoute();
const offer = ref(null);
const loading = ref(true);
const notFound = ref(false);

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

const sourceLinks = computed(() => {
  const o = offer.value;
  if (!o) return [];
  if (o.links?.length) return o.links;
  return o.site_url || o.article_url
    ? [{ site_url: o.site_url, article_url: o.article_url }]
    : [];
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
      <router-link :to="{ name: 'offers' }" class="detail__back">← до списку</router-link>

      <div class="detail__head">
        <h1 class="detail__provider">{{ offer.provider }}</h1>
        <img v-if="offer.image_url" class="detail__photo" :src="offer.image_url" alt="" />
      </div>

      <div class="detail__discount">
        <OfferBadge :offer="offer" />
        <span v-if="offer.title" class="detail__dtext">{{ offer.title }}</span>
      </div>

      <p v-if="offer.description" class="detail__desc">{{ offer.description }}</p>

      <div v-if="offer.target_categories?.length" class="detail__whom">
        <div class="detail__whom-label">Для кого</div>
        <div class="detail__chips">
          <span v-for="t in offer.target_categories" :key="t.id" class="chip">{{ t.name }}</span>
        </div>
      </div>

      <div v-if="offer.offer_categories?.length" class="detail__row">
        <span class="detail__label">Тематика:</span>
        <span v-for="c in offer.offer_categories" :key="c.id" class="chip chip--light">{{ c.name }}</span>
      </div>
      <div v-if="offer.location" class="detail__row"><span class="detail__label">Локація:</span> {{ offer.location }}</div>
      <div v-if="period" class="detail__row"><span class="detail__label">Діє:</span> {{ period }}</div>
      <div v-for="(l, i) in sourceLinks" :key="i" class="detail__row">
        <span class="detail__label">Джерело{{ sourceLinks.length > 1 ? ' ' + (i + 1) : '' }}:</span>
        <a v-if="l.site_url" :href="l.site_url" target="_blank" rel="noopener">Сайт</a>
        <a v-if="l.article_url" :href="l.article_url" target="_blank" rel="noopener" style="margin-left:8px">Сторінка новини</a>
      </div>
    </article>
  </div>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.detail__back { display: inline-block; margin-bottom: 16px; color: @link; }
.detail__head { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; }
.detail__provider { margin: 0; font-weight: 800; font-size: 38px; line-height: .95; letter-spacing: -.5px; color: @text; }
.detail__photo { width: 40px; height: 40px; flex: none; object-fit: cover; border-radius: 9px; }
.detail__discount { display: flex; align-items: center; gap: 10px; margin: 14px 0; }
.detail__dtext { font-size: 14px; }
.detail__desc { line-height: 1.55; color: @desc-muted; margin: 0 0 16px; }
.detail__whom {
  background: @whom-bg; border: 1px solid @whom-border; border-radius: 8px; padding: 9px 11px; margin-bottom: 14px;
  display: inline-block;
}
.detail__whom-label { font-size: 9px; text-transform: uppercase; letter-spacing: 1.5px; color: @meta-muted; font-weight: 700; margin-bottom: 6px; }
.detail__chips { display: flex; flex-wrap: wrap; gap: 5px; }
.chip { font-size: 12px; font-weight: 600; padding: 2px 9px; border-radius: 999px; background: @chip-bg; color: @chip-text; }
.chip--light { background: @whom-bg; color: @meta-muted; border: 1px solid @whom-border; margin-right: 4px; }
.detail__row { margin: 8px 0; }
.detail__label { color: @meta-muted; margin-right: 6px; text-transform: uppercase; font-size: 11px; letter-spacing: .5px; }
.state { text-align: center; padding: 48px 0; color: @meta-muted; }
</style>
```

- [ ] **Step 2: Прогнати тест деталі**

Run: `npx vitest run tests/views/OfferDetailView.test.js`
Expected: PASS (наявний тест перевіряє текст `title`/`provider`, hrefs джерел і дату `01.07.2026` — усе рендериться; `image_url:null` → фото не показуємо, тест його й не перевіряє).

- [ ] **Step 3: Commit**

```bash
git add public/src/views/OfferDetailView.vue public/tests/views/OfferDetailView.test.js
git commit -m "feat(public-ui): restyle offer detail view (provider hero, whom panel)"
```

---

### Task 6: Наскрізна перевірка (тести + браузер)

**Files:** (немає нових; лише за потреби дрібні правки)

- [ ] **Step 1: Прогнати повний тест-набір**

Run: `npm run test`
Expected: PASS — усі тести зелені (наразі 43; після Task 3 їх трохи більше). Якщо щось червоне — виправити відповідний компонент/тест і повторити.

- [ ] **Step 2: Запустити dev-сервер і перевірити візуально**

Run: `npm run dev` (Vite :5174; бекенд на :8000 для реальних даних — за наявності; інакше перевірити верстку на порожньому/мок-стані).
Перевірити вручну в браузері:
- Лістинг: білий хедер із бурштиновим «УБД», майже білий фон, кремові картки з темною рамкою; герой-провайдер великий; фото — маленький thumbnail зверху справа, не звисає нижче тексту; бейджі (−%, «Безкоштовно» шавлієвий, «Подія» темний) з центрованим текстом; панель «Для кого»; футер-мета + посилання.
- Деталь: великий герой-провайдер, опис, бейдж+текст, панель «Для кого», категорії/локація/дати, усі джерела-посилання.
- Фільтри: пігулка-тригер, панель у новій палітрі, primary-кнопка темна.

- [ ] **Step 3: Commit (лише якщо були візуальні правки)**

```bash
git add -A
git commit -m "fix(public-ui): visual polish after browser check"
```

---

## Self-Review

**1. Покриття спеки:**
- Токени → Task 1. ✓
- Картка (герой, фото-thumbnail, бейдж+title, опис/плейсхолдер, «Для кого», футер) → Task 3. ✓
- Бейдж (3 види, центрування, free шавлієвий) → Task 2. ✓
- Хедер/фільтри/футер → Task 4. ✓
- Сторінка-деталь → Task 5. ✓
- Тести + браузер → у кожному завданні + Task 6. ✓
- Бекенд/crawler/адмінка поза скоупом. ✓

**2. Плейсхолдери:** немає TBD/TODO; увесь код наведено повністю.

**3. Узгодженість типів/імен:** класи, що їх перевіряють тести (`card__link`, `card__photo`, `card__desc-empty`, `card__whom`, `badge--free`), збігаються між кодом і тестами; `offerBadge()` не змінюється; `placeholderDataUri`/`formatDate` — наявні утиліти.
