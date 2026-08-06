# Reject навчає рейтинг доменів (soft down-rank) — беклог #9

**Дата:** 2026-08-06
**Гілка:** `feat/crawler-reject-feedback` (від `main` 2472061)
**Тип:** backend (новий read-ендпоінт) + crawler (новий канал навчання). admin/public/міграції не чіпаються.

## Мотивація

`ActiveHarvester` пише `+offer` у crawler-side `DomainRegistry` за **створений** офер
(`harvest.py:76`, `record(host, offers, errors)`), незалежно від рішення модератора. Домен, чиї
офери **постійно відхиляють**, набирає score → `DomainFeed` ре-фідить його + `site:`-запити його
цілять → марна витрата бюджету + повторний шум у черзі. Негативного зворотного зв'язку від
відхилень у рейтинг **немає**.

Беклог #9 (затверджений 2026-07-29): «`harvest.py` пише +offer навіть якщо офер потім
відхилять; reject негативного сигналу НЕ дає. Додати: reject→down-rank».

## Що вже є (щоб не дублювати)

- **#34** (`set_status`/`_maybe_autoblock_hosts`) — hard-block блокліста при **≥2 rejected і 0
  published**. Бінарно, гейтоване «0 published» (дуал-статусні бізнес-хости захищені), краулер
  повністю перестає фетчити.
- **#36** — дедуп discovered-оферів по `article_url_canonical` проти rejected-рядка (ре-крол
  уже-rejected сторінки = no-op).
- **Канал навчання** — краулер полить `GET /api/internal/approved-offers?since=` (snowball,
  курсор у JSON). Цей трек дзеркалить його для відхилень.

## Геп, який закриває #9

Домен зі **змішаним** результатом (кілька rejected, але ≥1 published — тож #34 його **не**
блокує) тримає високий score → далі агресивно ре-фідиться `domain_feed`/`site:`. Soft down-rank —
**градуйований, оборотний** сигнал, що доповнює (не дублює) hard-block #34: доменів зі стійко
поганою якістю поступово опускає нижче `promote_min` → випадають з `top()` → менше ре-фіду й шуму.
Hard-block лишається для чистих 0-published шумовиків.

