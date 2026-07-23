# Crawler: вузький per-domain `site:` (discovery P3-recall)

**Дата:** 2026-07-23
**Трек:** self-growing discovery, P3-важіль (необовʼязковий). Гілка `feat/crawler-site-query` від `main`.
**Скоуп:** лише `crawler/`. Без backend/admin, без БД-схеми, без міграцій.

## Проблема й мета

`DomainWalker` (sitemap-глибина) розкриває productive-домен через `robots → sitemap → BFS≤2`.
Промо-сторінки, яких немає в `sitemap.xml` або що глибші за `BFS≤2`, він пропускає.

**Мета:** для вже-productive домену спитати пошуковик «які промо-сторінки цього домену ти
індексуєш, що ми ще не викраулили?» — вузьким запитом `site:{домен} {промо-термін}`. Це
recall-добавка поверх walker'а на домени, що вже *довели* дохідність оферами.

Свідомо відкинуто раніше (див. [[ubd-crawler-discovery-scaling-brainstorm]]): широкий
`site:*.ua` (throttling + пошуковик обрізає глибину). Тут — **вузько**, по одному домену.

## Тверді рамки (успадковані)

- Людський модераційний гейт лишається — site: лише виробляє кандидатів у модерацію.
- Детермінований core екстракції/атрибуції лишається — site: не чіпає живий гейт.
- DDG-throttling — єдине жорстке обмеження; бюджет левера малий і самообмежений.
- Розширення recall безпечне лише завдяки наявним precision-гейтам ([[ubd-crawler-precision]]):
  audience у запит НЕ додаємо, бо relevance-gate на екстракції її й так забезпечує.

## Затверджені рішення (брейншторм 2026-07-23)

1. **Таргет-домени = `DomainRegistry.top(budget, known_hosts)`** — ті, що вже дали офери.
   Найкращий ROI на дефіцитний DDG-слот. Це переважно ще-НЕ-заапрувлені домени (заапрувлені
   йдуть у пасивний deep-walk і в реєстр не пишуться), тож host-skip-конфлікту немає, а
   виключення `known_hosts` прибирає й корнер-кейс «заапрувлений домен зависає в top».
   Заапрувлених партнерів свідомо НЕ таргетимо (їх покриває пасивний deep-walk щопрохід).
2. **Термін-вісь = лише intent-форми, без audience.** Домен уже звужує простір; `військовим`
   у запиті радше зашкодить (промо-сторінки часто не містять аудиторію у видимому/URL-тексті).
   Audience забезпечує downstream relevance-gate. 1 ротаційний термін на домен за прохід.
3. **Бюджет малий (`site_query_budget`, дефолт 5), левер default ON.** Рівняння на сусідні
   левери (`domain_rating`/`brand_feed` — ON). Вартість самообмежена: під час global-backoff
   провайдер повертає `[]` без sleep (site:-запити — дешеві no-op саме тоді, коли пошук у ямі);
   реальну ціну (~45с/запит) платять лише коли канал живий. `site_query_enabled=False` →
   байт-еквівалентний відкат.

## Архітектура (Підхід A: реюз keyword-шляху, генерація в Runner)

Site:-запит — це звичайний keyword-рядок для наявного шляху
`keyword → build_search_provider → ActiveDiscovery → candidates → ActiveHarvester`.
Генеруємо site:-рядки в runtime (у `Runner.run()`), де доступні `known_hosts` і `domain_registry`,
і проганяємо їх через **той самий** `ActiveDiscovery`.

**Відкинуті альтернативи:**
- **B — генерація в wiring (build-time), як `grid_cursor`:** на build-time немає `known_hosts`
  → або leak (заморожений заапрувлений домен у `top` палить марний запит щопрохід), або зайвий
  другий `api.list_sources`. Гірше без виграшу.
- **C — окремий `SiteQueryHarvester` із власним fetch+attribution+submit:** дублює provider-виклик,
  атрибуцію й сабміт; велика тест-поверхня. Overkill для P3.

### Компоненти

**1. Новий модуль `crawler/discovery/site_query.py`** — чистий генератор, без I/O.

```python
SITE_INTENT_FORMS = (
    "знижка", "акція", "промокод", "спеціальна ціна", "пільгова ціна",
    "спеціальна пропозиція", "сертифікат",
)

class SiteQueryPlanner:
    def __init__(self, terms=SITE_INTENT_FORMS):
        self._terms = tuple(terms)

    def next_batch(self, domains, budget, cursor):
        """One rotating term per domain, capped at budget.
        domain[i] → terms[(cursor + i) % len(terms)]. Advances cursor by 1/pass."""
        if not self._terms:
            return [], cursor
        doms = [d for d in domains if d][:max(0, int(budget))]
        out = [f"site:{d} {self._terms[(cursor + i) % len(self._terms)]}"
               for i, d in enumerate(doms)]
        return out, (cursor + 1) % len(self._terms)
```

