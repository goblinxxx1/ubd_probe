# Crawler domain-rating — design spec

**Дата:** 2026-07-22
**Трек:** self-growing discovery, важіль 3 («snowball + domain-rating → список росте сам»)
**Гілка:** `feat/crawler-domain-rating` (від `main`)
**Пам'ять:** [[ubd-crawler-discovery-scaling-brainstorm]], [[ubd-crawler-brand-domain-feed]],
[[ubd-crawler-sitemap-depth]], [[ubd-design-for-whole-picture]]

## 1. Контекст і мета

Discovery-конвеєр уже виробляє офери: `brand_feed`/DDG-`discovery` дають website-кандидатів →
`DomainWalker` (sitemap-глибина) розкриває їх у промо-сторінки → атрибуція → людська модерація.
Але є дві діри, які закриває цей трек:

1. **Забування productive-доменів.** Домен, знайдений раз через DDG чи walker-розкриття, що дав
   офер, **не памʼятається** як майбутній кандидат — поки хтось вручну не аппрувне його
   suggestion у формальний `Source`. Немає памʼяті «цей домен вартий повторного візиту».
2. **Порядок = доля.** `ActiveHarvester.harvest()` бере кандидатів **у порядку списку** до
   `active_fetch_budget` (20). Перевірені домени й нові конкурують за ті самі слоти без
   пріоритезації; хвіст голодує (тому `brand_feed` уже має ротацію).

**Мета:** persistent crawler-side рейтинг доменів, що (а) наповнюється з КОЖНОГО активно
фетченого website-домену, (б) сам ре-фідить перевірені домени як кандидатів (DDG-незалежно),
(в) пріоритезує бюджет під них, (г) гасить і викидає мертві/шумні домени. Список джерел росте
сам, без ручного аппруву на кожен productive-домен.

Плюс дві звʼязані вимоги цілісності (див. §4, §5), без яких трек регресує покриття:
host-рівневий skip заапрувлених доменів з активного шляху, і глибокий walk заапрувлених
доменів пасивним source-loop'ом.

## 2. Тверді інваріанти (не порушувати)

- **Живий модераційний гейт незмінний.** Реєстр впливає ЛИШЕ на те, кого й у якому порядку
  активно фетчимо. Кожен офер усе одно йде в людську модерацію. Авто-промоушн домену в
  candidate-feed **не** оминає жоден live-гейт.
- **Детермінований core екстракції недоторканий** (regex/лексикони, наявний тест-контракт).
  Рейтинг — окремий шар навколо фетчу, не в extract.
- **Best-effort скрізь:** реєстр/фід/walk НІКОЛИ не валять прохід (як `brand_feed`/walker).
- **`domain_rating_enabled=False` ⇒ byte-еквівалент поточної поведінки** (ні запису, ні фіда,
  ні host-skip). Дефолт — ON (узгоджено з `brand_feed_enabled`/`sitemap_depth_enabled`).
- **Тільки website.** Реєстр keyed by bare host; telegram/IG/FB-хендли поза скоупом.
- **Backend недоторканий.** Увесь стан — crawler-side JSON (рішення користувача:
  узгоджено з `search_state.json`/`brand_domains.json`/`robots_cache.json`).

## 3. Компоненти

Три нові crawler-side одиниці + інтеграція у наявні `harvest.py`/`runner.py`/`wiring.py`.

### 3.1 `discovery/domain_registry.py` — `DomainRegistry`

Persistent JSON `/data/domain_registry.json`, атомарний запис (той самий патерн, що
`BrandDomainCache._save`: `tmp`+`os.replace`). Ключ — **bare host** (переюзати `_host()` з
`walker.py`: strip scheme/userinfo/port/`www`).

Формат:
```json
{
  "version": 1,
  "domains": {
    "silpo.ua": {
      "score": 1.9, "offers": 3, "errors": 0, "passes": 4,
      "empty_passes": 1, "first_seen": 1700000000.0,
      "last_seen": 1700600000.0, "last_offer": 1700500000.0
    }
  }
}
```

API:
- `load(path, clock=time.time) -> DomainRegistry` — best-effort (corrupt → чистий), `setdefault`
  бекфіл ключів як `BrandDomainCache.load`.
- `record(host, offers: int, errors: int) -> None` — оновлює score (див. §3.2) + лічильники
  (`offers`/`errors` кумулятивні; `passes += 1`; `empty_passes += 1` якщо `offers == 0`;
  `last_seen = clock()`; `last_offer = clock()` якщо `offers > 0`; `first_seen` при створенні).
  **Не** зберігає одразу (батч-запис у кінці проходу — `save()`).
