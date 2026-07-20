# DDG-антиблок: стабілізація активного пошуку без блокування IP

**Дата:** 2026-07-20
**Трек:** `feat/ddg-antithrottle`
**Скоуп:** тільки анти-блокування активного пошуку (DuckDuckGo/`ddgs`). Backend/admin/public не чіпаємо.

## Проблема

Активний discovery ганяє `ddgs().text(keyword, backend="duckduckgo,brave,google,mojeek,startpage,wikipedia,yahoo,grokipedia")`.
`ddgs` 9.14.4 на списку бекендів стріляє їх **у фіксованому порядку**, ~2 паралельно, і
**зупиняється, щойно набрав `max_results`**. На практиці перші два — `duckduckgo`+`brave` — щоразу
дають достатньо результатів, тож **саме вони з'їдають 100% навантаження** на кожному keyword
кожного проходу. Наслідок — пошуковики глушать наш єдиний вихідний IP (rate-limit/CAPTCHA), і
активний пошук деградує до нуля.

Обмеження: **Brave API відкинуто** (платний), проксі/Tor у цьому треку **не використовуємо**
(одна IP-адреса). Швидкість проходу **не важлива** — важлива відсутність блокування.

## Мета

Тримати per-endpoint частоту звернень настільки низькою, щоб блокування стало малоймовірним, а
коли якийсь ендпоінт таки заблокував — **м'яко перетікати** на інші, а не падати. Усе — на одній
IP, без платних сервісів.

## Ключова знахідка (чому це працює)

Кілька «пошуковиків» `ddgs` ходять в один апстрім результатів, але **б'ють різні HTTP-ендпоінти**,
і саме ендпоінт лімітує наш IP:

| Движок `ddgs` | Джерело результатів | Ендпоінт (лімітує наш IP) | UA |
|---|---|---|---|
| `google` | Google | google.com | ★★★ |
| `startpage` | Google | startpage.com (проксі) | ★★★ |
| `duckduckgo` | Bing | duckduckgo.com | ★★ |
| `yahoo` | Bing | search.yahoo.com | ★★ |
| `brave` | Brave | search.brave.com | ★★ |

**Пул для ротації (рішення):** `google, startpage, duckduckgo, yahoo, brave` (5 ендпоінтів).
Викинуто: `mojeek` (крихітний індекс, слабко для UA), `wikipedia`/`grokipedia` (енциклопедії, не
веб-пошук — чистий шум), `yandex` (рос., уже було виключено). Один запит б'є **один** ендпоінт →
кожен бачить наш IP лише ~1/5 часу.

## Архітектура

Три частини навколо наявного DDG-провайдера в `crawler/crawler/discovery/`:

1. **`RotatingDdgProvider`** (заміна `DuckDuckGoProvider`) — один бекенд на запит, round-robin по
   пулу, пропуск бекендів у cooldown; тримає per-backend circuit-breaker.
2. **`SearchCache`** — декоратор `keyword → результати` з TTL; кеш-хіт = нуль мережі й нуль sleep.
3. **`SearchState`** — один JSON-файл (атомарний запис, інжектована `clock`), що переживає рестарт
   контейнера: per-backend cooldown, кеш keyword'ів, курсор ротації, глобальний `next_allowed_at`.

Провайдер лишається `Callable[[str], list[SourceCandidate]]`, тож `ActiveDiscovery`/`build_search_provider`
не змінюють контракт (лише конструювання). `SearxngProvider` — **без змін**.

### Потік на один keyword (в `ActiveDiscovery` через провайдер)

```
0. Глобальний backoff: now < state.next_allowed_at ?  → активний пошук цього запуску весь пропускаємо
1. Кеш: свіжий запис для keyword (age < TTL) ?         → повертаємо кешовані кандидати, без мережі
2. Інакше: backend = наступний здоровий у ротації
     немає здорових (усі в cooldown) ?                 → state.next_allowed_at = now + global_backoff; обрив run
   sleep(min_delay * (1 + rand[0, jitter]))            → тільки тут, на реальному виклику
   results = ddgs().text(keyword, max_results, backend=<один>)
     успіх         → класифікуємо; кешуємо; backend.fails = 0, cooldown знято
     Ratelimit/DDGSException/інше → backend.fails += 1
                     backend.cooldown_until = now + min(base * 2^(fails-1), cap) * (1 + rand jitter)
                     keyword один раз перетікає на наступний здоровий backend (крок 2)
```

