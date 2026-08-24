# Паралелізація пасивного проходу краулера (Трек #11)

**Дата:** 2026-08-24
**Статус:** затверджено (brainstorm)
**Скоуп:** лише `run_passive`. Активний `harvest`, scheduler, cadence — поза скоупом.

## Проблема

`Runner.run_passive` обходить усі активні (approved) джерела серійно
(`crawler/crawler/runner.py:279` — `for source in sources`), а всередині кожного
джерела deep-walk фетчить сторінки теж серійно
(`crawler/crawler/runner.py:333`). Час пасивного проходу росте **лінійно** з
кількістю джерел — це остання незакрита стеля пропускної здатності з
ранжованого беклогу (#11). Ручки обсягу (budget/TTL) множать роботу, але не
прибирають серійність, тож прохід стає ×N довшим.

Пасив — I/O-bound: час іде на HTTP-фетчі та per-domain політ-затримки
(`domain_rl.wait`), не на CPU. Різні домени незалежні й можуть накладатись;
один домен мусить лишатись серійним заради політу.

## Рішення (огляд)

`ThreadPoolExecutor(max_workers=N)`, **1 таск = 1 джерело**. Різні домени
накладаються; один домен серіалізується per-domain локом усередині
`DomainRateLimiter`. Уся потокобезпечність заштовхана в спільні обʼєкти
(internally-locked) + per-task summary + `LockedSet` для `known` —
**жодної зміни сигнатур** методів, тож серійні шляхи (`run_first_crawl`,
активний harvest, bootstrap/snowball) не зачеплені.

Обґрунтування вибору потоків (а не asyncio/процесів) — задача I/O-bound, GIL
відпускається на HTTP+sleep; fetchers уже на потокобезпечному спільному
`httpx.Client`; asyncio = непропорційний перепис усього I/O-стеку; процеси =
IPC для `domain_registry`/`api`/`corpus` без виграшу на I/O. Патерн
«per-domain партиціювання, 1 хост = 1 воркер за раз» — канонічний політ-дизайн
краулерів.

## Чому нічого не ламається (блиск-радіус)

Ключ: scheduler виконує **рівно один прохід за крок** (`crawler/crawler/scheduler.py`)
— активний і пасивний ніколи не йдуть одночасно. Тому локи в registry/corpus
реально контендяться лише всередині паралельного пасиву; для всіх інших
(серійних) викликів це неконтендований лок ≈ наносекунди, нуль зміни поведінки.

| Спільна точка | Хто ще викликає | Як закрито |
|---|---|---|
| `_crawl_source` | `run_passive` + `run_first_crawl` (серійно) | Сигнатуру не чіпаємо; кожен таск дістає власний локальний `summary`, зливаємо після join |
| `DomainRegistry.record/take_skip/save/record_rejections` | активний harvest (`harvest.py:118`), reject-ingestor | Лок **всередині** методів; адитивно |
| `CorpusRecorder.record` | harvest (`harvest.py:183`), bootstrap, snowball | Лок всередині; усі інші виклики серійні |
| `DomainRateLimiter.wait` | walker, sitemap, robots, language_gate | Per-domain лок адитивний; інтерфейс незмінний |
| `known` (set) | `_process_page` (спільний для обох шляхів) | У `run_passive` обгортка `LockedSet` (`__contains__`/`add`); first_crawl передає звичайний set |

## Компоненти

### 1. `DomainRateLimiter` (модифікація, `crawler/crawler/ratelimit.py:22`)

Додати потокобезпечність **per-domain** (не глобальний лок).

**Correctness crux:** глобальний лок, що тримається під час `sleep`, серіалізує
ВСІ домени → паралелізм помирає. Тому:

- `self._guard = threading.Lock()` — короткий лок, що захищає реєстри
  `_last` і `_locks` (тримається лише навколо dict-доступу, ніколи навколо sleep).
- `self._locks: dict[str, threading.Lock]` — по одному локу на домен.
- `wait(domain, delay)`:
  1. під `_guard` дістати/створити `dl = _locks[domain]`;
  2. під `dl` (тримається під час RMW+sleep): прочитати `_last[domain]`,
     поспати залишок, записати `_last[domain]`.

Один домен серіалізується (політ збережено); різні домени беруть різні `dl` і
накладаються. Публічний інтерфейс (`__init__`, `wait`) незмінний → усі наявні
callers працюють як раніше. `sleep`/`monotonic` лишаються інʼєктовними для тестів.

### 2. `LockedSet` (нове, малий хелпер)

Мінімальна потокобезпечна обгортка над `set`: `__contains__` і `add` під
`threading.Lock`. Уживається лише в `run_passive` для `known`. `_process_page`
поводиться з `known` як із set-like → працює і для обгортки (пасив), і для
звичайного set (first_crawl).

### 3. `DomainRegistry` (модифікація, `crawler/crawler/discovery/domain_registry.py`)

Внутрішній `threading.Lock`, узятий у `record`, `take_skip`, `record_rejections`,
`save`, `prune`. RMW над `_data["domains"]` і вставка нових ключів стають
атомарними. Активний (серійний) шлях бере неконтендований лок → без зміни поведінки.

### 4. `CorpusRecorder` (модифікація, `crawler/crawler/learn/corpus.py`)

Внутрішній `threading.Lock` навколо `record` (append + `_rotate`), щоб паралельні
append'и не перепліталися й `_rotate` не гонився з append'ом.

### 5. `Runner.run_passive` (модифікація, `crawler/crawler/runner.py:271`)

- `sources = api.list_sources()`, `known = LockedSet({...})` — до пулу.
- `with ThreadPoolExecutor(max_workers=self._passive_workers) as ex:` —
  сабмітити по джерелу; кожен таск викликає `_crawl_source(source, cats, known,
  local_summary)` зі **своїм** локальним `summary` (`_empty_summary()`).
- Ізоляція per-source: виняток таску ловиться → `local_summary["errors"] += 1`
  + лог (як зараз, `runner.py:283`), щоб один домен не топив пул.
- Після `as_completed`: злити всі локальні summary в один.
- Далі як зараз (серійно, після join): `expire_stale`, `registry.save()`.

`_passive_workers` — новий інʼєктований параметр `Runner.__init__`, дефолт `4`.
Значення `1` завжди дає byte-identical серійну поведінку (аварійний відкат).

### 6. Executor-інʼєкція для тестів

`run_passive` бере фабрику executor'а (дефолт `ThreadPoolExecutor`); тести
підставляють синхронний inline-executor, щоб логіка проходу тестувалась
детерміновано, без гонок.

## Потік даних

```
run_passive()
  sources = api.list_sources()               # 1 виклик, серійно
  known   = LockedSet({...})                 # до пулу
  ┌── ThreadPoolExecutor(max_workers=N) ──────────────┐
  │  task(source) → local_summary:                    │
  │     take_skip (registry lock) → deep-walk:        │
  │        walk → for url: domain_rl.wait (per-dom)   │
  │                       fetch (shared httpx client) │
  │                       _process_page:              │
  │                          extract, corpus (lock),  │
  │                          submit_offer (httpx),    │
  │                          known.add (LockedSet)    │
  │     registry.record (lock)                        │
  └────────────────────────────────────────────────────┘
  merge local_summaries → summary
  expire_stale (1 виклик) ; registry.save() (1 раз, після join)
```

## Конфіг

Нова ручка `passive_workers` (env → `config` → `wiring` → `Runner`), дефолт `4`.
`passive_workers` — звичайний конфіг, міняється будь-коли; `1` завжди дає точну
наявну серійну поведінку (аварійний відкат). Пул створюється лише в
`run_passive`; активний прохід і scheduler нічого не бачать.

## Обробка помилок

- Per-source ізоляція збережена (виняток у таску → `errors += 1` + лог).
- `expire_stale` і `registry.save()` — після join, best-effort, як зараз.
- `save()` мусить іти ПІСЛЯ всіх `record()` (after join) — гарантовано порядком.

## Тестування (verify-by-execution)

- **Детермінізм:** inline-executor у тестах — прохід тестується без гонок.
- **Rate-limiter потокобезпека:** fake-clock/sleep, два потоки на один домен →
  фактична серіалізація + сумарна затримка ≥ floor; два РІЗНІ домени → БЕЗ
  взаємної затримки (доказ, що лок per-domain, а не глобальний).
- **Злиття summary:** N джерел із різними offers/errors → сума = серійний baseline.
- **Regression:** `passive_workers=1` → byte-identical зі старим кодом.
- **Corpus/registry під конкурентністю:** N потоків пишуть → жодного втраченого/
  побитого рядка, лічильники консистентні.
- **Жива Docker-перевірка:** ребілд контейнера, реальний пасивний прохід,
  звірка summary та що політ не порушено (per-domain інтервали витримані).

## Поза скоупом (YAGNI)

Активний `harvest`, scheduler, cadence пасиву, крос-процесна/розподілена
конкурентність, async-перепис. Кожне — окремий майбутній крок, коли/якщо впреться.
