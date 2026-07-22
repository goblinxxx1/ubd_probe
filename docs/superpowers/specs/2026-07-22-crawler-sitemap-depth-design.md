# Crawler — sitemap-глибина розкриття домену (design)

**Дата:** 2026-07-22
**Трек:** self-growing discovery, крок 3 (після [[ubd-crawler-query-grid]], [[ubd-crawler-brand-domain-feed]])
**Гілка:** `feat/crawler-sitemap-depth`

## Проблема

Discovery-фіди (`brand_feed`, active-search) емітять **homepage** website-кандидатів.
`ActiveHarvester._harvest_one` фетчить рівно **одну** сторінку (homepage) наявним
`WebsiteFetcher`, а промо/знижки живуть на **глибших** сторінках
(`/sale`, `/akcii`, `/акції`, `/znizhki`, `/rozprodazh`). Тому вихід оферів із homepage
майже нульовий. Зв'язка brand-feed → **розкриття глибини** → атрибуція→модерація і дає
реальний вихід оферів — обидва попередні треки самі по собі результату не дають (це
«сантехніка»; див. [[ubd-design-for-whole-picture]]).

## Скоуп (зафіксовано під час брейнштормінгу)

Повний конвеєр розкриття домену для website-кандидата на harvest-шляху:
`robots.txt → sitemap.xml (+ index→дочірні) → URL/HTML промо-фільтр → BFS≤2 fallback →
hard cap → фетч наявним WebsiteFetcher`. Плюс **політ-шар**: robots-кеш, honour Disallow,
Crawl-delay → per-domain rate-limit, per-domain page cap.

**Точка вклинення — `harvest.py:48`** (виклик `fetcher.fetch(...)` усередині
`_harvest_one`). Це за визначенням **лише harvest-шлях** (кандидати brand-feed/active);
краул наявних DB-джерел (`Runner._crawl_source`) **не чіпається**.

**Тверді рамки (з [[ubd-crawler-discovery-scaling-brainstorm]]):** людський модераційний
гейт лишається; детермінований core екстракції лишається; мережа НІКОЛИ не валить/не
блокує прохід (best-effort скрізь); розширення recall безпечне завдяки наявним
precision-гейтам ([[ubd-crawler-precision]]).

## Архітектура (варіант A — виділений walker)

Розглянуто 3 варіанти вбудовування:
- **A. Виділений `DomainWalker`, викликаний harvester'ом** — обрано.
- B. Розкриття всередині `WebsiteFetcher` — відкинуто (роздуває фетчер, змішує політ-політику
  з парсингом, зачіпає краул DB-джерел).
- C. Розкриття як стадія в `Runner` (1 кандидат → N URL-кандидатів) — відкинуто
  (`SourceCandidate` = *джерело*, а не сторінка; ламає модель suggestions/dedup).

A обрано, бо тільки він тримає точку вклинення саме на `harvest.py:48`, лишає `WebsiteFetcher`
простим one-page фетчером і ізольовано тестується (HTTP інʼєктується, як `BrandResolver`).

### Компоненти (нові, `crawler/discovery/`; HTTP інʼєктується; кожен fail-path → порожньо)

| Компонент | Файл | Відповідальність |
|---|---|---|
| `RobotsPolicy` | `discovery/robots.py` | per-domain `robots.txt`: fetch+persist-кеш, парс через stdlib `urllib.robotparser`; віддає `can_fetch(url)`, `crawl_delay()`, `sitemaps()` |
| `collect_sitemap_urls` | `discovery/sitemap.py` | обхід sitemap-index→дочірні→`urlset`, gzip-підтримка, `xml.etree`, cap на к-ть документів |
| `DomainWalker` | `discovery/walker.py` | оркестрація robots→sitemap-URL→промо-фільтр→BFS≤2 fallback→дедуп/cap; повертає `WalkPlan(domain, urls, crawl_delay)` |
| `DomainRateLimiter` | `ratelimit.py` (додати) | `wait(domain, effective_delay)` — як `RateLimiter`, але delay per-call, ключ = домен |

**Промо-URL-лексикон** — курований набір токенів (латиниця+кирилиця:
`sale, promo, akci, akcii, znizhk, rozprodazh, discount, offer, deal, black-friday,
спецпропоз, знижк, акці, розпродаж…`) у `walker.py` поряд із логікою (як `BRANDS` у
`query_grid.py`), матч по нормалізованому (lower + %-decoded) URL-path.

### Потік даних (harvest-шлях)

