# Crawler (трек 4) — нотатки брейнсторму (у процесі, на паузі)

> Це **не** фінальний spec, а проміжний стан брейнсторму. Продовжити з розділу
> «Відкрите питання», далі дійти до повного spec → плану → реалізації.
> Гілка `feat/crawler` уже створена від `main`.

## Що будуємо

Сервіс за кроном: обходить джерела (`website` / `facebook` / `telegram` / `instagram`),
знаходить оффери, пропонує нові джерела — усе через **internal API** бекенда з `X-API-Key`.

## Точка інтеграції з бекендом

`/api/internal`, auth: header `X-API-Key` == `settings.crawler_api_key`:

- `GET /api/internal/sources?is_active=true` → джерела для обходу
  (`SourceOut`: `id, name, type, url_or_handle, is_active, last_crawled_at, created_by, created_at`).
- `POST /api/internal/offers` — `OfferCreate` + опційний `source_id`; бекенд форсить
  `created_by=crawler`, `status=pending_review`.
- `POST /api/internal/suggested-sources` — `name, type, url_or_handle,
  discovered_from_source_id, discovery_note`.
- `SourceType` ∈ {website, facebook, telegram, instagram}.
- **Немає** endpoint для writeback `last_crawled_at`; **немає** dedup на offers.
  → Краулер веде **власний локальний стан** (dedup вже поданого, last-seen на джерело).

## Ухвалені рішення

1. **Реальний краулінг усіх платформ.** Pluggable-провайдер доступу на кожну платформу
   за єдиним інтерфейсом + архітектурний гачок під платний сервіс (Apify/HikerAPI) на майбутнє.
2. **Доступ IG/FB:** логін бот-акаунтом + open-source бібліотеки (`instaloader` для IG,
   аналог для FB), опційно проксі. Окремий бот-акаунт (не особистий), консервативний rate-limit.
   Бан бот-акаунта — очікувана норма: адаптер це переживає (повертає «нічого нового»), не падає.
3. **Telegram:** `https://t.me/s/<handle>` для публічних каналів (без креденшелів)
   + опційно MTProto (Telethon, безкоштовний `api_id`) для груп.
4. **Zero-cost runtime (жорсткий принцип).** Коли підписка на Claude закінчиться —
   усе працює без залучення коштів. Дозволені лише безкоштовні Python-бібліотеки;
   заборонені хмарні платні LLM / скрейпінг-сервіси в runtime.
5. **Extraction:** pluggable extractor.
   - Дефолт `heuristic` — offline, детерміновано: словники ключових слів (укр:
     знижка, акція, −%, безкоштовно, для військових/ветеранів/УБД, промокод…),
     regex `discount_type`/`discount_value` (−20%/«знижка 20%»→percent; «500 грн»→fixed;
     «безкоштовно»→free), regex дат (`valid_from`/`valid_until`), `provider`=назва джерела,
     мапінг ключових слів→наявні категорії.
   - Опційно `local_llm` — **лише локальна** LLM (Ollama, напр. Qwen2.5-7B / Llama-3.1-8B),
     НІКОЛИ хмарна платна. Гібрид: евристики-префільтр відсіюють сміття → локальна LLM
     докручує структуру лише на кандидатах (бо локальна LLM повільна).
6. **Discovery нових джерел** (напрям, не фіналізовано): під час обходу витягувати з контенту
   згадки/посилання на інші акаунти/канали (@handle, `t.me/`, `instagram.com/`,
   `facebook.com/`, зовнішні посилання) → фільтр проти наявних `sources` та локального стану
   → `POST /suggested-sources` з `discovery_note` і `discovered_from_source_id`.

## Відкрите питання (продовжити тут)

Чи закладаємо **обидва** extractor-провайдери вже зараз (`heuristic` дефолт + опційний
`local_llm`/Ollama), чи поки лише `heuristic` + гачок в інтерфейсі під локальну LLM пізніше?

## Ще не обговорено (наступні кроки брейнсторму)

- Фіналізувати обсяг discovery.
- Локальний стан краулера — SQLite? Що зберігаємо (dedup content-hash, last-seen на джерело,
  стан/кулдаун бот-акаунтів, історія suggested-sources).
- Механізм cron/scheduling — Windows Task Scheduler / APScheduler / CLI-entrypoint `python -m crawler run`.
- Структура проєкту — тека `crawler/`, свій venv (аналогічно `backend/`).
- Тестування — мок HTTP/`instaloader`, фікстури HTML/постів, offline.
- Конфіг (`.env`, gitignored): internal API URL, `X-API-Key`, креденшели бот-акаунтів,
  проксі, вибір extractor, rate-limit.
- Rate-limit / ввічливість (robots, затримки, User-Agent).

Далі: завершити брейнсторм → повний spec у цій теці → план у `docs/superpowers/plans/`
→ реалізація (subagent-driven).
