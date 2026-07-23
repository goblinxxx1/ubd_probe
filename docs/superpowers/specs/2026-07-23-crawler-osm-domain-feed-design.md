# Crawler: OSM-енумераційний фід доменів (auto-fill каталогу)

**Дата:** 2026-07-23
**Трек:** закриття тріщини #1 аудиту цілісності ([[ubd-design-for-whole-picture]]) — перша (і головна) підзадача. Гілка `feat/crawler-osm-domain-feed` від `main`.
**Скоуп:** лише `crawler/`. Без backend/admin/public, без БД-схеми.

## Проблема

Самонаповнення каталогу доменів (`DomainRegistry`+`DomainFeed`, трек domain-rating) **існує**, але **голодне на нові домени**: єдине джерело запису в реєстр — домени, які харвестер фактично зафетчив (`harvest.py:55`), а харвест годується з `domain_feed` (уже відомі), `brand_feed` (**фіксовані 48** `BRAND_SEEDS`) і двох DDG-викликів (`discovery.run` grid/site: — **мертві**: throttle/CAPTCHA). Тобто genuinely нові домени приходили лише через DDG → реєстр рециркулює ті самі 48 брендів.

«Бренд-БД (OSM) як прямий фід доменів» був у брейнштормі **найбільшим важелем**, але побудований лише як **резолвер** фіксованих 48 назв (`nwr["brand"="{конкретний}"]`) — не як **енумерація** нових брендів. Пів-важеля.

## Мета

DDG-незалежно **енумерувати** мережеві бренди України з OpenStreetMap і фідити їхні домени в наявний конвеєр `walker → модерація → DomainRegistry`, щоб самонаповнення отримало реальне паливо (сотні мереж замість 48). Best-effort, рідкісний refresh, дзеркалить наявний brand-feed патерн.

## Затверджене рішення (брейншторм 2026-07-23)

Джерело нових доменів = **OSM/Overpass-енумерація** (авто, DDG-незалежно, узгоджено з наявним `BrandResolver`, що вже говорить з Overpass). Ручне розширення списку відкинуто (не «auto»). Ретайр мертвих DDG-левер + SearXNG — **окремий follow-up трек**, тут не змішуємо.

## Архітектура (дзеркалить brand-feed)

### 1. `crawler/discovery/osm_feed.py` — новий модуль

**`OsmEnumerator`** — best-effort енумерація через Overpass (HTTP інжектиться для тестів):
- Запит на POI України з `brand` + (`website`|`contact:website`):
  ```
  [out:json][timeout:180];
  area["ISO3166-1"="UA"][admin_level=2]->.ua;
  ( nwr(area.ua)["brand"]["website"];
    nwr(area.ua)["brand"]["contact:website"]; );
  out tags 20000;
  ```
- Парсинг+агрегація: для кожного елемента `brand=tags["brand"]`, `host=bare_host(website|contact:website)`; накопичити `brand → Counter(hosts)`.
- **Шумо-фільтр:** для кожного бренду взяти найчастіший host; лишити, якщо POI-count ≥ `min_pois` (реальна мережа) **і** host не в блоклисті (`blocklist.is_blocked_host`); дедуп за host (стабільний sort брендів, перший виграє); cap до `max_domains`.
- Провал HTTP / порожньо → повертає `{}` (викликач лишає старий кеш).
- Сигнатура: `enumerate() -> dict[str, str]` (brand→host).

**`OsmDomainFeed`** — емітер, дзеркало `BrandFeed.candidates`:
- Ітерує `sorted(cache.domains())` (виявлені бренди) ротаційним вікном `per_pass` через персистентний курсор кешу.
- Дедуп проти `known` (`normalize_ref`); емітить `SourceCandidate(type="website", url_or_handle=f"https://{host}", discovery_note=f"osm-feed:{host}")`.
- Порожній кеш → `[]`.

### 2. Кеш — реюз `BrandDomainCache`

`BrandDomainCache` ([brand_feed.py:83](crawler/crawler/discovery/brand_feed.py)) вже є JSON brand→domain кеш із refresh-freshness gate, ротаційним курсором і атомарним записом — **перевикористовуємо** його (окремий файл `osm_domains_path`). Overpass чіпаємо лише на refresh; проходи читають офлайн.

### 3. `crawler/wiring.py` — `_build_osm_feed`