`budget` кепить кількість доменів (= кількість запитів, бо 1 термін/домен). `cursor` крутить
фазу термінів між проходами: за `len(terms)` проходів кожен топ-домен обходиться всіма термінами,
а всередині одного проходу різні домени вже беруть різні терміни (модульна індексація, як у
`QueryGrid`).

**2. `crawler/discovery/search_state.py`** — новий персистентний курсор, симетрично `grid_cursor`:
- `"site_cursor": 0` у `_EMPTY`;
- property `site_cursor` + `set_site_cursor(value)` з `_save()` (атомарний запис).
- Старі state-файли підхопляться наявним `setdefault`-циклом у `load()`.

**3. `crawler/config.py`** — два нові прапори (у `_RawSettings`, `Config`, `load_config`):
```python
site_query_enabled: bool = True     # сам левер (default ON)
site_query_budget: int = 5          # макс. доменів (=DDG-викликів) на прохід
```

**4. `crawler/wiring.py`** — побудова планувальника і проброс у `Runner`:
```python
site_planner = None
site_state = None
if config.site_query_enabled:
    from crawler.discovery.site_query import SiteQueryPlanner
    site_planner = SiteQueryPlanner()
    site_state = state if config.active_discovery else None   # state існує лише при active_discovery
```
У конструктор `Runner(...)` додаємо `site_planner`, `site_state`, `site_query_budget`.
(`domain_registry` і `discovery` Runner уже отримує.)

**5. `crawler/runner.py`** — генерація site:-запитів у наявному блоці кандидатів
(усередині `if self._harvester is not None:`, поряд із domain_feed/discovery/brand_feed):
```python
if (self._site_planner is not None and self._site_state is not None
        and self._discovery is not None and self._domain_registry is not None):
    domains = self._domain_registry.top(self._site_query_budget, known_hosts)
    site_queries, new_cur = self._site_planner.next_batch(
        domains, self._site_query_budget, self._site_state.site_cursor)
    self._site_state.set_site_cursor(new_cur)
    if site_queries:
        candidates += self._discovery.run(site_queries, known)
```
Ключове:
- `top(budget, known_hosts)` виключає заапрувлені домени (той самий `known_hosts`, що й у DomainFeed).
- Прогін через **той самий** `ActiveDiscovery` — окремий виклик `.run()`, тож site-запити не
  крадуть grid-бюджет (кожен `.run()` має власний лічильник; site уже обмежений на генерації).
- Site-кандидати додаються **після** brand_feed (найнижчий пріоритет під `active_fetch_budget`);
  harvester фетчить конкретний promo-URL (walker розкриває від нього).
- Курсор просувається раз на реальний прохід і персиститься.

## Гейт (три рівні, будь-який OFF → тихий no-op)

Site:-запити спрацьовують лише коли одночасно:
1. `site_query_enabled=True` (сам левер) — інакше `site_planner=None`, гілка не виконується;
2. `active_discovery=True` — інакше `site_state=None` і `self._discovery=None`;
3. `domain_rating_enabled=True` — інакше `domain_registry=None`.

`site_query_enabled=False` → байт-еквівалентний відкат до pre-track поведінки.
Практичний наслідок: out-of-box (`active_discovery=False`) левер — no-op; вмикається разом із
активним пошуком (а `domain_rating` за замовчуванням уже ON).

## Тести (TDD, crawler-only, поверх baseline 361)

1. **`tests/test_site_query.py`** (новий) — `SiteQueryPlanner`:
   формат `site:{домен} {термін}`; `budget` кепить кількість доменів; ротація курсора (фаза між
   проходами + різні терміни для різних доменів у межах проходу); порожні `terms` → `([], cursor)`;
   порожні/None-домени відфільтровано; детермінізм.
2. **`tests/test_search_state.py`** (новий, або доповнити наявний файл, де вже тестується
   `SearchState`) — `site_cursor` дефолт 0, `set_site_cursor` персиститься, старий файл без ключа
   підхоплюється.
3. **`tests/test_config.py`** (доповнити) — `site_query_enabled`/`site_query_budget` дефолти й проброс.
4. **`tests/test_runner.py`** (доповнити) — з увімкненим левером: `registry.top` викликається з
   `known_hosts`, `discovery.run` отримує site-запити, `set_site_cursor` викликано, кандидати влиті;
   байт-еквівалентність при `site_query_enabled=False` (гілка не виконується).

## Поза скоупом (YAGNI / deferred)

- Заапрувлені домени як site:-таргет (обхід host-skip) — доробити, якщо recall-gap підтвердиться.
- Audience-токен у запиті — додати, лише якщо на реальних даних wasted-fetch виявиться високим.
- Окремий fetch-шлях без walker-розкриття — не потрібен (walker включає site:-URL першим).

## Перевірка завершення

- crawler-тести зелені (baseline 361 + нові), `pytest -q` з `crawler/`.
- Жива Docker-перевірка (як у попередніх треках): левер увімкнено, за наявності rated-доменів
  генеруються коректні site:-запити; при OFF — байт-еквівалентно.
- Фінальне opus whole-branch рев'ю перед merge.
