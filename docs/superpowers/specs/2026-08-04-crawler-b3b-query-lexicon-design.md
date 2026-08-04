# B3b — Self-growing query lexicon from approved offers (crawler + backend)

**Дата:** 2026-08-04
**Гілка:** `feat/crawler-b3b-query-lexicon` (від `main`, HEAD 6e6adb2)
**Тип:** backend + crawler (мінімальне read-only розширення внутрішнього ендпоінта).
**Контекст:** Трек B, фаза B3b (ядро новизни — «щотижня нові фрази»). B3a (місто-множник,
грід=1701) уже влито/задеплоєно. Батьк-дизайн `2026-08-04-crawler-search-overhaul-design.md`
§3b. Дзеркалить наявний promo/marketing autofill [[ubd-crawler-marketing-lexicon-autofill]].
Пам'ять [[ubd-crawler-news-exclusion]], [[ubd-crawler-query-grid]].

## Проблема
`build_grid` статичний: сервісний/категорійний вимір відсутній (лише INTENT×AUDIENCE +
місто). `promo_lexicon` самонавчається, але годує лише ЕКСТРАКТОР, не ЗАПИТИ. Нові
вертикалі бізнесів (стоматологія, автосервіс, кав'ярня…), що вже є серед прийнятих
оферів, ніколи не стають пошуковими фразами → новизна лише з нових захардкоджених осей.

## Рішення — окремий query-лексикон, що зростає з прийнятих оферів
Дзеркало promo-autofill, але для ЗАПИТІВ: майнер (офлайн, детермінований) з прийнятих
оферів → кандидати → **людський audit-гейт** → `LEARNED` query-лексикон → `build_grid`
комбінує як `{service} {audience}`. Injection-hardened: джерело — вже провалідовані
модерацією офери, не сирий веб. Порожній LEARNED = **байт-еквівалент** поточного гріда.

### Джерело — дві доріжки (опція C)
1. **Структурні `offer_categories`** (куровані вертикалі, які модератор проставив на
   published-офері) → **прямо в LEARNED** (вже вветовані людиною на етапі публікації;
   бутстрап без audit). Потребує read-only розширення бекенд-ендпоінта.
2. **Іменники з `text`** (`title\ndescription`, уже віддається) → майнер (pymorphy3
   NOUN-фільтр + log-odds) → кандидати → **audit-гейт** (людина approve).

`provider` (бренд) **виключено** з майнінгу — бренди свідомо НЕ вісь запитів (їх покриває
brand_feed); майнити provider = повернути бренди в запити.

### Backend — мінімальне read-only розширення
`ApprovedOfferOut` ([internal.py:102](backend/app/routers/internal.py)) додати
`categories: list[str] = []`; в ендпоінті `list_approved_offers` мапити
`categories=[c.name for c in o.offer_categories]` (relationship уже selectin-loaded).
Адитивно, зворотно сумісно (snowball ігнорує зайве поле). Тест `test_internal`.

### Crawler — компоненти (дзеркало `learn/`)
- **`discovery/query_lexicon.py`** (дзеркало `promo_lexicon`): `reload_learned(path)` +
  `learned_services() -> tuple[str, ...]`. БЕЗ SEED (порожній старт → byte-eq OFF).
- **`learn/tokenize.py`**: додати `service_terms(text) -> list[str]` — леми ЛИШЕ
  іменників (pymorphy3 `tag.POS == 'NOUN'`) + noun-noun біграми. Наявний `tokenize`
  не чіпати.
- **`learn/miner.py`**: додати параметр `tokenizer=tokenize` у `mine(...)` (дефолт =
  наявний → byte-eq для promo-майнера). Query-майнер передає `tokenizer=service_terms`.
- **`learn/run_query_miner.py`** (дзеркало `run_miner`): `run_query_miner(config)` —
  `read_corpus` → `mine(rows, known_stems=query_lexicon.learned_services(),
  stoplist=<soft>, tokenizer=service_terms)` → `survivors` (support/z пороги) →
  `write_candidates(query_candidates_path)`.
- **`learn/audit.py`**: `approve`/`load_stoplist` реюз як є (параметризовані шляхами) для
  query-путі — `approve --candidates <q_cand> --learned <q_learned>`. Наявний `reject`
  (плоский стоплист-`list[str]`) **не чіпати** (promo byte-eq). Додати **окремий** query-
  reject, що пише `{term, z}` (див. м'який reject нижче) + CLI-підкоманду для query-путі.
- **`learn/bootstrap_query_lexicon.py`** (новий оркестратор бутстрапу, CLI).

### Reject — м'який, «категорії > стоплист» (рішення (1))
- Стоплист query-путі — файл `{term, z_at_reject}`-записів (НЕ плоский список), **НЕ
  перманентний**. Query-майнер пропускає стоплистнутий термін, **доки** новий
  `z ≤ z_at_reject × query_lexicon_resurface_factor` (config, дефолт **2.0**); при
  `z >` цього — термін **спливає знову** в кандидати. (Проти перманентної сліпої плями у
  відкритому, еволюційному сервіс-словнику.)
- **Категорії виграють:** при бутстрап-сідінгу структурної категорії, якщо термін є в
  query-стоплисті — він **авто-знімається** зі стоплиста (категорія — людський сигнал
  сильніший за текстовий reject).

### `build_grid` — інтеграція LEARNED (форма 6×N, без міста)
- Сигнатура: `build_grid(cities=None, services=None)`. `services=None → ()` (порожньо →
  byte-eq). Wiring передає `query_lexicon.learned_services()` коли прапор ON.
- Новий **service-блок** ПІСЛЯ гео-блоку (порядок незмінний до нього → байт-стабільний
  префікс 1701): `for service in services: for aud in GEO_AUDIENCES: add f"{service} {aud}"`
  → «стоматологія ветерани», «стоматологія військові», … = **6×N** фраз.
- **Лише аудиторно-таргетований** шаблон (самофільтрація аудиторією в запиті → жодного
  модераційного шуму; `{intent}×{service}` свідомо ВІДКИНУТО — спирався б на relevance-gate).
- **БЕЗ місто-множника** на LEARNED (міста вже в гео-блоці; інакше вибух).
- **Бюджет-кап** `config.query_lexicon_max_terms` (дефолт 40): у грід ідуть перші N
  сервісів — **спершу категорії** (пріоритет), далі текст-майнені за спаданням z. Тримає
  грід ~1941 (обхід ~5.4 дн < TTL 168 год). Ріст понад — чекає B3c (due-walking).

### Бутстрап — ОДРАЗУ (ключова вимога)
`bootstrap_query_lexicon.py` (CLI, ідемпотентний):
1. `api.list_approved_offers(since=None)` — **повний backfill** усіх прийнятих оферів
   (з категоріями).
2. Кожен офер: `CorpusRecorder.record(item, True, snowball=True)` — **закинути text у
   корпус** (годує текст-майнінг); зібрати `categories`.
3. **Структурні категорії** (унікальні імена) → прямо в `query_lexicon_learned.json`
   (`source="category"`, dedup); авто-зняти зі стоплиста.
4. `run_query_miner(config)` → текст-іменник-кандидати в чергу для audit.
5. Друк зведення: N категорій засіджено, M кандидатів у черзі.

### Гейтинг
`config.query_lexicon_enabled: bool = True`. `False` → wiring кличе `build_grid(services=[])`
→ грід 1701 (byte-eq B3a). Майнінг завжди офлайн (CLI); живий грід читає лише `LEARNED`.
Порожній `LEARNED` = byte-eq незалежно від прапора.

### Config-шляхи (дефолти `/data/…`)
`query_lexicon_learned_path`, `query_candidates_path`, `query_stoplist_path`,
`query_lexicon_enabled=True`, `query_lexicon_max_terms=40`, `query_lexicon_resurface_factor=2.0`,
`query_miner_min_domain_support`, `query_miner_min_logodds`, `query_miner_max_candidates_per_run`
— **окремі** конфіги query-путі (щоб тюнити незалежно від promo), дефолти = ті самі
значення, що в наявних promo-порогах (`miner_min_domain_support` тощо).

## Обсяг / файли
- **Backend:** `routers/internal.py` (+`categories` в `ApprovedOfferOut`+мапінг),
  `tests/test_internal.py`.
- **Crawler нові:** `discovery/query_lexicon.py`, `learn/run_query_miner.py`,
  `learn/bootstrap_query_lexicon.py` (+тести).
- **Crawler зміни:** `learn/tokenize.py` (`service_terms`), `learn/miner.py` (`tokenizer`
  param), `discovery/query_grid.py` (`build_grid` services-блок), `config.py`/`wiring.py`
  (шляхи+прапор+кап; wiring вантажить query_lexicon і передає в build_grid),
  `learn/audit.py` (м'який reject query-путі).

## Тести (TDD)
- backend: `approved-offers` повертає `categories`.
- `service_terms`: лишає лише іменники, дропає дієслова/прикметники/сміття; біграми.
- `mine(tokenizer=…)`: promo-виклик byte-eq (дефолт); query-виклик через service_terms.
- `build_grid(services=[…])`: 1701 + 6×N; `services=[]`→1701 (byte-eq); байт-стабільний
  префікс; кап N; категорії перед текст-термінами.
- м'який reject: стоплистнутий не спливає доки z≤поріг; спливає при z>поріг; категорія
  авто-знімає зі стоплиста.
- bootstrap: повний backfill (since=None), категорії→LEARNED прямо, text→кандидати,
  ідемпотентність.
- config/wiring: прапор ON→services у гріді, OFF→1701; порожній LEARNED byte-eq.

## Деплой
Backend rebuild (нове поле) + crawler rebuild. **Запустити бутстрап одразу**
(`python -m crawler.learn.bootstrap_query_lexicon`) → засідити категорії, наповнити
чергу кандидатів. Далі людина проходить `audit list/approve/reject` по черзі. Жива
верифікація: `approved-offers` віддає categories; після audit-approve нові фрази
`{service} {audience}` з'являються в гріді; порожній LEARNED = грід 1701.

## Поза скоупом (наступне)
- **B3c** — due-query walking (робить великий простір нормальним; після нього кап можна
  підняти).
