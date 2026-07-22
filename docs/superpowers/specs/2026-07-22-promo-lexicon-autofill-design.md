# Spec: Автонаповнення промо-лексикону (self-growing marketing lexicon)

**Дата:** 2026-07-22
**Гілка:** `feat/promo-lexicon-autofill`
**Місце в цілісній картині:** трек програми self-growing discovery (див. пам'ять
`ubd-crawler-discovery-scaling-brainstorm`). Попередні P1-важелі — query-grid, brand→domain
feed, sitemap-глибина — вже в `main`. Цей трек знімає наступний боттлнек: **статичний
промо/relevance-словник**, замінюючи його самонавчальним конвеєром. Проєктується під усю
картину, не як standalone-фіча (пам'ять `ubd-design-for-whole-picture`).

---

## 1. Мета

Промо-словник, що вирішує «чи текст/URL — це оффер», перестає бути статичним. Система
**сама пропонує нові промо-терми** з накопиченого корпусу, а людина лише **аудитує ~20
термів/тиждень** (не per-item). Розширення recall безпечне лише завдяки наявним precision-
гейтам (target-лексикон, discount-context, blocklist) — тому recall і precision ростуть у парі.

**Тверді рамки (з брейншторму, не переглядаються):**
- Людський модераційний гейт лишається; **авто-публікації термів немає**.
- Детермінований core екстракції лишається детермінованим (269-тест контракт); **навчання
  тільки офлайн**; вихід майнера — **untrusted → аудит**.
- Мітки БЕЗ людини в потоці = наші детерміновані гейти (auto-PASS/auto-FAIL) + фіксовані
  якорі (gov/media = негатив, schema.org `Offer` = позитив) + узгодження сигналів.
- Контраст-майнінг через **log-odds** (informative Dirichlet prior), не сира частота.
- Запобіжники замість вичитки: multi-domain support, PASS-collision backtest veto, abstention.

## 2. Критерій готовності (працює як комплекс, наскрізь)

Наскрізний тест на fixture-корпусі:
1. bootstrapped корпус (PASS/FAIL з якорями) →
2. майнер пропонує ≥1 осмислений промо-терм →
3. вето відсіює overfit/anchor-колізії/низьку впевненість →
4. `audit approve <term>` дописує терм у LEARNED-дані →
5. повторний матч живим гейтом ловить новий терм →
6. **усі наявні детерміновані тести (269) лишаються зеленими.**

Плюс жива Docker-перевірка: bootstrap по реальних brand-feed доменах → непорожня черга
кандидатів у `audit list`.

## 3. Свідомо НЕ входить у цей трек

- **Vue-адмінка аудиту** — v1-аудит = CLI + versioned дата-файл. Сторінка модерації термів
  у Vue — пізніший UX-апгрейд.
- **LLM-хвіст перефразувань** — опційний офлайн-класифікатор для хвоста; P3, окремо.
- **Авто-approve без людини** — терм ніколи не входить у живий лексикон «за впевненістю»;
  вето лише фільтрують чергу, апрув робить людина.

**Переїхало В скоуп:** snowball (прийнятий модератором офер → сильний PASS у корпус).

---

## 4. Архітектура

```
crawler/crawler/discovery/promo_lexicon.py   ← ЄДИНИЙ source-of-truth
    SEED   (курований, розширений цієї сесії: кирилиця-стеми + трансліт URL-токени)
    LEARNED (дата-файл promo_lexicon_learned.json; у репо ПОРОЖНІЙ)
        │ живить
        ├─ walker.url_is_promo            (URL-токени)
        └─ extract/heuristic.py           (текст-тригери, discount-context, free)
                    │ extract() → OfferCandidate (PASS) | None (FAIL)
                    ▼
crawler/crawler/learn/corpus.py  (CorpusRecorder)
    пише JSONL {text, label, host, anchors, matched_stems, source, ts}
        ▲                                   │
        │ snowball (сильний PASS)           │
backend internal endpoint                   ▼
GET /api/internal/approved-offers   crawler/crawler/learn/miner.py  (офлайн)
    (тексти прийнятих оферів)            log-odds контраст PASS↔FAIL
                                            → кандидат-стеми
                                                │
                                        crawler/crawler/learn/vetoes.py
                                            multi-domain / PASS-collision / abstention
                                                │
                                        candidates.json ── audit CLI ── approve → LEARNED
```

Bootstrap: одноразовий CLI, що ганяє наявні фетчери + `DomainWalker` по brand-feed доменах і
наповнює корпус, аби майнеру було з чого вчитися вже зараз.

---

## 5. Компоненти (детально)

### 5.1 `promo_lexicon.py` — єдиний модуль, два tier-и
- Зводить докупи теперішні розкидані джерела: `_OFFER_TRIGGERS`, `_DISCOUNT_CTX`, `_FREE`
  (з `extract/heuristic.py`) і `_PROMO_URL_TOKENS` (з `discovery/walker.py`).
- **SEED** — курований, розширений: укр. промо-стеми (напр. `спецпропоз`, `уцінк`,
  `ліквідац`, `бонус`, `кешбек`, `подарунок`, `друга за пів ціни`, `тільки сьогодні`,
  `гаряч пропозиц`, `супер ціна`, `вигідн`, `економ`, `розпродаж залишк`), а також
  трансліт-варіанти для URL-токенів. Точний перелік — на етапі реалізації, кожен стем
  супроводжений тестом-прикладом.
- **LEARNED** — `promo_lexicon_learned.json`: список схвалених термів + метадані (коли, ким,
  log-odds, support). **У репо файл порожній** → 269 тестів не змінюють поведінку. Наповнюється
  лише в живому деплої через audit CLI.
- Матчинг обох tier-ів — той самий детермінований движок (`_compile`, word-start boundary,
  як у `discovery/lexicon.py`/`geo.py`). Живий гейт лишається regex-стем, детермінований.
- Розділення tier-ів → завжди видно куроване vs навчене; тривіальний rollback.
- `walker.py` та `heuristic.py` імпортують промо-токени/тригери з `promo_lexicon` замість
  локальних кортежів (рефактор без зміни поведінки — покрито регрес-тестом).

### 5.2 Labeler + якорі
- **Мітка з наявних гейтів:** `extract()` дав `OfferCandidate` → **PASS**; повернув `None`
  → **FAIL**. Окремого класифікатора немає — гейт *і є* labeler.
- **Якорі** (сильні сигнали правди, окремо від мітки):
  - `is_blocked_host()` (gov/media/агрегатор, `discovery/blocklist.py`) → **negative anchor**.
  - Наявність schema.org `Offer` / промо-`og:`-розмітки у HTML → **positive anchor**.
- **Узгодження сигналів:** мітка + якір записуються обидва; майнер/вето використовують їх
  разом (напр. PASS без жодного позитивного сигналу поряд із negative-anchor host — слабкий).

### 5.3 `corpus.py` — `CorpusRecorder`
- Новий колаборатор, викликається там, де зараз `_extractor.extract(...)`
  ([`runner.py`](../../crawler/crawler/runner.py) `_crawl_source`, і в `ActiveHarvester.harvest`).
- Пише рядок JSONL: `{text, label: "pass"|"fail", host, anchors: {...}, matched_stems, source, ts}`.
- Локальний файловий стор через `corpus_path` (як `brand_domains_path`/`robots_cache_path`).
- Ротація за `corpus_max_mb` (найстаріші рядки вибувають).
- Приймає інжекцію в конструктор `Runner`/`ActiveHarvester`; коли `None` — no-op (сумісність).

### 5.4 Snowball (backend + crawler)
- **Backend:** новий internal-ендпоінт `GET /api/internal/approved-offers?since=<ts>`
  (X-API-Key, як інші internal-ендпоінти) — віддає `{text, host, approved_at}` оферів, які
  модератор **прийняв**. Потрібне поле «коли прийнято» для інкрементальної вибірки.
- **Crawler:** `CorpusRecorder` (або окремий `SnowballIngestor`) періодично тягне цей фід і
  пише тексти як **сильний PASS-якір** (мітка pass + прапорець `snowball: true`, вищий вагою
  в майнері). Курсор `since` зберігається локально (як `search_state`).
- Backend-тести (63–82) — тримати зеленими; додати тест ендпоінта.

### 5.5 Bootstrap CLI
- Команда `python -m crawler.learn.bootstrap` (або підкоманда наявного CLI): проганяє
  website-фетчер + `DomainWalker` по поточних brand-feed доменах, лейблить через екстрактор,
  наповнює корпус. Одноразово перед першим майнінгом; далі корпус доростає живими прогонами.

### 5.6 `miner.py` — офлайн контраст-майнер
- Токенізація текстів корпусу в стеми/біграми; нормалізація форм через лематизатор (5.7).
- **Weighted log-odds з informative Dirichlet prior** (Monroe, Colaresi, Quinn) PASS↔FAIL.
  Не сира частота — уникаємо перекосу на частих загальних словах.
- Кандидат = стем із високим позитивним log-odds, якого **немає** ні в SEED, ні в LEARNED,
  ні в reject-стоплисті.
- `miner_max_candidates_per_run` — стеля пропозицій за прохід.

### 5.7 Морфологія / лематизатор
- **Повноцінний лематизатор:** `pymorphy3` + `pymorphy3-dicts-uk`, **версія запінена** у
  `requirements`. Використовується **тільки в офлайн-майнері** для токенізації/групування форм.
- **Живий гейт НЕ використовує лематизатор** — лишається regex-стем (детермінізм цілий).
  Лематизатор впливає лише на те, які кандидати спливають; їх усе одно вичитує людина.
- Пін версії словника = відтворюваність майнера.

### 5.8 `vetoes.py` — запобіжники перед пропозицією
- **Multi-domain support:** терм має зустрітись у PASS на **≥ N різних registrable-доменах**
  (`miner_min_domain_support`, дефолт **N=3**); інакше відкинути (анти-poison/overfit).
- **PASS-collision backtest:** якщо додавання терму робить хоч один negative-anchor FAIL-док
  «PASS-подібним» (терм матчиться в gov/media-текстах корпусу) → вето.
- **Abstention:** log-odds < `miner_min_logodds` або support < N → «утриматись», не пропонувати.

### 5.9 Audit CLI + промоція
- `audit list` — звіт кандидатів (терм, log-odds, support, домени, приклади-сніпети).
- `audit approve <term>` — дописує терм у `promo_lexicon_learned.json` (з метаданими).
- `audit reject <term>` — у reject-стоплист (майнер більше не пропонує).
- Промоція в LEARNED — **єдиний** шлях, яким навчене потрапляє в живий гейт.

---

## 6. Детермінований контракт і тестова стратегія

- LEARNED-файл у репо **порожній** → наявні 269 crawler-тестів не змінюють поведінку.
- **Регрес рефактора:** тест, що SEED-зведення промо-токенів у `promo_lexicon` дає **той самий**
  набір матчів, що й теперішні `_OFFER_TRIGGERS`/`_DISCOUNT_CTX`/`_FREE`/`_PROMO_URL_TOKENS`.
- Нове покриття (fixtures, без мережі): labeler-мітки+якорі; corpus-запис/ротація; snowball-
  ingestion (замоканий фід); log-odds на синтетичному PASS/FAIL-корпусі; кожне вето окремо
  (multi-domain, PASS-collision, abstention); audit approve/reject; наскрізний сценарій §2.
- Backend: тест `GET /api/internal/approved-offers` (авторизація X-API-Key, `since`-фільтр).

## 7. Конфіг-кнопки (`crawler/crawler/config.py`, як наявні)

`corpus_path`, `corpus_max_mb`, `promo_lexicon_learned_path`, `snowball_state_path`,
`miner_min_domain_support` (N, дефолт 3), `miner_min_logodds`, `miner_max_candidates_per_run`,
`autofill_enabled`.

## 8. Ризики / нюанси

- **Порожній корпус на старті** — знято bootstrap-командою (§5.5).
- **Poison/overfit** — знято multi-domain support + PASS-collision backtest.
- **Дрейф лематизатора** — знято піном версії словника; до того ж він лише офлайн і кандидати
  проходять аудит.
- **Розсинхрон crawler↔backend (snowball)** — інкрементальний `since`-курсор + best-effort
  (збій фіду не валить прохід, як інші discovery-кроки в `runner.py`).
