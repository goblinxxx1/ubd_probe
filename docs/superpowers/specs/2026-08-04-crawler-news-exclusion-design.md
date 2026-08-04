# Track A — News exclusion from the active crawl

**Дата:** 2026-08-04
**Гілка:** `feat/crawler-news-exclusion` (від `main`)
**Тип:** crawler-only (+ жива чистка стану). Backend/admin не змінюються.

## Проблема (підтверджено фактами)
Новинні/медіа сайти просочуються в активний краулінг і навіть у топ `domain_registry`. Живий доказ: серед 22 «доступних» (score ≥ 0.5, не заапрувлені) доменів ~10 — новинні: `breaking.znaj.ua`, `week.ukrainianwall.com`, `kosht.media`, `epravda.com.ua`, `protocol.ua`, `focus.ua`, `glavcom.ua`, `thepage.ua`, `parlament.ua`, `kharakter.media`. Жоден із них не в блоклісті (`is_blocked_host`=False для всіх).

**Ланцюг леаку:** пошук за фразою «знижки військовим» закономірно повертає новинні статті → екстрактор («мішок термінів») пропускає (є offer-тригер+знижка+аудиторія будь-де) → атрибуція не відкинула новинний хост як провайдера → хост не в блоклісті → `domain_registry` записав його «продуктивним» → `DomainFeed` ре-фідить щопрохід.

## Рішення (курований список + кнопка модератора; без евристики — 0 хибних)
1. **Розширити SEED-блокліст** `blocklist.py::_MEDIA` курованим набором UA-новинних/медіа-хостів: виявлені 10 + відомі загальні (напр. `liga.net`, `pravda.com.ua` вже є; додати `epravda.com.ua`, `znaj.ua`, `ukrainianwall.com`, `kosht.media`, `protocol.ua`, `focus.ua`, `glavcom.ua`, `thepage.ua`, `parlament.ua`, `kharakter.media`, `hromadske.ua`, `suspilne.media`, `24tv.ua` (є), `tsn.ua` (є) — фінальний список у плані). Суфікс-матч уже покриває сабдомени (`breaking.znaj.ua` ← `znaj.ua`).
2. **Не тримати блоклістнуте у пулі кандидатів:** `DomainFeed.candidates` і `site:`-виклик `registry.top` **пропускають** `is_blocked_host` хости — блоклістнутий домен не емітиться кандидатом (не марнує слот). (Фетч його вже й так не чіпає — гейт blocklist=no-fetch, трек [[ubd-crawler-blocklist-no-fetch]]; запис у registry теж не відбувається, бо гейт стоїть до `record`.)
3. **Жива чистка стану:** прибрати новинні/блоклістнуті хости з `domain_registry.json`, brand/osm/aggregator-фідів і пошук-кешу (одноразовий скрипт у контейнері, як у попередніх чистках).
4. **Хвіст (нові леаки):** модератор ріже кнопкою «Заблокувати» (вже є, [[ubd-reject-block-host]]) → одразу в блокліст → no-fetch + вилучення з пулу.

**Свідомо БЕЗ загальної евристики** (`news.`/`breaking.`/`.media`/`novyny`-токени): ризик хибних спрацювань на легітимних бізнесах. Додамо лише якщо леак повторюватиметься.

## Обсяг / файли
- `crawler/crawler/discovery/blocklist.py` — розширити `_MEDIA`.
- `crawler/crawler/discovery/domain_feed.py` — `candidates` пропускає `is_blocked_host`.
- `crawler/crawler/runner.py` — у `site:`-гілці відфільтрувати `registry.top` від блоклістнутих (belt).
- Тести: `test_blocklist.py` (нові хости → blocked), `test_domain_feed.py`/`test_runner.py` (блоклістнутий не емітиться кандидатом).
- Жива чистка: одноразовий скрипт (не в репо).

**НЕ робимо:** евристику; backend/admin; зміни екстрактора/атрибуції (окремо, якщо знадобиться).

## Тести / деплой
TDD (crawler pytest). Канонічний ребілд crawler; жива чистка стану + верифікація `is_blocked_host`=True і відсутності новинних у пулі.
