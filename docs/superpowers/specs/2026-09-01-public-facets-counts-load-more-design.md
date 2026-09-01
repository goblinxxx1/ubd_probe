# Публічка: контекстні фасети з лічильниками + «Завантажити ще»

Дата: 2026-09-01
Гілка: `feat/public-facets-counts-loadmore` (від `main`)

## Мета

Дві зміни в публічному фронті (`public/`) + бекенд:

1. **Фасети відображають лише присутні значення, з контекстними лічильниками.** У фільтрах не показуються варіанти, яких немає в жодному опублікованому непротермінованому офері. Поруч кожного варіанта — число оферів, яке **перераховується під активні фільтри** (маркетплейс-стиль).
2. **Кнопка «Завантажити ще»** дорощує список наступною пачкою без перезавантаження сторінки. Наявний номерний пейджер **лишається** (обидва механізми співіснують).

## Обмеження (тверді)

- **Адмінка не чіпається ніде.** Доказ перевірки:
  - `admin/src` не має жодної згадки `/facets` чи `/locations`.
  - `routers/admin.py` споживає з `offer_crud` лише `create_offer`, `list_offers`, `set_status`, `get_offer`, `update_offer`, `delete_offer` — жодну не редагуємо.
- **Не редагуємо жодну наявну функцію** `crud/offer.py` і `crud/category.py` — тільки додаємо нові.
- **Не змінюємо сигнатуру `list_offers`** і схему `CategoryOut` (адмінка віддає її через `response_model`).
- Ендпоінти `/target-categories`, `/offer-categories`, `/locations` лишаються as-is.
- Російська мова ніде не з'являється (лексикони/тексти) — незмінно для проєкту.

## Задача 1 — контекстні фасети з лічильниками

### Бекенд

Новий публічний ендпоінт: `GET /api/facets`, приймає **ті самі фільтри**, що й `/offers`:
`type: list[OfferType]`, `target_category: list[int]`, `offer_category: list[int]`,
`location: list[str]`, `q: str` (усі опційні; `page`/`size` — не приймає).

Повертає нову схему `FacetsOut`:

```json
{
  "target_categories": [{"id": 1, "name": "…", "count": 10}, …],
  "offer_categories":  [{"id": 2, "name": "…", "count": 4}, …],
  "types":             [{"value": "discount", "count": 12}, …],
  "locations":         [{"name": "Львів", "count": 3}, …]
}
```

**Схеми (нові, у `schemas/offer.py` або `schemas/facets.py`):**
- `CategoryFacet { id: int, name: str, count: int }`
- `TypeFacet { value: OfferType, count: int }`
- `LocationFacet { name: str, count: int }`
- `FacetsOut { target_categories, offer_categories, types, locations }`

**Правило диз'юнктивного фасетування («фасет не звужує сам себе»):**
Рахуючи лічильники фасета F, застосовуємо:
- базу: `status = published` + не протерміновані (`valid_until IS NULL OR valid_until >= today`) + пошук `q`;
- **усі інші** фасети (їх активні вибори);
- але **ігноруємо** власний вибір у F.

Отже:
| Фасет F | застосовуються фільтри | GROUP BY |
|---|---|---|
| target_categories | type, offer_category, location, q | target_category.id |
| offer_categories | type, target_category, location, q | offer_category.id |
| types | target_category, offer_category, location, q | offer.type |
| locations | type, target_category, offer_category, q | location.name |

Пошук `q` — це не фасет-чекбокс, а текстовий фільтр; застосовується завжди до всіх лічильників.

**Видимість значень:**
- значення з `count = 0` **ховаються**, **окрім** уже вибраних (щоб поставлений чекбокс не зникав і його можна було зняти);
- бекенд домішує вибрані значення (він отримав перелік фільтрів) з їх реальним лічильником, можливо 0; для назв робить lookup за id (категорії) — типи й локації несуть значення у самому параметрі.

**Нові crud-функції у `crud/offer.py` (лише додавання):**
- `count_facet_target_categories(db, *, types, offer_category_ids, locations, search, selected_ids) -> list[(id, name, count)]`
- `count_facet_offer_categories(db, *, types, target_category_ids, locations, search, selected_ids) -> …`
- `count_facet_types(db, *, target_category_ids, offer_category_ids, locations, search, selected) -> list[(value, count)]`
- `count_facet_locations(db, *, types, target_category_ids, offer_category_ids, search, selected) -> list[(name, count)]`

