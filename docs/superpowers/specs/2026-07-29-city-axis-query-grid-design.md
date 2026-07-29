# City-вісь у query-grid (Трек #8) — дизайн

Дата: 2026-07-29
Гілка: `feat/city-axis`
Пам'ять: [[ubd-backlog-coverage-moderation]] (P1 · #8), [[ubd-crawler-query-grid]]

## Проблема й ціль

Активний пошук краулера генерує фрази `{intent} {audience}` (`query_grid.build_grid()`,
≈14×27 = 378 фраз). Міста свідомо виключені (`query_grid.py:3`). Через це видача
однорідна по всій країні й **не тягне локальні бізнеси** конкретних міст — а ціль
беклогу #8 — national coverage («вся Україна»): city×intent×audience має діставати
місцеві бізнеси зі знижками УБД.

Жорстка вимога беклогу: **місто = окрема ротаційна вісь із власним курсором, НЕ
декартів добуток** (378 × 1229 міст = комбінаторний вибух). Диверсифікація видач
цінніша за ре-фреш.

## Рішення (огляд)

Додати **місто як незалежну ротаційну вісь**: місто — **суфікс** до наявних
`{intent} {audience}` фраз. Два незалежні курсори (фрази через `grid_cursor` +
місто через новий `city_cursor`) з різними періодами ротації дають повільний
«діагональний» sweep простору city×phrase **без матеріалізації** декартового добутку.

City-вісь — суто **discovery/recall-левер**: змінює лише які пошукові запити
видаються. Кандидати далі течуть наявним пайплайном (harvester → attribution →
offer) без змін.

## Джерело міст

Перевикористовуємо наявний **`gazetteer.json`** (1229 записів) **як є**.

Емпірична підстава (Overpass, UA, 2026-07-29): `place=city|town` = 46 city + 1260 town
= **міста + смт**; сільські села/селища — це `place=village` (у газетир не входять).
Надійного OSM-тегу «смт» немає (`official_status` заповнений лише в ~75 з 1306),
тож ділити далі нічим і не треба: наявний газетир **вже і є** «усі міста + смт,
без сільського хвоста» — рівно потрібна межа.

Суфікс запиту = канонічне `name` кожного запису (напр. `Львів`, `Кривий Ріг`).
**Не** інфлексовані форми (`forms` існують для екстракції міста з тексту, не для запиту).

## Новий компонент: `crawler/crawler/discovery/city_axis.py`

Ізольований, тестований; перевикористовує `geo._load_entries()` для завантаження назв.

```python
class CityAxis:
    def __init__(self, cities: list[str] | None = None):
        # cities = [e["name"] for e in geo._load_entries()] за замовчуванням
        self._cities = cities if cities is not None else _load_city_names()

    def __len__(self) -> int: ...

    def next_batch(self, base_phrases: list[str], cursor: int, k: int
                   ) -> tuple[list[str], int]:
        """Суфіксує ПОТОЧНЕ місто (cities[cursor]) на перші k base_phrases.
        Повертає (queries, new_cursor). Місто рухається 1/прохід."""
        # порожній газетир АБО k<=0 АБО порожні base_phrases -> ([], cursor)
        # C = cities[cursor % len(cities)]
        # queries = [f"{p} {C}".strip() for p in base_phrases[:k] if p]
        # new_cursor = (cursor + 1) % len(cities)
```

Контракти:
- порожній список міст → `([], cursor)` (byte-eq off, курсор не рухається);
- `k <= 0` → `([], cursor)`;
- негативний/out-of-range `cursor` нормалізується через `% len` (як `QueryGrid`);
- детермінізм: однакові входи → однаковий вихід.

## Інтеграція у `SearchPass`

`SearchPass.__init__` отримує додатково `city_axis` та `city_queries_per_pass`
(обидва опційні; `None`/0 → повна відсутність city-запитів, byte-eq pre-track).

У `run()`, для кожного provider-плану **після** побудови базового `batch`
(40 фраз за курсором провайдера):

```python
keywords = merge_queries(batch, pins)
if self._city_axis is not None and self._city_k:
    city_qs, _ = self._city_axis.next_batch(batch, self._state.city_cursor, self._city_k)
    keywords = merge_queries(keywords, city_qs)     # дедуп через наявний merge_queries
```

`city_cursor` — **єдиний, спільний** для провайдерів. Рухається **раз на прохід**,
**після** циклу планів, якщо **хоч один** провайдер успішний (advance-on-success,
дзеркалить семантику `grid_cursor`):

```python
# any_succeeded = будь-який plan.succeeded() після run(); визначається у циклі планів
if self._city_axis is not None and self._city_k and len(self._city_axis) and any_succeeded:
    self._state.set_city_cursor((self._state.city_cursor + 1) % len(self._city_axis))
```

Курсор просувається на +1 рівно тоді, коли city-запити мали сенс цього проходу
(вісь задана, `k>0`, є міста, ≥1 провайдер успішний). `CityAxis.__len__` дає
кількість міст для модуля.

