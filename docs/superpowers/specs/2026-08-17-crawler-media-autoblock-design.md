# Спек: авто-блок медіа-хостів від краулу (behavioral, без `is_article`)

Дата: 2026-08-17
Скоуп: `crawler/` (детекція + блок), `backend/` (write-ендпойнт блокліста). Одна сесія/трек.

## Проблема

Медіа/новинні хости (`dumka.media` тощо) далі фетчаться щокраулу, палять бюджет і
періодично протікають у чергу модерації як «офери». Наявні гейти:

- Курований `_MEDIA` seed (`crawler/discovery/blocklist.py`) — no-fetch, але ручний.
- Атрибуційний медіа-гейт (`is_article`) — вето **окремого офера**, не хоста; до того ж
  `is_article` фонить в обидва боки: не спрацював на `dumka.media` (числові пермалінки,
  без og:type=article), але спрацьовує й на звичайних бізнес-сайтах із блогом.
- `host_miner` — самонавчальний, але **аудит-гейтований** (у pending-чергу).

Мета: коли краулер сам розпізнав хост як не-бізнес — **закріпити ВЕСЬ хост як no-fetch**
автоматично, дзеркалячи наявний гео-блок (`harvest.py` RU/BY → `GeoBlockStore.add`).

## Рішення (узгоджені розвилки)

1. **Агресивність:** консервативно + вето бізнесу.
2. **Сховище:** backend `blocked_hosts` (видно в адмінці, відкатне через наявний `reject`).
3. **Тригер:** поведінковий — «0 структурної provider-evidence за K краулів», **БЕЗ `is_article`**.

### Правило детекції

Per host, per crawl (один виклик `DomainRegistry.record` = один обхід хоста в `harvest`):

- `structural_provider` = хоч одна обійдена сторінка хоста має schema.org **`Offer`**
  або **`LocalBusiness`** (`has_offer_schema` / `has_business_schema`). Це — вето бізнесу.
  **НЕ** рахуємо текстову first-party евристику атрибуції (маркер «ми/пропонуємо») —
  саме вона хибно робить новину провайдером; це вектор витоку `dumka.media`.
- `produced_offers` = хост цього краулу подав ≥1 офер.

Логіка streak:

- `produced_offers AND NOT structural_provider` → `media_streak += 1`.
- будь-який краул зі `structural_provider` → `media_streak = 0` (і назавжди знімає кандидатуру: `provider_ever = True`).
- краул із 0 оферів → streak не чіпаємо (це порожній прогін, ним керує наявний `empty_skip`).
- `media_streak >= K` (config `media_autoblock_crawls`, дефолт **2** — блок на 2-му офер-краулі) і `not provider_ever`
  → **авто-блок хоста**.

**Чому це ловить `dumka.media`:** новинний сайт виробляє «офери» (леджені), але не має
`Offer`/`LocalBusiness` schema.org → structural_provider завжди False → streak росте → блок.

**Прийнятий залишковий ризик:** малий реальний бізнес **без** schema.org, що само-декларує
знижку лише текстом, може бути заблокований після K прогонів. Пом'якшення: (а) K=2;
(б) видимість у адмінці + миттєвий `reject`(розблок); (в) курований seed лишається
для миттєвих відомих кейсів. `dumka.media` уже додано в seed окремо — цей трек ловить
**майбутні невідомі** медіа.

## Компоненти (ізольовані)

### crawler

- **`DomainRegistry`** (`crawler/discovery/domain_registry.py`) — розширити:
  - `record(host, offers, errors, structural_provider=False)` — новий kwarg;
    веде `media_streak`, `provider_ever` у per-host записі (JSON-стор, як зараз).
  - `media_block_due(host, k) -> bool` — `entry and not provider_ever and
    media_streak >= k and not media_blocked`. Ставить `media_blocked=True` (щоб не
    ре-постити). Чиста функція над стором, без I/O назовні.
- **`MediaAutoBlocker`** (новий, напр. `crawler/discovery/media_autoblock.py`) — тонка
  обгортка: `block(host, sample_url)` → `api.auto_block_host(...)` + миттєве
  `blocklist.add_learned(host)` (щоб решта кандидатів цього ж прогону вже пропускалась).
  Гейтований `config.media_autoblock_enabled` (kill-switch, дефолт True).