Дзеркало `_build_brand_feed`, після `blocklist.reload_learned` (щоб фільтр блоклиста працював на enumeration):
```python
def _build_osm_feed(config):
    cache = BrandDomainCache.load(config.osm_domains_path)
    if cache.is_stale(config.osm_feed_refresh_hours * 3600):
        try:
            domains = OsmEnumerator(
                overpass_url=config.overpass_url, timeout=config.request_timeout,
                min_pois=config.osm_min_pois, max_domains=config.osm_feed_max_domains).enumerate()
            if domains:
                cache.replace(domains)
        except Exception as exc:  # noqa: BLE001 — refresh best-effort; feed uses cache
            log.warning("osm-domain enumeration failed: %s", exc)
    return OsmDomainFeed(cache, per_pass=config.osm_feed_per_pass)
```
Будується лише коли `config.osm_feed_enabled`; передається в `Runner`.

### 4. `crawler/runner.py`

Новий kw-параметр `osm_feed=None` (в кінці, з дефолтом). У блоці кандидатів поряд із brand_feed:
```python
if self._osm_feed is not None:
    candidates += self._osm_feed.candidates(known)
```
Ті самі кандидати → harvester → walker → registry.record → модерація. Порядок: після brand_feed.

### 5. `crawler/config.py` — нові прапори

```python
osm_feed_enabled: bool = True          # цільове паливо auto-fill (default ON)
osm_feed_refresh_hours: int = 336      # ~14 днів, як brand_feed
osm_feed_per_pass: int = 20
osm_domains_path: str = "/data/osm_domains.json"
osm_feed_max_domains: int = 500
osm_min_pois: int = 2                  # бренд має бути на ≥2 POI (реальна мережа)
```
`overpass_url` перевикористовуємо. `osm_feed_enabled=False` → wiring не будує фід (`osm_feed=None`) → байт-еквівалентний відкат.

## Безпека recall

Нові домени — лише **кандидати**; наявні precision-гейти (медіа/агрегатор host-blocklist, relevance-gate атрибуції — [[ubd-crawler-precision]], [[ubd-crawler-attribution-hardening]]) + людська модерація стоять нижче за потоком. Ширший приплив безпечний — саме для цього гейти будувались. Enumeration ще й пре-фільтрує блоклистнуті хости.

## Межі скоупу (що НЕ робимо)

- Ретайр мертвих DDG-левер (query-grid, site:, ActiveDiscovery-провайдер) + вестиж SearXNG — **окремий follow-up трек** (coherence-cleanup).
- Wikidata SPARQL як друге джерело енумерації — можливе майбутнє; v1 = Overpass (уже wired).
- Не чіпаємо фіксований `BRAND_SEEDS`/`BrandFeed` — OSM-фід **додатковий**; перетини доменів дедупляться природно (`known`).

## Тести (crawler, pytest; без mysql; поверх baseline 381)

1. **`test_osm_feed.py`** — `OsmEnumerator` (інжектнутий fake-client повертає штучні Overpass elements): агрегація brand→host; `min_pois`-фільтр (одиничний POI відсіяно); дедуп за host; cap `max_domains`; `website`↔`contact:website` fallback; елементи без brand/website пропущено; блоклистнутий host відсіяно; HTTP-провал → `{}`.
2. **`test_osm_feed.py`** — `OsmDomainFeed`: ротаційне вікно з кешу; дедуп проти `known`; форма `SourceCandidate` (`type=website`, `discovery_note=osm-feed:`); порожній кеш → `[]`; курсор просувається.
3. **`test_config.py`** (доповнити) — нові прапори: дефолти + env-override.
4. **`test_wiring.py`** (доповнити) — `osm_feed_enabled=True` → `runner._osm_feed` є `OsmDomainFeed` (fresh кеш, без мережі); `False` → `None`.
5. **`test_runner.py`** (доповнити) — з `osm_feed` кандидати влиті у harvest (стаб-фід), поряд із brand/domain feed.

## Перевірка завершення

- crawler-тести зелені (baseline 381 + нові), `pytest -q` з `crawler/`.
- Фінальне opus whole-branch рев'ю перед merge.
- (Жива Overpass-перевірка опційна: enumeration повертає непорожній набір UA-доменів — але мережа/rate-limit роблять це best-effort; поведінка вичерпно покрита юнітами з fake-client.)