- `top(n, known_hosts) -> list[str]` — до `n` хостів зі `score >= promote_min_score`,
  відсортованих `(-score, host)` (детерміновано), пропускаючи `host in known_hosts`.
- `prune(evict_min_score, evict_ttl_seconds) -> int` — видаляє записи зі
  `score < evict_min_score` І `clock() - last_seen >= evict_ttl_seconds` (холодні + старі).
  Повертає к-ть видалених. Тримає файл bounded.
- `save() -> None` — атомарний персист.

Конструктор приймає score-параметри (decay/offer_weight/error_weight/promote_min_score) —
інжектяться з config, тестуються детерміновано.

### 3.2 Модель score

Експоненційне згасання + винагорода. На кожен `record(host, offers, errors)`:
```
score = max(0.0, score * DECAY + offers * OFFER_WEIGHT - errors * ERROR_WEIGHT)
```
Дефолти: `DECAY=0.9`, `OFFER_WEIGHT=1.0`, `ERROR_WEIGHT=0.5`, `promote_min_score=0.5`.
Наслідок: 1 офер (`score=1.0 ≥ 0.5`) промотує домен у фід; домен, що перестав давати офери,
згасає (×0.9/прохід) і врешті падає нижче `evict_min_score=0.1` → `prune`.

**Poison-захист — наявний, окремого вета не треба:** медіа/держ/агрегатор-домени вже відсіює
attribution-blocklist → вони не дають оферів → score не росте → у фід не потрапляють.

### 3.3 `discovery/domain_feed.py` — `DomainFeed`

`DomainFeed(registry, per_pass)` → `candidates(known_hosts) -> list[SourceCandidate]`:
емітить `registry.top(per_pass, known_hosts)` як `website` `SourceCandidate`
(`url_or_handle=f"https://{host}"`, `discovery_note=f"domain-rating:{host}"`), DDG-незалежно —
рівно як `BrandFeed`. Це «самонаповнення»: домен, який раз дав офер, стає **постійним**
кандидатом без потреби ставати формальним `Source`.

## 4. Host-рівневий skip заапрувлених доменів (вимога цілісності)

Заапрувлений домен = активний `Source` (`known = list_sources(is_active=True)`). Такий домен
краулить **пасивний** source-loop; **активний** шлях (DDG/brand/domain-feed + walker) його
взагалі не чіпає — це економить запити (вимога користувача).

Механізм: у `runner.run()` будуємо `known_hosts = {_host(s.url_or_handle) for s in sources
if s.type == "website"}`. Передаємо в harvest. У `ActiveHarvester.harvest()` для
website-кандидата пропускаємо, якщо `_host(cand.url_or_handle) in known_hosts` — **до**
walker-розкриття (тобто й підсторінки заапрувленого домену активно не фетчаться). `DomainFeed`
теж фільтрує `known_hosts`, щоб не палити слоти. Наявний `normalize_ref`-skip лишається для
non-website типів.

## 5. Глибокий walk заапрувлених доменів пасивним loop'ом (вимога цілісності)

Sitemap-глибина зараз вкручена ЛИШЕ в active harvest; пасивний `_crawl_source` — плаский
(фетчить один URL джерела). Якщо ми host-skip'аємо заапрувлені домени з активного (walker-
оснащеного) шляху, то без цього кроку втратили б глибокий крол саме перевірених доменів.

Тому: у `Runner._crawl_source`, для **website**-джерел, коли `sitemap_depth_enabled`,
розкриваємо джерело тим самим `DomainWalker` і фетчимо КОЖНУ сторінку через `WebsiteFetcher`
під спільним `DomainRateLimiter`, ганяючи наявну пасивну екстракцію ПОСТОРІНКОВО
(offer-extract + `extract_source_candidates` suggestions + corpus record як зараз). Провайдер =
`source["name"]` (пасивна семантика, БЕЗ активної attribution). Telegram/IG/FB-джерела —
недоторкані (walker website-only). `crawl_state` best-effort: `set_crawl_state` останнім
`new_key` (backend і так дедупить офери за `content_hash`/`target_url`, тож ре-крол сторінок
безпечний — освіжає `last_seen_at`, не плодить дублі). Бюджет сторінок = наявний
`domain_page_cap`.