Кожна будує базовий фільтр опублікованих непротермінованих оферів, застосовує «чужі» фасети, робить `JOIN` до відповідної асоціації/поля + `GROUP BY` + `COUNT(DISTINCT offer.id)`, домішує вибрані нульові, сортує за name/value. 4 агрегати на запит — на наших обсягах дешево.

Спільний внутрішній хелпер може зібрати «базовий query з переліком застосованих фасетів», щоб уникнути дублювання логіки фільтрації (без зміни `list_offers`).

### Фронт (`public/src`)

- `composables/useDictionaries.js` → **новий** `composables/useFacets.js`: тягне `/api/facets` з поточними фільтрами з `route.query` і **перезавантажується на кожну зміну фільтра** (`watch(route.query)`), паралельно до `useOffers`. Віддає `targetCategories`, `offerCategories`, `types`, `locations` (усі з лічильниками).
  - **Stale-while-revalidate:** під час рефетчу тримаємо попередній результат (не спорожняємо), щоб фільтри не блимали.
  - Параметри — той самий serializer, що для `/offers`, мінус `page`/`size`.
- `api/offers.js`: додати `facets(params)` → `GET /facets`.
- `components/OfferFilters.vue`: біля кожного варіанта — лічильник, напр. `☑ Медицина (10)`. Опції беруться з відповіді `/facets`; для «Типу» лейбл із `OFFER_TYPES` (константа лишається), присутність/лічильник — з відповіді. Локації — теж із `/facets` (пошук по місту лишається).
- `views/OffersView.vue`: замінити `useDictionaries` на `useFacets`, прокинути `types` у `OfferFilters`.
- Адмінський стор словників — без змін.

## Задача 2 — «Завантажити ще» + пейджер (обидва)

### Модель співіснування

- **Пейджер** (номерний, унизу) = *стрибок/заміна*: клік по сторінці N → `?page=N`, список скидається й показує саме пачку N. Поточна поведінка, лишається.
- **«Завантажити ще»** (кнопка під ґридом) = *дорощування*: підвантажує наступну пачку за поточно завантаженою й **додає** (append), URL не чіпає.
- Зміна фільтрів/пошуку → скидання на базову пачку (`page` з URL).
- **Прийнятий компроміс:** пейджер підсвічує *базову* сторінку навіть після дорощування (одне джерело істини для URL, ціною маленької неточності підпису).

### Фронт

- `composables/useOffers.js` рефактор:
  - `loadedPage` (найвища завантажена; старт = базова `page` з URL);
  - `items` **накопичуються** (append), а не замінюються при loadMore;
  - `hasMore = items.length < total`;
  - окремий `loadingMore` (щоб ґрид не блимав порожнім, на відміну від початкового `loading`);
  - `watch(route.query)` → reset: очистити `items`, `loadedPage = page`, fetch базову (replace);
  - `loadMore()` → fetch `loadedPage + 1`, append, оновити `loadedPage`.
- Новий `components/LoadMore.vue`: показ лише коли `hasMore`; спінер на `loadingMore`; підпис «Показано X з Y». Емітить `load`.
- `views/OffersView.vue`: під `OfferGrid` — `LoadMore` (`@load="loadMore"`), нижче — наявний `Pagination` (без змін до самого компонента).

## Тестування

**Backend (pytest):**
- контекстність: клік по локації змінює `count` тематик;
- диз'юнктивність: вибір одного значення у F не обнуляє інші варіанти того ж F;
- вибране значення з `count = 0` присутнє у відповіді (не зникає);
- порожня БД → усі списки порожні;
- протермінований/неопублікований офер не «світить» своє значення й не додає до лічильника.

**Public (vitest):**
- `OfferFilters` рендерить лічильники, ховає нулі (крім вибраних);
- `useFacets` рефетчить на зміну фільтра, тримає stale під час рефетчу;
- `useOffers`: reset на зміну фільтра, append на `loadMore`, межа `hasMore` (останній `loadMore` ховає кнопку).

**Прод-перевірка ([[ubd-preview-surfaces]]):**
- `npm run build` у `public/` (ловить scoped-Less);
- `npx vitest run` (public + backend pytest);
- ребілд контейнерів `docker compose up -d --build public backend`;
- `curl` бандла/`/api/facets` для підтвердження живих змін.

## YAGNI / поза межами

- Не поєднуємо `/offers` і `/facets` в один ендпоінт (лишаємо ізольованими, хоч обидва фетчаться на зміну фільтра).
- Не чіпаємо адмінку жодним файлом.
- Не додаємо контекстні фасети в адмінський редактор — там усі категорії, як і було.