**Обмеження (свідомо прийняте):** down-rank діє лише на канали, що **читають** рейтинг
(`domain_feed`, `site:`). Пошуково-транзитний домен (не в рейтингу) пошук знайде знову незалежно від
score — тому reject на **невідомий рейтингу хост = Skip** (нічого ре-фідити; повторний шум ловлять
#36 і #34). Заведення «чорного запису» дало б мало користі й роздувало б файл рейтингу.

## Дизайн (дзеркалить snowball-канал)

### Компонент 1 — Backend read-ендпоінт `GET /api/internal/rejected-offers?since=`
- CRUD `offer.py::list_rejected_since(db, since)` — дзеркало `list_published_since`:
  `status == rejected` **І** `created_by == crawler`, `updated_at > since` (якщо задано),
  `order_by(updated_at.asc())`.
- Роутер `internal.py`: `RejectedOfferOut(host: str, rejected_at: datetime | None)`,
  `host = _host(o.site_url or o.article_url)` (той самий `_host`, що в approved-offers).
- Схема повертає **окремий рядок на офер** (не агреговано) — агрегацію по хостах робить краулер
  (простіший бекенд; курсор коректний). Порожній host (нема site/article) відсіюється на боці
  краулера.

### Компонент 2 — `DomainRegistry.record_rejections(host, n)` (`crawler/discovery/domain_registry.py`)
- Новий параметр конструктора `reject_weight=1.0`.
- Метод: `host = _host(host)`; якщо порожній **або відсутній у `self._data["domains"]`** → return
  (Skip — не заводимо запис). Інакше:
  `e["score"] = max(0.0, e["score"] - n * self._reject_w)`; `e["rejects"] = e.get("rejects", 0) + n`.
  **НЕ** чіпає `offers`/`errors`/`passes`/`empty_passes`/`last_seen`/`last_offer` (down-rank —
  окремий сигнал, не «прохід»; не оновлює last_seen, щоб не збивати cooldown/prune-охолодження).
- `record()` (наявний) додає `"rejects": 0` у дефолтний запис нового домену (для стабільності
  форми; back-compat читання через `.get("rejects", 0)`).

### Компонент 3 — Крос-краулер полер `RejectionIngestor` (`crawler/learn/reject_feedback.py`)
Копія структури `SnowballIngestor` (курсор у JSON):
- `__init__(api, registry, state_path)`; `_since`/`_save_since` (той самий JSON-патерн).
- `ingest() -> int`: `rows = api.list_rejected_offers(self._since()) or []`; агрегувати
  `counts: dict[host,int]` (пропускаючи порожній host); для кожного `registry.record_rejections(h, n)`;
  запам'ятати `newest = max(rejected_at)`; `_save_since(newest)`; повернути к-сть застосованих rows.
  Курсор рухається навіть коли всі хости — Skip (щоб не перечитувати ті самі rejected щопрохід).

### Компонент 4 — API-клієнт (`crawler/api_client.py`)
- `list_rejected_offers(since=None) -> list[dict]` — GET `/api/internal/rejected-offers`
  (дзеркало наявного `list_approved_offers`).

### Компонент 5 — Wiring/config
- `config.py`: `rejection_feedback_enabled: bool = True`, `domain_reject_weight: float = 1.0`,
  `reject_feedback_state_path` (дефолт поряд із domain_registry, напр. `/data/reject_since.json`).
  Прокинути в `CrawlerConfig` + `from_settings`.
- `wiring.py`: під гейтом `domain_rating_enabled AND rejection_feedback_enabled` збудувати
  `RejectionIngestor` (реюз того самого `DomainRegistry`, що й `DomainFeed`) і передати `reject_weight`
  у `DomainRegistry.load(...)`. `crawler/.env.example` + RUN.md.
- **Виклик `ingest()`**: у `run_active()` перед побудовою feeds (щоб down-rank застосувався до
  score **до** того, як `domain_feed.candidates()`/`registry.top()` читають рейтинг цього ж проходу).
  Best-effort try/except (навчання не валить прохід). Персист рейтингу — наявний `finally` save.

## Магнітуди / семантика
- `reject_weight = 1.0` = скасовує `offer_weight` (+1.0) одного офера. Домен із рівним балансом
  approve/reject лишається біля нейтралі; стійкий шумовик тоне під `promote_min=0.5` і випадає з
  `top()`; далі prune приберає, коли охолоне (score<evict_min І cold≥ttl).
- Курсор `since` = `updated_at`. Дубль-рахунок майже неможливий (strictly-greater), а якщо офер
  ре-rejected — повторний малий down-rank прийнятний.

## OFF-семантика
- `rejection_feedback_enabled=False` (або `domain_rating_enabled=False`) → ingestor не будується,
  `run_active` поводиться байт-ідентично pre-track. Backend-ендпоінт лишається (read-only, нікого не
  ламає; не викликається без ingestor).

## Поза скоупом (свідомо)
- Пошуково-транзитні домени (не в рейтингу) — Skip; їх ловлять #34/#36.
- Агрегація/дедуп на боці бекенду — не потрібна (краулер агрегує).
- Зміна `search_pass` (він рейтинг не читає) — не чіпаємо.
- Нові hard-block пороги — #34 лишається як є.

## Тести (TDD)
**Backend (pytest, mysql-container):**
- `list_rejected_since`: повертає лише crawler+rejected; поважає `since`; сортує asc.
- ендпоінт `/rejected-offers`: host з site_url, фолбек article_url; порожній since = усі.
- не повертає published/pending/admin-rejected.

**Crawler (pytest):**
- `record_rejections`: наявний хост score↓ на n*weight, clamp ≥0, `rejects` росте, offers/errors/passes/last_seen без змін.
- `record_rejections`: відсутній хост → no-op (Skip), домен не з'являється.
- `record_rejections`: порожній host → no-op.
- `RejectionIngestor.ingest`: агрегує по хостах, викликає record_rejections, зберігає newest курсор, курсор рухається навіть при всіх-Skip.
- `RejectionIngestor`: back-compat читання record без `rejects`.
- api_client `list_rejected_offers`: GET правильний шлях+параметр (мок).
- wiring: gated build (обидва прапори); OFF → ingestor None; ON → присутній, реюз registry.
- runner: `ingest()` викликається до feeds у run_active; помилка ingest не валить прохід (best-effort).
