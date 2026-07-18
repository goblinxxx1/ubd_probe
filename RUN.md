# UBD — як запускати

Довідник запуску платформи знижок для УБД. Сервіси: **db** (MySQL) → **backend**
(FastAPI, `/api`, :8000) → **public** (Vue SPA) + **admin** (Vue SPA) + **crawler**
(Python, ходить джерелами й пошуком, шле знахідки в backend).

Домовленість проєкту: **основний спосіб запуску — Docker**; хостовий (окремі процеси)
— для розробки/ітерації окремого сервіса.

---

## Передумови

**Docker-варіант:** Docker Desktop. Один раз:

```bash
cp .env.example .env      # секрети/порти за бажанням
```

**Хостовий варіант (dev):**
- Python 3 + venv у `backend/` та `crawler/` (`python -m venv .venv`, `pip install -e ".[dev]"`).
- Node.js у `admin/` та `public/` (`npm install`).
- MySQL, доступний за `backend/.env` → `DATABASE_URL` (зазвичай `mysql-container` у Docker:
  `docker start mysql-container`). Скопіюй `backend/.env.example`→`backend/.env` і
  `crawler/.env.example`→`crawler/.env`.

Логін адмінки за замовчуванням: **`admin@example.com` / `admin12345`** (сідиться автоматично).

---

## Блок 1. Запуск сервісів — окремо і все разом

### Варіант A — Docker (рекомендовано)

**Усе разом** (db + backend + public + admin):

```bash
docker compose up -d --build
```

- Public:  http://localhost:8080
- Admin:   http://localhost:8082  (`admin@example.com` / `admin12345`)
- API:     http://localhost:8000/api/health

Backend сам мігрує (`alembic upgrade head`) і сідить дані на старті. MySQL — лише
внутрішній (порт 3306 НЕ публікується, щоб не конфліктувати з локальним MySQL).
Порти перевизначаються в `.env`: `PUBLIC_PORT` / `ADMIN_PORT` / `BACKEND_PORT`.

**Окремі сервіси** (compose піднімає й залежності — напр. admin потягне backend+db):

```bash
docker compose up -d db backend      # тільки БД + API
docker compose up -d admin           # адмінка (+ backend, db як залежності)
docker compose up -d public          # публічний сайт
```

Краулер — за профілем `crawler` (див. Блоки 2–3), сам по собі окремим сервісом
не тримається постійно (одноразовий прохід або цикл).

**Усе разом + краулер** (додає `fixture` + `searxng` + `crawler` за профілем):

```bash
docker compose --profile crawler up -d --build
```

За замовчуванням краулер зробить **один прохід і завершиться** (`CRAWL_INTERVAL_SECONDS=0`);
для постійного циклу постав `CRAWL_INTERVAL_SECONDS>0` у `.env`. Активний пошук лишається
вимкненим, доки не задаси `ACTIVE_DISCOVERY=true` (див. Блоки 2–3). Джерела для обходу
мають існувати (демо-фікстура або схвалені джерела) — інакше проходити нема що.

**Усе разом + активний пошук по ключових словах (обери движок):**

Спершу підніми стек, потім зроби прохід активного пошуку. Движок обираєш через
`-e SEARCH_PROVIDERS`; ключові слова беруться з `crawler/.env` (`SEARCH_KEYWORDS`),
який compose підвантажує в контейнер (`env_file`) — тож `crawler/.env` має існувати
(скопіюй з `.env.example`, там уже заповнений список фраз).

```bash
docker compose up -d --build                      # db + backend + public + admin

# один движок — DuckDuckGo:
docker compose --profile crawler run --rm \
  -e ACTIVE_DISCOVERY=true -e SEARCH_PROVIDERS=duckduckgo crawler

# один движок — SearXNG:
docker compose --profile crawler run --rm \
  -e ACTIVE_DISCOVERY=true -e SEARCH_PROVIDERS=searxng crawler

# усі движки разом:
docker compose --profile crawler run --rm \
  -e ACTIVE_DISCOVERY=true -e SEARCH_PROVIDERS=duckduckgo,searxng crawler
```

Знахідки падають у **admin → Запропоновані джерела** (див. Блок 3). Для запуску на
розкладі задай `ACTIVE_DISCOVERY=true` + потрібний `SEARCH_PROVIDERS` прямо в `crawler/.env`
і підніми краулер циклом: `docker compose --profile crawler up -d --build`
(з `CRAWL_INTERVAL_SECONDS>0`).

**Зупинка / скидання:**

```bash
docker compose down        # зупинити, дані лишити
docker compose down -v     # + витерти том БД
```

### Варіант B — Хостовий dev (окремо, для ітерації)

Потрібен запущений MySQL (`docker start mysql-container`) і заповнені `.env`.
Кожен сервіс — свій термінал.

**Backend** (з `backend/`, venv):

```bash
.venv/Scripts/python.exe -m alembic upgrade head   # міграції (перший раз / після змін схеми)
.venv/Scripts/python.exe -m app.seed               # базові дані + адмін
.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000 --reload
```

**Admin** (з `admin/`):

```bash
npm run dev        # http://localhost:5173, проксі /api → http://localhost:8000
```

**Public** (з `public/`):

```bash
npm run dev        # http://localhost:5174, проксі /api → http://localhost:8000
```

**Crawler** (з `crawler/`, venv) — одноразовий прохід:

```bash
.venv/Scripts/python.exe -m crawler run
```

> **Важливо:** усі команди краулера — саме з теки `crawler/`; конфіг читає `.env`
> відносно робочої теки, інакше мовчки візьме дефолти-заглушки.

