# Admin UX: top pagination + return-to-origin + live moderation badge

**Дата:** 2026-08-03
**Гілка:** `feat/admin-pagination-nav-badge` (від `main`)
**Тип:** admin-only (Vue 3 + Element Plus). Backend/crawler не змінюються.

## Проблема / три задачі

1. **Пагінація лише знизу.** `el-pagination` є тільки в `OffersListView.vue` (обслуговує «Оффери» і «Черга модерації» через `ModerationQueueView`). Довгі списки незручно гортати — потрібен другий бар пагінації **над** списком.
2. **Редагування завжди повертає в «Оффери».** `OfferFormView` після save/publish/cancel робить `router.push({name:'offers'})`, тож із «Черги модерації» (чи з вкладки «Відхилені») викидає не туди. Має повертати в **той самий розділ і вкладку**.
3. **Badge модерації не оновлюється.** `AdminLayout` вантажить `pendingCount` один раз `onMounted`; після publish/delete/reject/restore лічильник у меню стає застарілим до перезавантаження сторінки.

## Рішення

### Задача 1 — Пагінація зверху
Додати другий `<el-pagination>` **над** `<ResponsiveTable>` (після `DataTableToolbar`) у `OffersListView.vue`, з тими самими прив'язками: `:total="total" :page-size="size" :current-page="page" @current-change="setPage"`. Обидва бари синхронні через спільний `page`/`total` з `useApiList` (нижній лишається).

### Задача 2 — Повернення в розділ + вкладку
- **Вкладка в URL.** `OffersListView` ініціалізує `tab` з `route.query.tab` (дефолт `"published"`). Зміна вкладки, окрім `applyFilters({})`, робить `router.replace({ query: { ...route.query, tab } })` — без ремаунту, лише для розділу «Оффери» (у «Черзі» вкладок нема, `fixedStatus`).
- **Передача походження.** `edit(id)` і кнопка «Створити оффер» додають `query: { from: route.name, tab: tab.value }` (tab лише коли не `fixedStatus`).
- **Повернення.** `OfferFormView` на `onSubmit`/`onSubmitPublish`/`cancel` йде в `{ name: route.query.from || 'offers', query: route.query.tab ? { tab: route.query.tab } : {} }`.

### Задача 3 — Живий badge модерації
- Новий Pinia-стор `stores/moderation.js`: state `pendingCount`, action `refresh()` → `offers.list({status:'pending_review', size:1})` → `pendingCount = result.total`. Помилку ковтати (badge некритичний).
- `AdminLayout`: `onMounted` → `store.refresh()`; badge прив'язаний до `store.pendingCount`.
- `OffersListView`: після `onPublish`/`onReject`/`onDelete`/`onRestore` (після `await load()`) викликати `store.refresh()` → badge оновлюється реактивно **без перезавантаження**.

Fallback з авто-перезавантаженням **не потрібен** — стор-підхід дає живе оновлення.

## Обсяг

**Файли:**
- `admin/src/views/OffersListView.vue` — верхня пагінація; tab з URL + replace; from/tab у переходах; `store.refresh()` у діях.
- `admin/src/views/OfferFormView.vue` — повернення за `from`/`tab`.
- `admin/src/stores/moderation.js` — новий стор (create).
- `admin/src/layouts/AdminLayout.vue` — badge зі стора.
- Тести: `admin/tests/views/OffersListView.test.js`, `admin/tests/views/OfferFormView.test.js`, `admin/tests/layouts/AdminLayout.test.js`, `admin/tests/stores/moderation.test.js` (create).

**НЕ робимо:** пагінацію в інших розділах (там її нема — Sources/Suggested/Host-candidates/Categories/Users не пагіновані); backend/crawler без змін.

## Тестова стратегія
TDD (Vitest), тест-перший. Перед мержем — `npm test` І `npm run build`. Часті коміти. Гілка → merge (ff) у `main` + push → канонічний ребілд `admin`.