```
brand-feed/active → website-кандидат (homepage)
  └─ ActiveHarvester._harvest_one(cand):
       plan = walker.walk(cand)          # robots+sitemap+BFS, політ-шар усередині
       for url in plan.urls:             # homepage перший + промо-сторінки, дедуп, cap
           domain_rl.wait(plan.domain, plan.crawl_delay)
           items = WebsiteFetcher.fetch({url, name=cand.name})   # НАЯВНИЙ фетчер, як є
           passing = extract-filter
           ctx = build_page_ctx(cand, passing)   # cand=homepage → _first_party origin вірний
           per-item attribute→submit             # НАЯВНИЙ пайплайн, по-сторінково
```

### Інваріанти

- `WebsiteFetcher` **не змінюється** — переюзається по-URL (одна сторінка = один виклик).
- `cand` (homepage) передається в `build_page_ctx` **завжди**, навіть коли фетчимо `/sale` →
  `_first_party` suggest-origin лишається homepage, а `article_url` оффера = глибока сторінка.
- Атрибуція — **по-сторінково** (кожен URL = свій `ctx`); семантика `offer_block_count` /
  first-person маркера не розмивається між сторінками.
- `DomainRateLimiter` **спільний** для внутрішніх фетчів walker (robots/sitemap/BFS) і
  offer-page фетчів harvester → єдина політ-політика на домен за прохід.
- Краул DB-джерел (`_crawl_source`) і telegram-шлях **не чіпаються**.

## Політ-шар (per-domain, за прохід)

- **robots-кеш** — persist JSON `/data/robots_cache.json` `{domain: {fetched_at, text, status}}`,
  атомарний запис (як `brand_domains.json`), TTL-гейт. Miss/stale → один фетч
  `https://domain/robots.txt` (через `DomainRateLimiter`), зберегти сирий текст, парс stdlib-ом
  при читанні (не серіалізуємо внутрішній стан robotparser).
- **Disallow** — кожен URL (sitemap/BFS/offer) проходить `can_fetch`; заборонений → відкидається
  (включно з homepage: заборонений homepage → `urls=[]` → кандидат пропущено).
- **Crawl-delay** — `effective = min(max(config.domain_min_delay, robots_crawl_delay),
  crawl_delay_cap)` — щоб ворожий `Crawl-delay: 3600` не завісив прохід.
- **per-domain rate-limit** — усі фетчі домену (robots+sitemap+BFS+offer-pages) серіалізуються
  через `DomainRateLimiter.wait(domain, effective)`.

## Бюджети/капи (жорсткі; best-effort — ніколи не валять прохід)

| Кап | Дефолт | Сенс |
|---|---|---|
| `active_fetch_budget` (наявний) | 20 | к-ть **кандидатів (доменів)** за прохід — **сенс не змінюється** |
| `domain_page_cap` | 10 | макс. offer-сторінок на домен за прохід (**включно з homepage**) |
| `sitemap_max_docs` | 20 | cap на к-ть sitemap-документів при рекурсії index→дочірні |
| `bfs_max_depth` | 2 | глибина BFS-fallback |
| `bfs_max_pages` | 8 | cap сторінок BFS (підмножина `domain_page_cap`) |
| `bfs_trigger_min` | 3 | BFS вмикається, коли sitemap дав `<` цього промо-URL (або sitemap відсутній) |

Верхня межа фетчів/прохід = `active_fetch_budget × domain_page_cap` (20×10=200), throttled
per-domain delay. Занижувати дефолти свідомо не будемо (принцип цілісної картини), але
значення — розумно-ввічливі.

## Config-кнопки (нові, `config.py` + `_RawSettings`)

```
sitemap_depth_enabled: bool = True
domain_page_cap: int = 10
sitemap_max_docs: int = 20
bfs_max_depth: int = 2
bfs_max_pages: int = 8
bfs_trigger_min: int = 3
domain_min_delay_seconds: float = 3.0
crawl_delay_cap_seconds: float = 30.0
robots_cache_path: str = "/data/robots_cache.json"
robots_cache_ttl_hours: int = 168
```

Промо-лексикон — **у коді**, не в config.

## Інтеграція в `ActiveHarvester`

`__init__` отримує опційний `walker=None` і `domain_rate_limiter=None`. `_harvest_one`
розкладається:

```python
def _harvest_one(self, cand, fetcher, cats, known, summary):
    if self._walker is not None and cand.type == "website":
        plan = self._walker.walk(cand)              # WalkPlan(domain, urls, crawl_delay)
        urls, domain, delay = plan.urls, plan.domain, plan.crawl_delay
    else:                                            # telegram / walker off → як зараз
        urls, domain, delay = [cand.url_or_handle], None, None
    for url in urls:
        self._wait(cand.type, domain, delay)         # per-domain, або наявний per-platform
        src = {"id": None, "type": cand.type, "url_or_handle": url, "name": cand.name}
        try:
            items, _ = fetcher.fetch(src, None)
            self._process_page(cand, items, cats, known, summary)  # винесена наявна логіка
        except Exception as exc:                      # один битий URL не зриває решту домену
            summary["errors"] += 1
            log.warning("harvest page failed for %s: %s", url, exc)
```

- `_process_page` = винесений наявний блок (extract-filter → `build_page_ctx(cand, …)` →
  per-item `attribute`→submit offer/suggestion). **Логіка не змінюється**, лише зветься per-URL.
- `_wait`: `domain` є → `domain_rl.wait(domain, delay)`; інакше наявний `rl.wait(cand.type)`.
- Бюджет кандидатів (`self._budget`) не чіпаємо; `domain_page_cap` застосований у `walker.walk`.

## Обробка помилок (best-effort — інваріант проєкту)

| Збій | Реакція |
|---|---|
| `robots.txt` fetch/parse впав | «дозволено все», `crawl_delay=config-floor`, `sitemaps=[]` → далі BFS |
| sitemap fetch/parse/gzip впав | той документ → `[]`, решта тривають; замало URL → BFS |
| BFS-сторінка впала | пропустити сторінку; капи не зростають від фейлу |
| offer-page `fetch` кинув | per-URL `try/except` у циклі → `errors += 1`, решта сторінок тривають |
| `walker.walk` кинув цілком | fallback `WalkPlan(urls=[homepage])` (не гірше за поточну поведінку) |

**Ідемпотентність/дедуп:** `plan.urls` дедупляться в walker (нормалізований URL); offer-дедуп —
наявний (`content_hash` бекенд, `known` для suggestions). Homepage завжди перший.

## Wiring (`wiring.py`)

`build_runner`: якщо `config.sitemap_depth_enabled` — збудувати `RobotsPolicy` (persist-кеш),
`DomainRateLimiter`, `DomainWalker` (інʼєкт HTTP-клієнта, robots, rate-limiter, капи) і
передати `walker` + `domain_rate_limiter` в `ActiveHarvester`. `False` → `walker=None`
(стара поведінка біт-у-біт).

## План тестів (TDD)

- **`test_robots.py`** — парс Sitemap/Crawl-delay/Disallow (наш UA і `*`), `can_fetch` allow/deny;
  кеш miss→persist / свіжий→без фетчу / stale→refetch / битий файл→clean start; fetch-фейл → «дозволено все».
- **`test_sitemap.py`** — `urlset`→`<loc>`; index→рекурсія; `.xml.gz` gunzip; `sitemap_max_docs` cap;
  малформ/HTTP-фейл → `[]`; namespace-XML.
- **`test_walker.py`** — sitemap-шлях (промо-фільтр, homepage перший, дедуп, `domain_page_cap`);
  BFS fallback (тригер `<bfs_trigger_min`/відсутній sitemap, in-domain only, `bfs_max_depth`/`bfs_max_pages`);
  Disallow-URL відкинуто; заборонений homepage → `urls=[]`; `crawl_delay` clamp; внутрішній виняток → `[homepage]`.
- **`test_promo_url_filter.py`** — латиниця/кирилиця/%-encoded позитиви, `/product`,`/blog` негативи.
- **`test_ratelimit.py`** (доповнити) — `DomainRateLimiter`: per-domain ізоляція, per-call delay.
- **`test_active_harvest.py`** (доповнити) — walker+website → кілька сторінок, `build_page_ctx` з homepage
  per-page; telegram/walker=None → як зараз; битий URL → решта тривають, `errors+=1`; `domain_page_cap`.
- **`test_config.py`** (доповнити) — нові кнопки/дефолти.
- **`test_wiring.py`** (доповнити) — walker будується при `True`, `None` при `False`.

Наявні 228 тестів лишаються зеленими.

## Свідомо поза скоупом

URL/HTML-фільтр за **вмістом** сторінки (окрім URL-path-токенів) — покладаємось на наявний
relevance-gate екстрактора; domain-rating, snowball, негатив-словник, LLM-хвіст — наступні
треки ([[ubd-crawler-discovery-scaling-brainstorm]]).