**Все разом (хост):** підніми MySQL, тоді 3 постійні термінали (backend, admin, public)
+ краулер за потреби. Для «все разом» простіше Docker (Варіант A).

---

## Блок 2. Краулер з одним / кількома пошуковими движками

Активний пошук нових джерел вмикається окремо: **`ACTIVE_DISCOVERY=true`**. Движки
задає **`SEARCH_PROVIDERS`** (у `crawler/.env`, або `-e` в Docker). Доступні:
`duckduckgo`, `searxng`, або обидва через кому. Знахідки йдуть у чергу
`suggested_sources` (не одразу в оффери).

**Один движок — DuckDuckGo** (дефолт, нічого зовнішнього не треба):

```bash
# crawler/.env:  ACTIVE_DISCOVERY=true   SEARCH_PROVIDERS=duckduckgo
.venv/Scripts/python.exe -m crawler run                    # хост
# або Docker:
docker compose --profile crawler run --rm \
  -e ACTIVE_DISCOVERY=true -e SEARCH_PROVIDERS=duckduckgo crawler
```

**Один движок — SearXNG** (self-hosted метапошук; сервіс `searxng` під профілем `crawler`):

```bash
docker compose --profile crawler run --rm \
  -e ACTIVE_DISCOVERY=true -e SEARCH_PROVIDERS=searxng crawler
# сервіс searxng підніметься автоматично як залежність (healthcheck).
```

**Кілька движків — DuckDuckGo + SearXNG** (стійкіше, агрегує більше):

```bash
docker compose --profile crawler run --rm \
  -e ACTIVE_DISCOVERY=true -e SEARCH_PROVIDERS=duckduckgo,searxng crawler
```

Налаштування пошуку (у `crawler/.env`): `SEARCH_KEYWORDS` (фрази через кому),
`SEARCH_RESULTS_PER_KEYWORD` (7), `SEARCH_MIN_DELAY` (4 c між запитами),
`SEARCH_BUDGET` (0 = всі ключові слова), `SEARXNG_URL` (для Docker — `http://searxng:8080`).
У Docker `crawler/.env` підвантажується в контейнер краулера через `env_file` (compose),
тож для пошуку по ключових словах він **має існувати**; окремі значення (`ACTIVE_DISCOVERY`,
`SEARCH_PROVIDERS`) перекриваються прапорцем `-e`.

> **SearXNG з хостового краулера:** сервіс `searxng` слухає всередині Docker-мережі
> (`searxng:8080`), з хоста не опублікований. Тому для `searxng` найпростіше гнати
> краулер теж у Docker (як вище), або вкажи `SEARXNG_URL` на доступний тобі інстанс.

---

## Блок 3. Краулер ходить → шукає → насипає в адмінку

Краулер нічого не пише в БД напряму — усе через внутрішній API backend (`X-API-Key`).
Куди потрапляють результати в адмінці:

- **Знайдені пошуком джерела** → черга **«Запропоновані джерела»** (`suggested_sources`).
  Адмін схвалює → створюється `Source`, який краулер обходитиме далі.
- **Витягнуті оффери** (з обходу джерел) → черга **«Черга модерації»** зі статусом
  `pending_review`. Адмін публікує → оффер зʼявляється на публічному сайті.

### Варіант 1 — детермінований офлайн-демо (без інтернету, фікстура)

```bash
docker compose up -d --build                                                   # db+backend+admin+public
docker compose --profile crawler run --rm --entrypoint python backend -m app.demo_seed
#   ^ реєструє офлайн-фікстуру як джерело (ідемпотентно)
docker compose --profile crawler run --rm crawler                              # один прохід обходу
```

Результат: у **admin → Черга модерації** зʼявляється `pending_review` оффер.
Схвалюєш → він на public (http://localhost:8080).

### Варіант 2 — реальний потік з активним пошуком

```bash
docker compose up -d --build                                                   # стек
docker compose --profile crawler run --rm -e ACTIVE_DISCOVERY=true crawler     # прохід: пошук + обхід
```

Що відбувається за прохід:
1. **Пошук** (якщо `ACTIVE_DISCOVERY=true`): по `SEARCH_KEYWORDS` через `SEARCH_PROVIDERS`
   → нові кандидати в **admin → Запропоновані джерела**.
2. **Схвалення** (вручну в адмінці): підтверджуєш релевантні → стають активними `Source`.
3. **Обхід** активних джерел (website/telegram/instagram/facebook) → витяг оферів
   → **admin → Черга модерації** (`pending_review`).
4. **Публікація** (вручну): публікуєш оффер → він на публічному сайті.

> Пошук і схвалення джерел — це один прохід (пошук) + твоє рішення + наступний
> прохід (обхід уже схвалених джерел). Тобто зазвичай ганяєш краулер двічі:
> перший раз — знайти джерела, після схвалення — зібрати з них оффери.

### На розкладі (щоб ходив сам)

```bash
# Docker: цикл кожні N секунд
#   .env:  CRAWL_INTERVAL_SECONDS=3600
docker compose --profile crawler up -d crawler       # крутиться щогодини

# Windows-хост: планувальник задач
cd crawler && .\register-task.ps1 -IntervalMinutes 60
```

---

## Тести (довідково, не для прод-запуску)

```bash
cd backend  && .venv/Scripts/python.exe -m pytest -q     # потрібен MySQL (ubd_test)
cd crawler  && .venv/Scripts/python.exe -m pytest -q
cd admin    && npm test          # Vitest, backend не потрібен (API замоканий)
cd public   && npm test
```

Пов'язані доки: **`README-docker.md`** (детальніше про Docker-стек, firewall-адреса
краулера, скидання), субпроєктні `*/README.md`, спеки/плани в `docs/superpowers/`.
