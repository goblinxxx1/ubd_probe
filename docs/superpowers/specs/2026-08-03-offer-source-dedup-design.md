# Дедуп оферів + lifecycle джерел — дизайн

Дата: 2026-08-03
Гілка: `feat/offer-source-dedup`
Пам'ять: [[ubd-backend-dedup-canonical]] (canonical), [[ubd-crawler-pagelevel-dedup-done]] (article-identity), [[ubd-approved-source-passive-remoderation]] (re-moderation)

## Проблема (підтверджено на живих даних)

Approved-сайт **batart.army** дав **5 near-дублів** у черзі модерації (offers 254–258, усі 25%, «ТОВ художня майстерня»). Два системні корені:

1. **Пагінація не нормалізується.** `canonicalize_target_url` (`app/core/urlnorm.py`) зберігає query-параметри крім `utm_*`/click-id, тож `en-gb-specials`, `?page=2`, `?page=3`, `?page=4` дають **різні** `article_url_canonical` → різні page-identity (трек #6) → окремі офери (254/255/256/257).
2. **Дубль-реєстрація джерел.** Той самий хост зареєстрований як **2 активні website-джерела** (batart: #44 `…specials?page=2` + #39 `batart.army`). Системно: 5 хостів (batart, balistyka, dobrobut, reima + fixture-тест). Крос-джерельний офер (#258, джерело 39) не зливається з #255 (джерело 44), бо `target_url` = NULL → `target_url_canonical` = NULL → крос-джерельний merge (`create_offer` branch 4) не спрацьовує.

Плюс **живий баг**: видалення джерела в адмінці → **500** (FK `source_crawl_state.source_id` NOT NULL блокує голий `db.delete`).

## Рішення (огляд)

Трек із трьох частин + міграція-cleanup. Політика (затверджено): **одне активне website-джерело на хост** (walker робить deep-walk від кореня — друге джерело надлишкове).

## A. Нормалізація пагінації

`app/core/urlnorm.py`: додати пагінаційні query-параметри до стрипу в `canonicalize_target_url`:
```python
_PAGINATION_PARAMS = frozenset({"page", "p", "start", "offset"})
```
У фільтрі `kept` виключати також `k.lower() in _PAGINATION_PARAMS` (поряд із наявним `utm_*`/`_TRACKING_PARAMS`). Наслідок: `…/en-gb-specials?page=2` і `…/en-gb-specials` → **однаковий** canonical. Оскільки `canonicalize_target_url` живить і `target_url_canonical`, і `article_url_canonical` (обчислюється тим самим викликом у `create_offer`/`update_offer`) — пагіновані сторінки схлопуються в одну page-identity.

**Межа:** стрипаємо лише пагінаційні ключі; змістовні query (`?id=`, `?category=`) зберігаються.

## B. Одне активне website-джерело на хост

Хелпер `source_host(url) -> str | None` у `urlnorm.py` (host lowercased, www-less; `None` для не-http(s)).

**Шар 1 — превенція на suggestion** (`crud/suggested_source.create_suggestion`): наявний guard 204-ить лише за точним `normalize_ref`. Додати: для `type == website` — 204 no-op також якщо `source_host(url)` збігається з хостом **будь-якого активного website-джерела**. Telegram/instagram/facebook — незмінно (per-ref). Зупиняє дубль у корені.

**Шар 2 — превенція на створенні** (`crud/source.create_source`): якщо `type == website` і хост уже має активне website-джерело — **не створювати** друге; повернути наявне. `suggested_source.approve` через це: suggestion → `approved` без нового `Source` (лінк на наявний). Ручний admin-`create_source` того ж хоста → повертає наявне (не 500, не дубль).

## C. Фікс `delete_source` (баг 500 → робочий)

`crud/source.delete_source` зараз: голий `db.delete(obj)` → IntegrityError на `source_crawl_state`(NOT NULL FK) та потенційно `offers`(nullable FK). Фікс:
```python
def delete_source(db, source_id):
    obj = get_source(db, source_id)
    db.query(SourceCrawlState).filter(SourceCrawlState.source_id == source_id)\
        .delete(synchronize_session=False)                      # ephemeral cursor — safe
    db.query(Offer).filter(Offer.source_id == source_id)\
        .update({Offer.source_id: None}, synchronize_session=False)  # offers survive orphaned
    db.delete(obj)
    db.commit()
```
Офери переживають видалення джерела (осиротілі, `source_id=NULL`, лишаються published/pending). `source_id` nullable — FK не блокує; unique `(source_id, content_hash)` з NULL не конфліктує (MySQL трактує NULL як унікальні).

## Міграція (auto-cleanup) — down_revision = `e5f6a7b8c9d0` (поточний head; звірити `alembic heads`)

1. **Backfill canonical із пагінацією-strip**: для кожного offer з непорожнім `target_url`/`article_url` перерахувати `target_url_canonical`/`article_url_canonical` через оновлений `canonicalize_target_url`. Без ретро-merge оферів (як [[ubd-backend-dedup-canonical]]) — крім кроку 3.
2. **Деактивувати дубль-джерела**: для кожного хоста з >1 активним website-джерелом лишити активним те, що **володіє найбільшою к-тю оферів** (щоб не осиротити published-офер; tie → кореневий `path in ('','/')`/найкоротший), решту `is_active=False`. (batart: #44 володіє published #173 + 254–257 → лишити **#44**, зняти #39.)
3. **Схлопнути наявні дубль-офери**: після backfill (крок 1) для кожної групи з однаковим `article_url_canonical`, що містить **published**-офер, усі `pending_review`-офери групи → `status=rejected` (накопичені дублі вже опублікованої сторінки/пагінації). batart: група `en-gb-specials` має published #173 → 254–258 стають rejected → лишається **одна картка** (#173).

Міграція deterministична, round-trip up/down (down — no-op для backfill; реактивація не потрібна).

## Що НЕ входить (свідомо)

Site-wide знижка, описана на **різних** інфо-сторінках (напр. і `/oplata-dostavka/`, і `/specials/` — різні `article_url`, не пагінація) досі дасть 2 картки: це page-identity #6 (1 сторінка = 1 офер), інший механізм. Спостережувана batart-проблема це не включає. Follow-up.

## План тестів (TDD)

**`test_urlnorm`** (доповнити): `?page=2/3/4` → однаковий `canonicalize_target_url`; `?p=2`,`?start=20`,`?offset=` теж; змістовний `?id=5` збережено; `source_host` (host lowercased/www-less/None для junk).

**`test_offer_source_dedup`** (новий):
- `create_suggestion` website — 204 no-op, коли хост має активне website-джерело (інший path); telegram того ж хоста — створюється; точний-ref guard збережено;
- `create_source` website — другий того ж хоста повертає наявне (не дубль); різний хост / інший тип — створюється;
- `suggested_source.approve` — коли хост уже має джерело: suggestion→approved, без нового Source;
- `delete_source` — джерело з crawl_state + offers: **не** кидає; crawl_state видалено; offers.source_id=NULL; source видалено.

**`test_migration`** (round-trip): up на seed-даних (дубль-хост + пагіновані офери) → 1 активне джерело/хост + схлопнуті офери; down не падає.

## Критерії готовності

- Усі нові + наявні backend-тести зелені (`pytest -q`, потрібен MySQL).
- Пагіновані офери одного джерела → одна card-identity.
- Один активний website-source на хост (нові suggestions/creates + наявні 5 прибрано міграцією).
- delete-source в адмінці більше не 500.
- Жива Docker-перевірка: міграція на реальній `ubd`, batart → одна картка; delete-source працює.
