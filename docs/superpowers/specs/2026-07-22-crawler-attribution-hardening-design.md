# Crawler attribution hardening — design spec

**Дата:** 2026-07-22
**Трек:** посилення атрибуції — self-growing host-blocklist (медіа/агрегатори поза статичним списком)
**Гілка:** `feat/attribution-hardening` (від `main`)
**Пам'ять:** [[ubd-crawler-discovery-redesign]], [[ubd-crawler-precision]],
[[ubd-crawler-marketing-lexicon-autofill]], [[ubd-crawler-domain-rating]],
[[ubd-crawler-discovery-scaling-brainstorm]], [[ubd-design-for-whole-picture]]

## 1. Контекст і мета

Атрибуція (`crawler/discovery/attribution.py` + `blocklist.py`) вирішує «хто провайдер офера».
Дірa (RESUME open item): новинні/держ/агрегатор-сайти **поза статичним `_BLOCKED`-набором**
просочуються як фейкові провайдери → «шумні багатокатегорійні офери» в модерації. Статичний
список ростили **ручними додаваннями** (ukr.net, dnipro.media, veteranam.info…) — саме те
втручання, що домовились мінімізувати ([[ubd-crawler-discovery-scaling-brainstorm]]: «самонаповнення
БЕЗ людини в потоці; аудит ~N/тиждень, не per-item»).

**Мета:** (а) детермінований живий гейт ловить медіа/агрегатори **структурно**, поза списком;
(б) реальні офери зберігаються (salvage через outbound-лінк); (в) список медіа/агрегатор-хостів
**самонаповнюється** офлайн-майнером + людським audit-approve, без ручної курації.

**Чесне походження рішень** (щоб не видавати нове за зафіксоване, [[ubd-design-for-whole-picture]]):
зафіксований принцип — self-growing НЕГАТИВ (для **термів**) + детерміновані якорі + офлайн-навчання
+ audit-гейт + мінімум людини. **Нове в цьому треку** (екстраполяція патерну, узгоджена з
користувачем): застосування self-growing до **host-blocklist** (не термів); `is_article` як негатив-
якір; per-host агрегація (не term-log-odds); aggregator outbound-spread сигнал; **Vue-audit-поверхня**
(не CLI — бо аудитор може бути нетехнічним, без доступу до коду).

## 2. Тверді інваріанти

- **Живий модераційний гейт цілий; без авто-публікації.** Майнер-вихід untrusted → людський
  approve → лише тоді в живий гейт.
- **Живий гейт детермінований; навчання офлайн** (агрегація/майнінг — окремий процес).
- **Best-effort:** фетч learned-списку / майнер НІКОЛИ не валять прохід (фейл → лише SEED).
- **Попередня автоматика ЗБЕРІГАЄТЬСЯ ПОВНІСТЮ** (§6): лексикон-автозаповнення (промо-словник,
  term-miner, CLI-аудит термів, snowball), auto-category, domain-rating — не ламаються й не
  мігруються. Host-пайплайн додається ПАРАЛЕЛЬНО.
- **Byte-безпечний дефолт:** порожній/нефетчнутий LEARNED ⇒ `is_blocked_host` = лише SEED =
  сьогоднішня поведінка.
- **Не воювати з domain-rating:** host-майнер вето-виключає активні sources і domain-rating-
  productive хости з кандидатів.

## 3. Архітектура — 3 шари

### Шар A — живий детермінований гейт (крауler, ON; негайна точність + мітки)

`RawItem.is_article: bool` — `WebsiteFetcher` детектить `schema.org` `@type`
NewsArticle/Article/BlogPosting/NewsMediaOrganization (дзеркало наявного `_has_offer_schema`;
`@type`-anchored regex, як у [[ubd-crawler-marketing-lexicon-autofill]]).

`attribute()` зміни (у `attribution.py`):
1. **article-негатив:** якщо `item.is_article` І сторінка не має Organization/LocalBusiness-
   сигналу (щоб не нукнути легіт single-business лендінг із BlogPosting-schema — див. recall-ризик
   §7) → сторінка НЕ first-party провайдер.
2. **aggregator-сигнал:** `ctx.outbound_host_count >= aggregator_min_outbound` → каталог → НЕ
   first-party (кожен офер лише через власний outbound-лінк).
