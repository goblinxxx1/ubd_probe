# Crawler: split active/passive passes with separate cadences

**Дата:** 2026-08-04
**Гілка:** `feat/crawler-active-passive-split` (від `main`)
**Тип:** crawler-only. Backend/admin/екстракція/атрибуція не змінюються.

## Проблема / мета

Зараз `Runner.run()` робить один прохід: **спершу пасивний** обхід усіх активних джерел, **потім** активний discovery, потім `expire_stale`; цикл — у `docker-entrypoint.sh` раз на `CRAWL_INTERVAL_SECONDS` (live 3год). Хочемо:
1. **Активний — основний і перший**, частіше; збирає максимум оферів за свої ліміти.
2. **Пасивний — рідко** (раз на 96 год) — джерела рідко змінюються; без втрати якості.
3. **Активний оминає опубліковані/заапрувлені джерела** — їх доглядає лише пасив.

Безпека рідкого пасиву перевірена: `expire_stale` протухає source-офери лише через `freshness_ttl_days=30` (720 год) невидимості; пасив раз на 96 год ≪ TTL → передчасного протухання нема. Опубліковані активні офери промоутяться в активні website-джерела (`promotion.maybe_promote_on_publish`), тож re-confirm'яться пасивом у межах 96 год.

## Рішення

### Розділення на дві процедури
- **`run_active()`** — `list_sources` лише для `known`/`known_hosts` (skip-сети), потім фіди (domain_feed/search/brand/osm/aggregator) + `site:`-запити + `ActiveHarvester.harvest` + prune/save `domain_registry`. **Не** краулить джерела. Повертає summary.
- **`run_passive()`** — `list_sources`, для кожного `_crawl_source` (deep-walk), наприкінці `expire_stale(freshness_ttl_days)`. Повертає summary.

### Оркестрація `run()`
1. **Завжди спершу `run_active()`.**
2. Якщо є `passive_schedule` і він **дозрів** (`now − last_passive_at ≥ passive_interval_seconds`) → `run_passive()` + `passive_schedule.mark()`.
3. Якщо `passive_schedule is None` (тести/one-shot) → `run_passive()` виконується завжди (зворотна сумісність із наявними `run()`-тестами).
4. Summary активного й пасивного зливаються (сума полів).
5. Персист мітки — `PassiveSchedule` у `/data/passive_state.json` (`{"last_passive_at": ts}`); нема файлу → дозрів (bootstrap-пасив на першому запуску).

### Активний оминає опубліковані джерела
- **Безумовний host-skip:** у `run_active()` `known_hosts` (хости всіх активних website-джерел) будується й застосовується **завжди**, незалежно від `domain_rating` (раніше було gated на `rating_on`). Активний ніколи не фетчить хост, що вже є джерелом.
- **Прибрати approved-партнерську гілку `site:`-пулу:** активний `site:` лишає лише `registry.top(known_hosts)` (продуктивні, ще-НЕ-заапрувлені); гілку `approved = sorted(known_hosts)` + `approved_cursor` + `bypass_host_skip`-для-заапрувлених — видалити. Recall промо-сторінок на заапрувлених доменах переходить у пасивний deep-walk. (Свідома зміна: частина [[ubd-crawler-site-query]] відкликається, бо суперечить вимозі; функціонал не втрачається — переходить у пасив.)

### Конфіг / ручки
- Нова `passive_interval_seconds` (env `PASSIVE_INTERVAL_SECONDS`, дефолт 172800=48год; **деплой 345600=96год**).
- Нова `passive_state_path` (дефолт `/data/passive_state.json`).
- `active_fetch_budget` 80→**150** (env при деплої).
- `CRAWL_INTERVAL_SECONDS` (активний цикл, entrypoint) 10800→**7200** (env при деплої).
- `now`-колбек інжектиться в `Runner`/`PassiveSchedule` для тестів.
- `docker-entrypoint.sh` без змін (цикл раз на активний інтервал).

## Обсяг / файли
- `crawler/crawler/runner.py` — split `run()` → `run_active()`+`run_passive()`+оркестрація; безумовний host-skip; site:-пул лише registry.
- `crawler/crawler/schedule.py` (new) — `PassiveSchedule` (due/mark, JSON-персист, інжектований `now`).
- `crawler/crawler/config.py` — `passive_interval_seconds`, `passive_state_path`.
- `crawler/crawler/wiring.py` — сконструювати `PassiveSchedule`, передати в `Runner`; `active_fetch_budget` вже прокинутий.
- Тести: `test_schedule.py` (new), `test_runner.py` (run_active не краулить джерела; run_passive краулить+expire_stale; оркестрація: активний перший, пасив лише коли дозрів; host-skip безумовний; site: без approved-гілки), `test_wiring.py` (PassiveSchedule прокинуто).

**НЕ робимо:** зміни бекенда/admin/екстракції/атрибуції; зміни `docker-entrypoint.sh`.

## Тестова стратегія
TDD (crawler pytest, `./.venv/Scripts/python.exe -m pytest -q`). Зворотна сумісність: наявні `run()`-тести (schedule=None) лишаються зеленими. Часті коміти. Гілка → merge (ff) → канонічний ребілд crawler; деплой-env: `PASSIVE_INTERVAL_SECONDS=345600`, `ACTIVE_FETCH_BUDGET=150`, `CRAWL_INTERVAL_SECONDS=7200`.
