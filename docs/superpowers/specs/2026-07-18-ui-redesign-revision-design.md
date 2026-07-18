# Ревізія обох фронтів — дизайн (spec)

**Дата:** 2026-07-18. Гілка: `feat/ui-redesign-revision` (від `main`, HEAD `de38a78`).
**Вхід:** аудит `docs/superpowers/specs/2026-07-18-both-fronts-revision-audit.md` + рішення користувача.

## Мета

Закрити знахідки аудиту когерентності+a11y обох фронтів (public `public/`, admin `admin/`)
і дорестайлити прості public-хвости під новий світлий бурштиновий стиль. Головний драйвер —
**контраст WCAG 2.1 AA** (системні провали muted-токенів і амбера-як-тексту) + видимі focus-стани.

## Скоуп (4 батчі)

Поза скоупом: backend/API/crawler; логіка компонентів; нові роути/сторінки; static-nav
«Оффери · Про нас» лишається як є (рішення користувача — не робити лінком).

### Батч 1 — контраст-токени (public + admin, дзеркально)

Джерело істини — `public/src/styles/variables.less`; `admin/src/styles/variables.less` дзеркалить.
Усі заміни перевірені = AA (див. аудит).

- `@nav-muted` `#8A8578` → **`#6E6A5E`** (5.17 на bg, 5.40 на white).
- `@meta-muted` `#7E7768` → **`#6A6355`** (5.28 на cream, 5.70 на bg). Збігається з `@desc-muted` —
  лишаємо обидва токени з однаковим значенням (не зливаємо імена, щоб не чіпати посилання).
- `@placeholder` `#9A9382` → **`#736D58`** (≈4.6 на cream; наразі 2.71).
- **Амбер-як-ТЕКСТ → `@link` `#8A5A1E`** (5.23 на cream, 5.65 на bg):
  - public: `base.less` глобальний `a { color: @brand }` → `a { color: @link }`.
  - admin: спершу **додати токен `@link: #8A5A1E`** у `admin/src/styles/variables.less` (дзеркало public,
    зараз відсутній). Тоді активний пункт сайдбару (`AdminLayout.vue` `.sidebar nav a.router-link-active`) —
    текст і `border-left` з `@brand` → `@link`. (Фон активного лишається `@cream`.)
- **Амбер `@brand` як ЗАЛИВКА/РАМКА/БЕЙДЖ — НЕ чіпаємо** (badge-и, filters-count, primary-кнопки,
  логотип «УБД») — там контраст ок або це логотип-акцент.
- **Логотип «УБД» лишається амбер** (`SiteHeader.vue` `.brand b`, admin `.logo`) — рішення користувача;
  WCAG виключає логотипи/назви бренду з вимог контрасту.

Admin: `@nav-muted` вживається в `AdminLayout` для неактивних nav — теж отримає темніше значення.

### Батч 2 — focus-стилі (обидва фронти)

Немає видимих `:focus-visible` ніде (WCAG 2.4.7). Додати спільний помітний стиль.

- public: у `base.less` — `a, button, select, input, [tabindex]:not([tabindex="-1"]) { &:focus-visible {
  outline: 2px solid @dark; outline-offset: 2px; } }` (або еквівалент без вкладеності). Це покриває
  `.btn`, `.filters__trigger`, `.card__link`, кнопки Pagination, лінки хедера/футера, select/input фільтрів.
- admin: Element Plus має власні focus-стилі для своїх компонентів. Кастомний сайдбар —
  `.sidebar nav a:focus-visible { outline: 2px solid @dark; outline-offset: 2px; }` (у scoped-стилях
  `AdminLayout.vue`). Логотип-лінк — так само якщо фокусований.
- Outline-колір `@dark` (`#211D16`) видимий і на світлому фоні, і на кремі.

### Батч 3 — public-хвости

- **C1. Колір помилки → теракота.** `@danger` `#b00020` → **`#C0492B`** (4.75 AA, бренд-палітра).
  Впливає: `OfferGrid.vue` `.state--error`, admin-alias `@danger` (admin `variables.less` має `@danger`?
  — ні; admin використовує EP; тож зміна лише в public). Public `variables.less` має `@danger` (alias);
  оновити його значення.
- **C2. Токен `@radius-sm`.** Додати `@radius-sm: 8px` у public `variables.less` (і в admin для паритету).
  Замінити хардкод `8px` radius у public `.btn`/`.filters__trigger`/`.filters__panel select|input`/
  `Pagination .btn` на `@radius-sm`. (Картки/панелі лишаються `@radius` 12px.)
- **C3. Рестайл Pagination.** `Pagination.vue` `.btn`: додати hover-стан (`background: @cream;
  border-color: @link;`) для не-disabled; лишити `:disabled { opacity:.5 }`; radius → `@radius-sm`;
  `:focus-visible` з батчу 2. Мітка сторінки — `@meta-muted` (уже темніший після батчу 1).
- **C4. Стани OfferGrid у панелі.** `OfferGrid.vue`: loading/empty/error — обгорнути у делікатну
  панель (`background: @cream; border: 1px solid @divider; border-radius: @radius; padding: 28px;
  text-align:center`) замість голого `<p>`. Error-текст — `@danger` (теракота). Зберегти тексти й
  `v-if/else` логіку незмінними.
- **C5. Вага h1 OffersView.** `OffersView.vue` `.offers__head h1` — `font-weight: 700` (зараз успадковує
  400; UAF Memory Bold 700 існує). Ієрархія відносно карток (900).

### Батч 4 — дрібний a11y

- **B2. `alt` = назва провайдера.** `OfferCard.vue:24` `alt=""` → `:alt="offer.provider"`; те саме в
  `OfferDetailView.vue:57` (`:alt="offer.provider"`). (Провайдер завжди присутній — герой картки.)
- **B4a. Filters disclosure.** `OfferFilters.vue` тригер: `:aria-expanded="open"` + `aria-controls="filters-panel"`;
  панелі додати `id="filters-panel"`.
- **B4b. Pagination `aria-label`.** `Pagination.vue` `<nav>` → `aria-label="Пагінація"`.
- Static-nav «Оффери · Про нас» — **без змін** (рішення користувача); його контраст усе одно виправлено батчем 1.

## Тестування

- Public Vitest-набір зелений (52) — стилі/атрибути, логіка не змінюється. Нові фокусні тести:
  - `alt` = provider на OfferCard (B2); `aria-expanded`/`aria-controls` на фільтрах (B4a);
    Pagination `aria-label` (B4b); OfferGrid error/empty/loading рендерять текст у панелі (C4).
- Admin Vitest-набір зелений (77) — зміни лише токени/scoped-стилі AdminLayout; існуючі тести не
  зачеплені (текст/видимість). Нових тестів для чистих стилів нема.
- Контроль контрасту: значення вже пораховані в аудиті (усі AA).
- Браузерна перевірка: обидва фронти — muted-текст читабельний, амбер-лінки темні, focus-ring видимий
  (Tab), Pagination hover, стани OfferGrid у панелі, alt присутній (DOM).

## Метод

spec → план (writing-plans) → subagent-driven → фінал-review → finishing-a-development-branch (merge у main).

## Відкриті рішення — усі закриті
- Лого «УБД»: лишити амбер (рекомендація прийнята). alt: назва провайдера. Static-nav: лишити як є.
  Обсяг: усі 4 батчі.