3. **salvage-реордер:** для будь-якої медіа/агрегатор/blocked-сторінки спершу пробувати
   outbound-third-party (case 2), і `None` лише якщо чистого бізнес-лінка нема. Зараз
   `is_blocked_host(host) → None` ДО салважу — це міняється.

`is_blocked_host` = SEED (`_BLOCKED`) + LEARNED. LEARNED — module-level set, наповнюваний
`blocklist.reload_learned(hosts)` (дзеркало `promo_lexicon.reload_learned`). `build_runner`
фетчить approved-blocked-hosts раз/прохід і наповнює LEARNED (best-effort).

### Шар B — офлайн-майнер (крауler; переюз корпусу)

`CorpusRecorder` (наявний, gated `autofill_enabled`) — розширюю рядок адитивно: `is_article`,
`outbound_hosts` (к-ть різних зовнішніх бізнес-хостів зі `item.links`). Term-miner/`read_corpus`
ігнорують зайві ключі → term-пайплайн незмінний.

`learn/host_miner.py` — агрегує корпус **per host**: `support` (к-ть різних сторінок, мін N);
`media_ratio` (частка article-сторінок); `aggregator_ratio` (частка high-outbound); контраст
проти provider-evidence (single-business/pos_anchor Offer-schema/low-outbound). Кандидат = висока
media/aggregator-поведінка + низька provider-evidence + `support ≥ N`. Детермінований сорт.

`learn/host_vetoes.py` — abstention (support<N); **вето взаємодії**: не пропонувати активні
sources АБО domain-rating-productive хости (передаються майнеру як `protected_hosts`); skip
уже-SEED/LEARNED/host-stoplist.

`learn/run_host_miner.py` — офлайн-оркестратор (`__main__`-guard): read_corpus → mine → vetoes →
**сабміт кандидатів у backend** `POST /api/internal/host-candidates` (X-API-Key). Дзеркало
`run_miner.py`.

### Шар C — backend + Vue-аудит (нетехнічний аудитор)

Backend таблиця `blocked_host` (+ Alembic-міграція): `id, host (unique), status
(pending|approved|rejected), media_ratio, aggregator_ratio, support, sample_urls (JSON),
reviewed_by, created_at, reviewed_at`. Дзеркало `SuggestedSource` (той самий moderation-патерн).

Ендпоінти:
- internal (X-API-Key): `POST /api/internal/host-candidates` (майнер сабмітить; ідемпотентно за
  host, як `create_suggestion`); `GET /api/internal/blocked-hosts` (краулер тягне approved-хости
  для живого гейта).
- admin (JWT): `GET /api/admin/host-candidates?status=pending`; `POST
  /api/admin/host-candidates/{id}/approve`; `/reject`. Дзеркало `suggested-sources`
  approve/reject у `routers/admin.py` + `crud/suggested_source.py`.

Admin Vue: `HostCandidatesView.vue` (дзеркало `SuggestedSourcesView.vue`) — список pending-хостів
із сигналами (media/aggregator/support + `sample_urls`) і approve/reject; роут+нав-пункт; тести.

## 4. Наскрізний потік (host-snowball)

Прохід: медіа/агрегатор-сторінка → Шар A ловить структурно (article/aggregator) → salvage або
drop, корпус пише `is_article`/`outbound_hosts` per host. Офлайн: `run_host_miner` агрегує → host
`X` перевищує пороги + support → вето (не source/не productive) → сабміт у backend (pending).
Модератор у Vue бачить `X` із сигналами → **approve** → `blocked_host.status=approved`. Наступний
прохід: `build_runner` фетчить approved → `blocklist.reload_learned([..., X])` → живий
`is_blocked_host(X)=True` → `X` більше не фейковий провайдер (salvage/drop). Reject → status=rejected,
майнер його більше не сабмітить (ідемпотентність + skip rejected).

## 5. Компоненти-файли