- **`blocklist.add_learned(host)`** (новий) — інкрементально додає хост у runtime-`_LEARNED`
  (щоб блок діяв у межах поточного прогону; на старті наступного все одно тече з
  `api.list_blocked_hosts()`).
- **`api_client.auto_block_host(host, sample_url=None)`** — `POST /api/internal/blocked-hosts`.
- **`harvest`** — прокинути `structural_provider`:
  - `_process_page` повертає bool «чи бачив structural_provider на цій сторінці»
    (`any(has_offer_schema or has_business_schema)` серед `items`).
  - `_harvest_one` OR-ить прапорець по всіх сторінках хоста й повертає його вгору.
  - `harvest()` після `self._registry.record(host, dOffers, dErrors, structural_provider=<flag>)`
    робить `if self._registry.media_block_due(host, k): self._media_blocker.block(host, url)`.

### backend

- **`POST /api/internal/blocked-hosts`** (`routers/internal.py`) — body `{host, sample_url?}`
  → `blocked_host_crud.auto_block(db, host)` (уже існує: approved, `reviewed_by=NULL`,
  ідемпотентний). Якщо `sample_url` — покласти у `sample_urls` (доказ для адміна).
  Новий вузький schema `AutoBlockCreate {host: str, sample_url: str | None}`.
  (Наявний `POST /host-candidates` не годиться — він створює *pending*, а нам треба approved.)

## Потік даних

```
harvest(host) ──walk pages──> _process_page ×N
   │                              └─ structural_provider? (Offer/LocalBusiness schema)
   ├─ record(host, offers, errors, structural_provider) ─> DomainRegistry (media_streak)
   └─ media_block_due(host, K)? ─yes─> MediaAutoBlocker.block(host)
                                         ├─ api.auto_block_host ─> backend blocked_hosts (approved)
                                         └─ blocklist.add_learned(host)  (миттєво в цьому прогоні)
next run: wiring reload_learned(api.list_blocked_hosts()) ─> is_blocked_host drops host у harvest/walk/feeds
admin: HostCandidatesView показує approved+reviewed_by=NULL; reject = розблок
```

## Обробка помилок

- `MediaAutoBlocker.block` ковтає мережеві помилки API (лог + продовжити) — блок не критичний
  для прогону; наступний краул повторить (streak лишається за порогом).
- `media_autoblock_enabled=False` → детекція взагалі не запускається (byte-eq попередній
  поведінці: `record` зі старою сигнатурою через дефолт `structural_provider=False`
  нічого не блокує без виклику `media_block_due`).
- `auto_block` ідемпотентний → повторний POST того самого хоста безпечний.

## Тести

- `DomainRegistry`: streak росте лише при `produced_offers and not structural_provider`;
  скидається на `structural_provider`; порожній краул не чіпає; `media_block_due` True на
  K-му; `media_blocked` не дає повторного True; `provider_ever` довічно вето.
- `MediaAutoBlocker`: викликає api + add_learned; kill-switch off = no-op; ковтає API-помилку.
- `blocklist.add_learned`: хост стає blocked одразу; порожній/None — no-op.
- backend: `POST /api/internal/blocked-hosts` → рядок approved reviewed_by=NULL; ідемпотентність;
  `sample_url` осідає в sample_urls; невалідний host → 422/пропуск.
- harvest-інтеграція: медіа-хост (офери, 0 схеми) за K прогонів → блокується й далі не фетчиться;
  бізнес зі schema.org — ніколи.

## Поза скоупом

- Ретро-чистка вже наявних медіа-оферів у черзі (адмін прибирає вручну / bulk-reject).
- Нові колонки БД (`auto_block` уже є; `sample_urls` уже є).
- Зміна `host_miner`/`is_article` деінде (лишаються як є для аудит-черги; цей трек їх не чіпає).
- Розрізнення в адмінці «media-auto» vs «reject-learned» (обидва reviewed_by=NULL) — за потреби окремо.
```
