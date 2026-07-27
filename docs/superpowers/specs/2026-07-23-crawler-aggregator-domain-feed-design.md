# Crawler: aggregator as domain feed (follow-through)

**Дата:** 2026-07-23
**Трек:** follow-through по veteranam-флуду. Гілка `feat/crawler-aggregator-domain-feed` від `main`.
**Скоуп:** лише `crawler/`. Без backend/admin, без БД-схеми.

## Проблема й мета

Блоклистнуті агрегатори/каталоги ветеранських знижок (як `veteranam.info`) — це фактично **куровані списки саме наших цільових бізнесів**. Поточний інтерим ([[ubd-crawler-attribution-hardening]], фікс `c5540e4`): блоклистнутий-хост-сторінка **дропається** без salvage (спинили флуд), але її корисні вихідні бізнес-лінки при цьому **пропадають**.

**Мета:** використати блоклистнутий агрегатор як **джерело бізнес-доменів** (не оферів): зібрати його вихідні бізнес-хости → фідити їх кандидатами → харвестер фетчить **сайт самого бізнесу**, walker розкриває промо → **first-party** офер (`provider`=бізнес, `site_url`=бізнес) → модерація. Аркуш агрегатора офера НЕ дає.

## Затверджені рішення (брейншторм 2026-07-23)

1. **Автофід** (як brand/osm), не human-gate доменів. Людський гейт лишається на рівні **офера** (`pending_review`). Human-gate кожного домену з каталогу непрактичний (сотні) і неузгоджений із наявними фідами.
2. **Майнити лінки лише з блоклистнутих хостів** — людськи-куровані високоточні каталоги (veteranam.info). Евристичні media (is_article / багато-outbound) свідомо НЕ майнимо (доменний шум вищий; можна розширити пізніше).
3. **Persist + re-feed** (дзеркало OSM-фіду), не інлайн-майн у тому ж проході — розтягує fan-out, бюджетує, без інлайн-вибуху.

## Архітектура

Той самий патерн, що OSM-фід ([[ubd-crawler-osm-domain-feed]]): стор доменів наповнюється, окремий фід ротаційно/бюджетовано подає їх кандидатами.

**Декаплінг проходів:** харвестер пише вихідні хости у стор наприкінці проходу; фід читає стор на старті **наступного** проходу (кожен прохід — свіжий `build_runner`). Тож щойно-зібрані хости фідяться наступного разу — fan-out розтягнутий і бюджетований.

### Компоненти

**A. Capture — `crawler/discovery/harvest.py`**
У `ActiveHarvester._process_page`: обчислити вихідні бізнес-хости (`_outbound_hosts(passing)` з `attribution` — він уже виключає блоклистнуті); якщо `is_blocked_host(ctx.host)` **і** є вихідні хости → `self._aggregator_store.add(hosts)`. Дроп агрегатор-офера лишається (кожен `attribute()` для блоклистнутого повертає None — без регресії до фіксу флуду). Store інжектиться в `ActiveHarvester.__init__` (як `domain_registry`), дефолт `None` → capture off, байт-еквівалентно.

**B. Store — `crawler/discovery/aggregator_feed.py` (новий), `AggregatorDomainStore`**
Дзеркало `BrandDomainCache`: персистентний JSON (**упорядкований** набір хостів; ротаційний `cursor`; freshness-gate не потрібен — стор накопичується безперервно), атомарний запис, tolerant-load. Методи: `add(hosts, cap: int)` — union наявних + нових зі **збереженням порядку** (наявні першими, нові в кінець, без дублів); коли `len > cap` — лишити **найновіші `cap`** (обрізати найстаріші з початку), щоб свіжі відкриття завжди входили; `domains() -> list[str]`; `cursor()`/`set_cursor()`.

**C. Feed — `crawler/discovery/aggregator_feed.py`, `AggregatorDomainFeed`**
Дзеркало `OsmDomainFeed`: ротаційне вікно `per_pass` website-`SourceCandidate` із стору через персистентний курсор; дедуп проти `known` (`normalize_ref`); `discovery_note=f"aggregator-feed:{host}"`; порожній стор → `[]`.

**D. Wiring — `crawler/wiring.py`**
`_build_aggregator_feed(config)` — завантажити `AggregatorDomainStore(config.aggregator_domains_path)`, повернути `AggregatorDomainFeed(store, per_pass=...)`. Store будується коли `config.aggregator_feed_enabled`, **інжектиться і в harvester (capture), і у фід** (один і той самий шлях/інстанс). Фід передається в `Runner`; його кандидати вливаються в наявний interleave (поряд із domain/brand/osm). Harvester отримує `aggregator_store=store` + `aggregator_max_domains` (cap для `add`).

**E. Config — `crawler/config.py`**
```python
aggregator_feed_enabled: bool = True      # default ON
aggregator_feed_per_pass: int = 20
aggregator_domains_path: str = "/data/aggregator_domains.json"
aggregator_max_domains: int = 500
```
`aggregator_feed_enabled=False` → store не будується (`None`) → capture off + фід не будується → байт-еквівалентний відкат.

## Безпека / узгодженість

- Нові домени — лише **кандидати**; наявні precision-гейти (relevance-gate атрибуції, host-blocklist) + людська модерація нижче за потоком. `_outbound_hosts` пре-фільтрує блоклистнуті, тож інші блок-хости у фід не потраплять.
- Дедуп через `known`; host-skip заапрувлених доменів працює як у інших фідів.
- Офери — `pending_review`, як усе. Аркуш агрегатора — 0 оферів (інтерим-drop збережено).

## Межі скоупу (YAGNI)

- Евристичні media як джерело лінків — НЕ тут (лише блоклистнуті).
- Скоринг/рейтинг агрегатор-доменів — НЕ тут (простий union-стор; productive-домени й так підхопить наявний `DomainRegistry` через харвест).
- Per-page cap лінків — НЕ окремо; `aggregator_max_domains` кепить весь стор.

## Тести (crawler, pytest; без mysql; поверх baseline 403)

1. **`test_aggregator_feed.py`** (новий) — `AggregatorDomainStore`: `add` union+дедуп+cap; `domains`; курсор дефолт 0/персист; tolerant-load. `AggregatorDomainFeed`: ротація вікна; дедуп проти `known`; форма `SourceCandidate` (`type=website`, `discovery_note=aggregator-feed:`); порожній стор → `[]`.
2. **`test_active_harvest.py`** (доповнити) — capture: блоклистнутий-хост-сторінка з вихідними бізнес-лінками → `store.add` викликано з тими хостами; звичайна (не-блоклистнута) сторінка → store НЕ чіпається; `aggregator_store=None` → байт-еквівалентно (нічого не капчиться).
3. **`test_config.py`** (доповнити) — нові прапори дефолти + env-override.
4. **`test_wiring.py`** (доповнити) — `aggregator_feed_enabled=True` → `runner._aggregator_feed` є `AggregatorDomainFeed`, harvester отримав store; `False` → обидва None.
5. **`test_runner.py`** (доповнити) — кандидати aggregator-фіду влиті у harvest (стаб-фід).

## Перевірка завершення

- crawler-тести зелені (baseline 403 + нові), `pytest -q` з `crawler/`.
- Фінальне opus whole-branch рев'ю перед merge.
- Жива Docker-перевірка: після кроулу блоклистнутого агрегатора у `aggregator_domains.json` зʼявляються бізнес-хости; наступного проходу вони йдуть кандидатами (лог `aggregator-feed:`).