**Крауler:** `fetchers/website.py` (+is_article детект), `models.py` (`RawItem.is_article`),
`discovery/attribution.py` (article/aggregator вето + salvage-реордер + outbound_host_count у
PageCtx), `discovery/blocklist.py` (+LEARNED set + `reload_learned`), `learn/labeler.py`/
`learn/corpus.py` (+is_article/outbound_hosts у рядок), `learn/host_miner.py`, `learn/host_vetoes.py`,
`learn/run_host_miner.py`, `api_client.py` (+submit_host_candidate, +list_blocked_hosts),
`wiring.py` (fetch+reload_learned per pass; protected_hosts для майнера), `config.py` (кноби).

**Backend:** `models/blocked_host.py`, `schemas/blocked_host.py`, `crud/blocked_host.py`,
`routers/internal.py` (+2 ендпоінти), `routers/admin.py` (+3 ендпоінти), Alembic-міграція.

**Admin:** `views/HostCandidatesView.vue`, роут+нав, `api` клієнт-метод, тести.

## 6. Збереження попередньої автоматики (явно)

- Лексикон-пайплайн (промо-словник SEED+LEARNED, `run_miner`, snowball, **CLI term-audit
  `learn/audit.py`**) — НЕ чіпається, НЕ мігрується у Vue. Дві audit-поверхні співіснують
  (терми=CLI, хости=Vue) — свідома ціна збереження робочої автоматики; уніфікація — майбутній трек.
- Спільний корпус розширюється **адитивно** — term-miner читає свої ключі, ігнорує нові.
- `labeler.neg_anchor = is_blocked_host` тепер може відображати host-LEARNED (audit-gated, стартує
  порожнім) — корисніші негатив-мітки term-майнера, не регрес.
- `is_blocked_host` SEED+LEARNED, LEARNED-порожній = byte-еквівалент.
- domain-rating не ламається; вето виключає його productive-хости.

## 7. Ризики / tradeoffs

- **`is_article` over-block (recall, живий гейт, НЕ audit-gated):** легіт single-business лендінг
  із BlogPosting-schema → хибний дроп. Обмеження: article-вето лише коли нема Organization/
  LocalBusiness-сигналу (Шар A.1). Тюн-параметр.
- **aggregator over-block:** мультибренд-маркетплейс (внутрішні бренд-сторінки) НЕ триггериться, бо
  рахуємо лише **зовнішні** хости. Афілійовані/купон-сайти — цільові (правильно ловляться).
- **Майнер-навантаження аудиту:** пороги (support N, ratio) впливають на к-ть кандидатів, не на
  живу безпеку (все audit-gated).

## 8. Конфіг (крауler, дзеркально config.py × RUN.md × .env.example)

`attribution_hardening_enabled` (Шар A live-anchors; дефолт ON — це і є посилення);
`blocked_hosts_refresh` (фетч approved per pass; вкл/поріг); `aggregator_min_outbound` (напр. 3);
`host_miner_min_support` (напр. 3); `host_miner_media_min_ratio`, `host_miner_aggregator_min_ratio`;
шляхи/gating майнера (переюз corpus-гейта `autofill_enabled`). Backend: X-API-Key (наявний).

## 9. Тестування

- **Крауler:** is_article детект (website_fetcher); attribute() article/aggregator вето +
  salvage-реордер (реальні фікстури: медіа-стаття з outbound → third-party; медіа без лінка → None;
  legit business BlogPosting+Organization → лишається first-party); blocklist SEED+LEARNED +
  reload_learned byte-safe; host_miner агрегація+контраст; host_vetoes (support/protected/skip);
  run_host_miner сабміт; wiring fetch+reload best-effort; корпус адитивний (term-miner не зламано).
- **Backend:** blocked_host CRUD (ідемпотентний submit, approve/reject, list approved); internal
  2 ендпоінти (+401); admin 3 ендпоінти (+auth); міграція.
- **Admin:** HostCandidatesView (list/approve/reject, замоканий API); `npm run build`.
- Зелені: crawler (324+нові), backend (84+нові), admin (84+нові).

## 10. Свідомо поза скоупом

- Міграція term-audit у Vue (окремий майбутній трек).
- LLM-детекція медіа (офлайн-хвіст, P3).
- Ретроактивне перечищення вже-поданих оферів від нововиявлених медіа-хостів (лише forward).
- Telegram/IG/FB медіа-детекція структурна (host-only цей трек).