`DomainWalker`+`DomainRateLimiter` стають доступні і `Runner` (не лише harvester) — спільні
інстанси → єдиний per-domain політ-шар для active+passive.

## 6. Інтеграція та порядок бюджету

`Runner.run()` (active-блок) — explore/exploit розкладка:
```
candidates = domain_feed.candidates(known_hosts)      # exploit: перевірені, score-sorted, ≤ per_pass
           + discovery.run(keywords, known)            # explore: нове з DDG
           + brand_feed.candidates(known)              # explore: ротація брендів
harvester.harvest(candidates, cats, known, known_hosts, summary)
```
`domain_feed_per_pass` (дефолт **8**) резервує слоти перевіреним, лишає ~12 з
`active_fetch_budget=20` під розвідку. Гейт: `domain_feed` будується лише якщо
`domain_rating_enabled`.

**Запис у реєстр:** `ActiveHarvester._harvest_one` для website-кандидата агрегує `offers` і
`errors` цього домену за прохід і кличе `registry.record(host, offers, errors)` (host з
`plan.domain`). Реєстр `save()` + `prune(...)` — у кінці проходу (у `runner`, як
`search_state`). Non-website кандидати реєстр не чіпають.

**Snowball-петля (наскрізний e2e):** прохід 1: DDG/brand дає новий домен `X` → harvest → офер →
`record(X, offers=1)` → `score(X)=1.0`. Прохід 2: `DomainFeed` сам емітить `X`. Модерація:
suggestion `X` аппрувнуто → `X` стає активним `Source` → потрапляє в `known_hosts` → активний
шлях його пропускає (§4), пасивний source-loop глибоко краулить (§5). Якщо `X` перестав давати
офери → score згасає → `prune` викидає з фіда.

## 7. Конфіг (дзеркально `config.py` × RUN.md × `.env.example`)

| knob | env | default |
|---|---|---|
| `domain_rating_enabled` | `DOMAIN_RATING_ENABLED` | `True` |
| `domain_registry_path` | `DOMAIN_REGISTRY_PATH` | `/data/domain_registry.json` |
| `domain_feed_per_pass` | `DOMAIN_FEED_PER_PASS` | `8` |
| `domain_score_decay` | `DOMAIN_SCORE_DECAY` | `0.9` |
| `domain_offer_weight` | `DOMAIN_OFFER_WEIGHT` | `1.0` |
| `domain_error_weight` | `DOMAIN_ERROR_WEIGHT` | `0.5` |
| `domain_promote_min_score` | `DOMAIN_PROMOTE_MIN_SCORE` | `0.5` |
| `domain_evict_min_score` | `DOMAIN_EVICT_MIN_SCORE` | `0.1` |
| `domain_evict_ttl_hours` | `DOMAIN_EVICT_TTL_HOURS` | `720` |

## 8. Тестування (TDD, crawler лишається зелений; зараз 299)

- `DomainRegistry`: score-decay математика (детермінований float), `record` лічильники/timestamps
  (інжектований clock), `top` сортування + `known_hosts`-skip + `promote_min_score`-поріг,
  `prune` (score І ttl обидва), load corrupt/backfill, атомарний save round-trip.
- `DomainFeed`: емісія top-N як website-кандидатів, skip `known_hosts`, порожній реєстр → `[]`,
  детермінований порядок.
- Host-skip у `harvest`: website-кандидат із хостом ∈ `known_hosts` пропущено ДО walk; non-website
  через `normalize_ref` як раніше; запис у реєстр лише для website.
- Пасивний walk у `Runner._crawl_source`: website-джерело розкрито walker'ом, кожна сторінка
  фетчиться+екстрактиться, telegram/IG/FB незмінні, `crawl_state` виставлено, gated
  `sitemap_depth_enabled`.
- `wiring`: гейт ON будує registry+feed і передає walker/domain_rl у Runner; OFF → byte-еквівалент
  (жодного нового обʼєкта, поведінка як зараз).
- E2e (§6): домен дав офер → наступний прохід у фіді → аппрув → у `known_hosts` → активний
  пропускає, пасивний walk'ає.

## 9. Свідомо поза скоупом / відкладено

- Telegram/IG/FB rating (handle-space) — окремий трек за потреби.
- Рейтинг пасивних sources (вони й так гарантований крол) — реєстр суто active-scope.
- LLM-хвіст, бренд-якорні запити — наступні важелі (P3), окремі треки.
- Backend `domain_rating`-таблиця — свідомо відкинуто на користь crawler-side JSON.