## Компоненти — деталі

### 1. `RotatingDdgProvider`

- Конструктор: `(pool: list[str], results_per_keyword, min_delay, jitter, state: SearchState,
  cooldown_base, cooldown_cap, ddgs_factory=DDGS, sleep=time.sleep, clock=time.time, rand=random.random)`.
- `__call__(keyword)`:
  - обирає наступний здоровий бекенд, стартуючи від `state.cursor` (round-robin, персиститься);
  - якщо здорових немає → кидає внутрішній сигнал `AllBackendsCooling` (ловить `ActiveDiscovery`-обгортка → глобальний backoff + обрив);
  - `sleep`, потім `ddgs_factory().text(keyword, max_results=n, backend=backend)`;
  - результати класифікує наявним `classify_candidate` → `list[SourceCandidate]` (`discovery_note=f"ddg:{backend}: {keyword}"`);
  - на винятку — cooldown бекенда й **одна** спроба на наступному здоровому бекенді для того ж keyword; повторний виняток на другому — повертаємо `[]` для цього keyword (без обриву всього run, якщо ще лишились здорові).
- «Здоровий» = `now >= cooldown_until`. Успіх скидає `fails=0`, `cooldown_until=0`.
- Курсор просувається на 1 після кожного **мережевого** вибору бекенда (не на кеш-хітах).

### 2. `SearchCache`

- Обгортка: `SearchCache(inner_provider, state, ttl_seconds, clock)`.
- `__call__(keyword)`: якщо `state.cache[keyword]` існує й `now - ts < ttl` → десеріалізує збережені
  кандидати й повертає (без виклику `inner`). Інакше викликає `inner(keyword)`, зберігає результат у
  `state.cache[keyword] = {ts, candidates:[{name,type,url_or_handle}]}`, повертає.
- Кешуємо **порожній** результат теж (щоб не гатити той самий keyword, що нічого не дав) — з тим самим TTL.
- Ключ нормалізуємо: `keyword.strip().casefold()`.

### 3. `SearchState`

- Один файл `search_state_path` (JSON). Форма:
  ```json
  {
    "version": 1,
    "cursor": 0,
    "next_allowed_at": 0,
    "backends": { "google": {"fails": 0, "cooldown_until": 0}, ... },
    "cache": { "<keyword>": {"ts": 0, "candidates": [ {"name","type","url_or_handle"} ] } }
  }
  ```
- Завантаження: якщо файлу нема/битий — стартуємо з порожнього стейту (best-effort, лог `warning`).
- Запис: **атомарний** (`tmp` файл + `os.replace`). Флаш робимо **після кожного мережевого виклику**
  (тобто раз на ~`min_delay` секунд) — так cooldown/кеш/курсор переживають краш посеред `run`; диск
  тут дешевий супроти 45-секундної паузи. На кеш-хітах (без мережі) флаш **не** робимо.
- Уся мутація стейту йде через методи `SearchState` (інкапсуляція); `clock` інжектується.
- Прибирання кеша: при завантаженні (або запису) відкидаємо записи, старші за TTL — щоб файл не ріс безмежно.

## Конфіг (`crawler/crawler/config.py` + `.env.example`)

Нові / змінені ключі (усі з дефолтами, парсинг CSV як уже є):

| Ключ | Дефолт | Призначення |
|---|---|---|
| `search_backends` | `google,startpage,duckduckgo,yahoo,brave` | пул ротації (CSV) |
| `search_state_path` | `/data/search_state.json` | персистентний стейт-файл |
| `search_cache_ttl_hours` | `168` (7 днів) | TTL кеша keyword'ів |
| `search_min_delay` | `45.0` (підняти з 4.0) | базова затримка між мережевими запитами, сек |
| `search_jitter` | `0.5` | частка джиттера (±) поверх `min_delay` |
| `search_backend_cooldown_base_seconds` | `300` | база експон. cooldown бекенда |
| `search_backend_cooldown_cap_seconds` | `21600` (6 год) | стеля cooldown бекенда |
| `search_global_backoff_hours` | `6` | пауза активного пошуку, коли всі бекенди cooled |

