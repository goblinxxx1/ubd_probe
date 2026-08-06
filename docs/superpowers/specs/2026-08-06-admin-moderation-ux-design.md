# UX черги модерації: превʼю реальної сторінки + confidence-асист + bulk-reject — беклог #10

**Дата:** 2026-08-06
**Гілка:** `feat/admin-moderation-ux` (від `main` 28e8487)
**Тип:** backend (confidence-сервіс + bulk-reject ендпоінт, admin-only) + admin (Vue3). public/crawler/міграції не чіпаються.

## Мотивація

Черга модерації (`ModerationQueueView` → `OffersListView fixed-status="pending_review"`) — гола таблиця:
щоб оцінити офер, модератор мусить клікнути «Редагувати». Немає (1) швидкого превʼю, (2) масового
прибирання шуму, (3) сигналу довіри. Беклог #10 (затверджено 2026-07-29): превʼю + bulk + confidence-**асист**
(людина завжди підтверджує, ніколи auto-publish).

## Рішення (три компоненти; рішення користувача зафіксовані)

### A. Превʼю реальної сторінки-джерела (admin, чисто фронтенд)
Клік «Превʼю ↗» на рядку → `window.open(article_url ∥ site_url, "_blank")` — відкриває **реальну
промо-сторінку** в новому вікні (не рендер витягнутих полів). `article_url` (сторінка, з якої
екстрактор дістав офер) пріоритетна; фолбек `site_url`; якщо жодного http-URL — кнопка disabled.

**Плюс компактні inline-дані в рядку** (з наявних полів `OfferOut`, без backend-змін): маленькі
el-tag'и — знижка (`discount_type`+`discount_value` або к-сть `discounts`), міста (`locations`),
тематики (`offer_categories`). Швидкий огляд без кліку; реальна сторінка — для глибокої перевірки.

### B. Confidence-асист: хост-репутація + completeness (backend-computed)
`OfferOut` **спільний із публічним** (`public.py:31`) — тож confidence НЕ додаємо в `OfferOut`.
Нова admin-схема `OfferAdminOut(OfferOut)` з `confidence: ConfidenceOut | None = None`; admin
`list_offers` віддає `Page[OfferAdminOut]`, публічний фронт лишається на `OfferOut`.

**Сервіс** `app/services/confidence.py`:
- `host_reputation(db, host, memo) -> tuple[int,int]` = (published, rejected) оферів, чий bare
  source-host (site_url/article_url/provider, exact-or-suffix) == host. Реюз патерну #34
  (`_offer_host_candidates`/`_host_blocked` LIKE-prefilter + точна звірка); memo — dict per-page,
  щоб однаковий хост рахувався раз.
- `score_offer(db, offer, memo) -> ConfidenceOut`. Primary host = перший непорожній із
  `bare_host(site_url)`, `bare_host(article_url)`, `bare_host(provider)` (provider — лише якщо має
  крапку). Completeness: `has_discount` (discount_type ≠ None **або** будь-який `discounts`),
  `has_location` (`locations` не порожні), `has_category` (`offer_categories` не порожні).
- **Тір:**
  - **high** — host published ≥1 І rejected == 0 (проявлений добрий) І `has_discount`.
  - **low** — (host rejected ≥1 І published == 0, проявлений шумний) **АБО** `not has_discount`.
  - **medium** — решта (новий хост 0/0, змішаний, тощо).
- **Сигнали** (list[str] слаги для чіпів): `proven_host` / `noisy_host` / `new_host`;
  `no_discount` / `no_location` / `no_category`.
- `enrich_pending(db, offers)` — для кожного офера ставить транзієнтний атрибут `offer.confidence`.

**Ендпоінт**: у `list_offers` — якщо `status == pending_review`, `enrich_pending(db, items)` перед
серіалізацією. Для інших статусів confidence лишається None (порожньо в UI). Обчислення лише на
поверненій сторінці (post-SQL), memo по хостах — обмежено розміром сторінки (≤100).

**Сортування:** клієнтське, в межах завантаженої сторінки (візуальне групування low→medium→high
або навпаки через тумблер). Глобальний крос-сторінковий сорт за confidence — свідомо **deferred**
(потребував би обчислення для всіх pending; черга зазвичай ≤1 сторінка). Документуємо.

### C. Bulk **reject** (backend ендпоінт + admin UI). Bulk publish — НЕ робимо (небезпечно).
- **Backend** `POST /admin/offers/bulk-reject` body `{ids: list[int]}` → для кожного id
  `set_status(rejected, admin.id)` (реюз усієї логіки, вкл. #34 auto-block learning). Відповідь
  `BulkRejectOut{rejected: list[int], failed: list[{id, error}]}`. Неіснуючий id → у `failed`,
  не валить решту. Порожній `ids` → 422. Auth `get_current_admin` (як `reject_offer`).
- **Admin UI**: `ResponsiveTable` — opt-in `selectable` (desktop el-table `type="selection"` +
  `@selection-change`; mobile — чекбокс на картці). У черзі (pending) — кнопка «Відхилити вибрані (N)»
  з `confirmAction` → `offers.bulkReject(ids)` → reload + `moderation.refresh()`. Reject = мʼякий
  кошик #12 (оборотно через «Відновити»), тож масове безпечне.

## Точність / безпека
- Confidence — **лише асист**: сортування + бейджі + підсвітка. Публікація завжди поодинока, людина
  підтверджує. Жодного auto-publish (узгоджено з [[feedback-preserve-working-structure]]).
- `OfferAdminOut` — суперсет `OfferOut` (додає опційне поле) → наявні admin-тести/фронт не ламаються;
  публічний API недоторканий.
- Bulk **лише reject** (оборотний). Confirm перед дією.
- Превʼю — просто `window.open` реального URL (iframe уникаємо: X-Frame-Options/CSP часто блокують).

## Поза скоупом (свідомо)
- Bulk publish/approve (відхилено користувачем).
- Глобальний крос-сторінковий confidence-сорт (deferred; черга мала).
- Скріншот/снапшот сторінки (превʼю = відкриття реального URL).
- Зміна екстрактора/крауле­ра/публічного фронту.

## Тести
**Backend (pytest, mysql-container):**
- `host_reputation`: рахує published/rejected по exact+suffix host; memo не подвоює.
- `score_offer`: high (proven host + знижка), low (noisy host / без знижки), medium (новий хост);
  сигнали правильні; primary host fallback article_url; provider без крапки ігнориться.
- `list_offers` pending: кожен item має `confidence`; інші статуси — None.
- `OfferAdminOut` серіалізує confidence; public `GET /offers` НЕ має поля confidence.
- bulk-reject: 3 pending → усі rejected; неіснуючий id → у failed, решта rejected; порожній→422;
  auth-guard 401 без токена; #34-навчання спрацьовує (хост ≥2/0 → auto_block).

**Admin (Vitest, API замоканий) + `npm run build`:**
- рядок черги: inline-бейджі знижка/міста/тематики; confidence-тег за тіром + чіпи сигналів.
- «Превʼю ↗» відкриває article_url (fallback site_url) новим вікном; disabled без URL.
- вибір рядків + «Відхилити вибрані (N)» → confirm → bulkReject(ids) → reload.
- клієнтський сорт за confidence перегруповує items.
- `ResponsiveTable selectable`: емітить selection-change з вибраними рядками.
- **обовʼязково `npm run build`** (Vitest не компілює scoped-Less — undefined-токен валить лише build).