Місто-запити **адитивні**: 40 базових + `k` city-суфіксних на провайдера на прохід.
Узгоджено з треком #5 (масштабування пропускної, [[ubd-crawler-coverage-scaleup-done]]);
реальні фетчі капить `active_fetch_budget=80`. Нові city-рядки — унікальні запити,
тож природно **обходять 96h-кеш** (`search_cache_ttl_hours`) — бонус до свіжості.

## Стан: `SearchState`

Додати поле `city_cursor` (дефолт 0) поряд із `grid_cursor`/`searxng_cursor`/
`site_cursor`/`approved_cursor`:
- `_EMPTY` отримує `"city_cursor": 0`;
- властивість `city_cursor` (int, дефолт 0) + `set_city_cursor(value)` (персист);
- незалежність від інших курсорів (round-trip зберігає).

## Config-ручки (`config.py`: `_RawSettings` + `Config` + `load_config`)

- `city_axis_enabled: bool = True` — у межах opt-in `active_discovery`; off → byte-eq;
- `city_queries_per_pass: int = 10` — скільки city-суфіксних/провайдера/прохід; 0 → off.

Дефолт 10 (за рішенням: адитивно, 40+10=50/провайдера/прохід).

## Wiring (`wiring.py`)

У блоці `if config.active_discovery:` після побудови `plans`:
```python
city_axis = CityAxis() if config.city_axis_enabled else None
search_pass = SearchPass(plans, state, QueryGrid(),
                         config.search_queries_per_pass, config.search_keywords,
                         city_axis=city_axis,
                         city_queries_per_pass=config.city_queries_per_pass)
```
`city_axis_enabled=False` → `city_axis=None` → SearchPass поводиться byte-eq pre-track.

## Ротаційна математика

- `grid_cursor` цикл ≈10 проходів (378/40);
- `city_cursor` цикл = 1229 проходів (по 1 місту/прохід).

Різні (взаємно майже прості) періоди → фраза-зріз дрейфує відносно міста →
з часом покриває багато city×phrase пар без вибуху. Кожне місто бачиться раз
на ~1229 проходів із тим фраза-зрізом, що вирівнявся того проходу. Це
«диверсифікація > ре-фреш».

## Що НЕ змінюється

- Місто **офера** досі визначається екстракцією зі *змісту* сторінки
  (`geo.find_cities`), а не із запиту.
- Harvester / attribution / offer-пайплайн / walker / інші фіди — недоторкані.
- `grid_cursor` / `searxng_cursor` / `site_cursor` / `approved_cursor` — незалежні,
  не чіпаємо.
- `QueryGrid`, `build_grid`, `AUDIENCE_FORMS`/`INTENT_FORMS`/`BRANDS` — без змін.

## Прийнятий компроміс

Окуповані міста (Крим / частина Сходу) присутні в газетирі 1229 → частина
city-запитів марна / ризик окупаційного junk. Ловиться attribution-hardening +
людською модерацією. Свідомо **не** фільтруємо в цьому треку: надійного
окупованого-списку в даних немає, курований блокліст — окремий scope. Лишається
гачок додати фільтр пізніше (напр. окремий `occupied_cities` set на етапі
завантаження `CityAxis`).

## План тестів (TDD)

**`test_city_axis.py`** (новий):
- suffix-форма: `next_batch(["знижка військовим"], 0, 1)` → `["знижка військовим <city0>"]`;
- ротація: курсор +1/виклик, wrap на кінці;
- k-cap: `k` обрізає base_phrases; `k > len(base)` → усі;
- byte-eq off: порожній список міст → `([], cursor)`; `k<=0` → `([], cursor)`;
- нормалізація негативного/out-of-range курсора;
- детермінізм: повтор входу = повтор виходу;
- фільтр порожніх/None фраз.

**`test_search_pass.py`** (доповнити):
- city-queries домержуються у keywords провайдера, коли axis+k задані;
- `city_cursor` рухається +1 на успіху ≥1 провайдера;
- `city_cursor` **не** рухається, коли всі провайдери зафейлили;
- axis=None або k=0 → keywords **ідентичні** pre-track (byte-eq);
- дедуп: якщо суфіксний запит випадково збігся — merge_queries прибирає дубль.

**`test_search_state.py`** (доповнити):
- `city_cursor` дефолт 0;
- `set_city_cursor` персист round-trip;
- незалежність від `grid_cursor`/`searxng_cursor`.

**wiring / config**:
- `city_axis_enabled=False` → `search_pass` без city-запитів (byte-eq);
- ручки прокидаються з `_RawSettings` у `Config`.

## Критерії готовності

- Усі нові + наявні crawler-тести зелені (`pytest -q`).
- `city_axis_enabled=False` → байт-еквівалентний відкат живого пошуку до pre-track.
- Жива Docker-перевірка: з увімкненою віссю пошук видає city-суфіксні запити,
  краулер стійкий, офери течуть.