Лишаються без змін: `active_discovery`, `search_providers` (`duckduckgo` за замовч.), `search_keywords`,
`search_results_per_keyword`, `search_budget` (per-run бюджет keyword'ів; курсор keyword'ів у
`ActiveDiscovery` лишаємо як є — прокрутка списку робиться наявним budget-механізмом; персистентний
курсор keyword'ів **не** додаємо в цьому треку, щоб не роздувати — достатньо кеша).

Прибираємо константу `DDG_BACKENDS` і поведінку «усі бекенди одразу».

### Docker

Змонтувати малий named-volume під `search_state_path` для сервісу краулера (профіль `crawler`) у
`docker-compose.yml`, щоб cooldown/кеш/курсор переживали перезапуск контейнера. Оновити
`README-docker.md`/`RUN.md` згадкою про стейт-файл.

## Тести (TDD, без реальної мережі)

Fake `ddgs`-factory (повертає задані результати або кидає `RatelimitException`), fake `clock`
(контрольований час), fake `rand` (детермінований jitter), tmp `search_state_path`.

Нові:
- **rotation** — 5 keyword'ів по здорових бекендах → цикл `google→startpage→…→brave→google`.
- **skip cooled** — бекенд у cooldown пропускається в ротації.
- **circuit-breaker** — `RatelimitException` → бекенд cooled на `base*2^(fails-1)` (перевірка експоненти й cap); успіх скидає `fails`.
- **fallthrough** — блок на першому бекенді → той самий keyword обслужений наступним здоровим.
- **cache hit** — 2-й виклик того самого keyword у межах TTL → `ddgs` не викликається, sleep не викликається.
- **cache expiry** — після TTL → перезапит.
- **empty cached** — порожній результат теж кешується (немає повторного мережевого виклику).
- **global backoff** — усі бекенди cooled → `run` активного пошуку обривається, `next_allowed_at` виставлено; наступний `run` до цього часу активний пошук пропускає.
- **pacing** — `sleep` викликається лише на мережевих викликах і в межах `[min, min*(1+jitter)]`.
- **state round-trip** — стейт зберігається й коректно вантажиться з диска (cooldown/cache/cursor); битий файл → чистий старт.
- **wiring** — `build_search_provider` з новим конфігом будує `SearchCache(RotatingDdgProvider(...))`.

Оновити наявні: `test_build_provider`, `test_active_discovery`, `test_active_harvest` (новий підпис
провайдера/конструювання). `test_searxng_provider` — без змін.

Прогін: `cd crawler && ./.venv/Scripts/python.exe -m pytest -q` (має лишитись зеленим; наразі 139).

## Поза скоупом (наступні треки)

- **freshness** (пасивний перекроул → `last_seen_at` → `expired`) — окремий трек.
- **promotion-лінк** (публікація оффера → джерело стає активним) — окремий трек.
- **seed-каталог** (курований git-файл довірених джерел → internal upsert у `sources`) — окремий трек.
- Проксі/Tor — не використовуємо.
- `SearXNG` — лишаємо як є (наразі віддає 0; не чіпаємо).
- `region="ua-..."` для UA-релевантності — можливе мінорне покращення, **не** в цьому треку.

## Ризики / нотатки

- Кеш робить discovery «повільнішим» на нові джерела (до 7 днів лагу на повтор keyword'а) — прийнятно,
  бо нові джерела з'являються повільно, а мета треку — не блокуватись.
- `ddgs` може мовчки віддати `[]` без винятку при soft-throttle. Порожній результат ми **не**
  трактуємо як блок (щоб не заганяти живі бекенди в cooldown марно) — лише реальні винятки.
  Це свідомий компроміс на користь стабільності.
- Дефолти таймінгів (45s/5хв/6год) — консервативні; усі конфіговані, тюняться без коду.
