# Масові дії для термінів пошуку (query-terms)

**Дата:** 2026-09-01
**Гілка:** `feat/query-terms-bulk-actions`

## Мета

Додати в адмінку (`QueryTermsView.vue`) мультивибір рядків + «вибрати всі на
сторінці» стандартними чекбоксами, щоб масово затверджувати / відхиляти /
закріплювати терміни пошуку замість почергового кліку по кожному.

## Контекст (наявне)

- `ResponsiveTable.vue` уже має проп `selectable` + подію `selection-change`
  (масив вибраних row-обʼєктів). el-table дає шапковий чекбокс «вибрати всі»
  нативно. Таблиця термінів рендерить `pageItems` (клієнтська пагінація 20/стор),
  тож «вибрати всі» = всі на поточній сторінці.
- Патерн bulk уже усталений в `OffersListView.vue`: `selectable` →
  `selected` ref → `.bulkbar` з кнопками `:disabled="!selected.length"` →
  bulk-API повертає `{done, failed}`, per-id ізоляція помилок.
- Рядкові дії термінів (по вкладках-статусах): pending → approve/reject;
  approved → to-pending; rejected → unreject (той самий crud `to_pending`);
  плюс protect/unprotect у всіх.
- Жорсткого delete для термінів немає. «Видалення» = `reject`.

## Дизайн

### Бекенд

Один узагальнений ендпоінт (шість дій → одна ручка з `action`-енумом):

```
POST /admin/query-terms/bulk
body: { ids: list[int], action: "approve"|"reject"|"to_pending"|"protect"|"unprotect" }
resp: { done: list[int], failed: list[{id: int, error: str}] }
```

- Per-id `try/except` у циклі — одна помилка не валить решту (як
  `/offers/bulk-reject`).
- `approve`/`reject` викликають `query_term_crud.approve/reject(db, id, admin.id)`;
  `to_pending` → `query_term_crud.to_pending(db, id)`; `protect`/`unprotect` →
  `query_term_crud.set_protected(db, id, True/False)`.
- `unreject` (кнопка rejected-вкладки) мапиться на `to_pending` — окремої дії не
  треба.
- Схеми `QueryTermBulkIn` / `QueryTermBulkOut` у `schemas/query_term.py`.

### Фронт

- `queryTerms.js`: `export const bulk = (ids, action) => client.post("/admin/query-terms/bulk", { ids, action })...`
- `QueryTermsView.vue`:
  - `ResponsiveTable :selectable="true" @selection-change="selected = $event"`,
    `const selected = ref([])`.
  - Bulk-панель над таблицею, контекстна до `status.value`, кнопки
    `:disabled="!selected.length"` зі лічильником `(n)`:
    - **pending**: `Затвердити вибрані` · `Відхилити вибрані`
    - **approved**: `Повернути в кандидати`
    - **rejected**: `Повернути в кандидати`
    - **у всіх статусах**: `Закріпити вибрані` · `Відкріпити вибрані`
  - Підтвердження (`confirmAction`) на незворотні-по-суті: `reject` та
    `to_pending` (прибирає з гріду). approve/protect/unprotect — одразу.
  - Після дії: очистити вибір, `load()`, `ElMessage` з лічильником done/failed
    (варнінг, якщо є failed).

### Поза скоупом

- Жорсткий delete термінів (не існує в системі).
- Master-чекбокс select-all у мобільному card-режимі — адмінка десктоп-first;
  шапковий select-all лишається десктоп-only, мобільний card має почерговий вибір.

## Тести

- Бекенд (`backend/tests/test_query_terms_admin.py`): bulk зі змішаними
  статусами ids; часткова помилка (неіснуючий id у `failed`, решта в `done`);
  кожна `action` застосовує правильний перехід статусу/protected.
- Фронт (Vitest): контекстні кнопки зʼявляються за вкладкою; клік кличе
  `bulk(ids, action)` з правильним action; порожній вибір → кнопки disabled.
