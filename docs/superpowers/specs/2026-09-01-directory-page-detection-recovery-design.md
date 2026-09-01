# Відсічення каталог/агрегатор-сторінок + best-effort recovery бізнесу

**Дата:** 2026-09-01
**Тип:** краулер — discovery/extraction

## Проблема (реальний кейс)

Офер 452 (`pending_review`) створено з
`https://myhelp.com.ua/places/vinnytsia-language-school/services/znyzhka-...`
з `provider="MY Help"`. Але myhelp.com.ua — **каталог знижок для військових/УБД**,
не сторінка знижки конкретного бізнесу. Реальний бізнес — «Vinnytsia Language
School». Таких оферів з myhelp — **11** (9 pending + 2 rejected), усі
`provider="MY Help"`, усі за патерном `/places/<бізнес>/services/<офер>`.

Сторінки тонкі (CSR ~15KB), без schema.org, **без вихідного лінка на сайт
бізнесу** (лише соцмережі+карти). Назва бізнесу є в `<title>` (до « | MY Help»)
і в URL-слагу; місто/адреса — в тексті/картах.

Наявний `source_hint.business_domains_from_page` уже вміє підсовувати домен
бізнесу як джерело, АЛЕ лише коли на сторінці є контактний **email** бізнесу.
У myhelp його нема → механізм мовчить. Наш resolver — **name-search** варіант
того самого: назва+місто → веб-пошук → домен.

## Мета

1. **Тверде:** каталог/директорні сторінки **не стають офером напряму**
   (агрегатор ≠ сторінка знижки), як editorial/news-гейти.
2. **Best-effort (можна спробувати):** з такої сторінки витягти *хто пропонує*
   (назва+місто) → шукати бізнес у неті (автономно, $0) → додати його домен у
   пошук → звичайний пайплайн сам витягує офер із САЙТУ бізнесу (правильна
   атрибуція). Не знайшли / нема знижки на сайті → офера просто нема — ок.
3. **Нема офера з резолвленого домену → видалити домен із пошуку.**
4. **Retro:** відхилити 11 наявних myhelp-оферів + прогнати їхні назви через п.2.

**Інваріант** ([[ubd-crawler-autonomy-invariant]]): усе автоматично, безкоштовно,
без людини. Тому — жодних платних API (Google Places тощо), лише наявний
DDG/SearXNG-пошук. LLM-суддя (Qwen, $0) СВІДОМО поза v1 (див. «Не в скоупі»).

## Дизайн

Усе в краулері (`crawler/crawler/discovery/`). Точка вбудови — `_process_page`
у `harvest.py` (там, де вже стоять editorial-suppression і source_hint).

### 1. Детектор каталог-сторінки — `is_directory_page(cand, items)`

Нова функція в `host_quality.py` (поряд з `is_news_host`). Директорна сторінка =
**обидва**:
- **host або URL:** host у сид-списку `DIRECTORY_HOST_SEEDS`
  (старт: `{"myhelp.com.ua"}`), **АБО** URL-шлях матчить патерн лістинг-запису:
  сегмент із `{places, place, company, companies, firm, profile, catalog,
  business, org}` + ще ≥1 сегмент (сам бізнес), типово + під-ресурс
  `{services, service, offers, offer, discount, znyzhka, akciya, akciyi}`.
- **title:** має роздільник « | » (сутність \| бренд) — тобто сторінка називає
  *іншу* сутність, а не власника домену.

Byte-стабільність і word-start матч слагів — за наявними утилітами (як
`page_target_word_start`). Детектор навмисно вузький (низькі false-positives);
розширюємо лише за доказом промахів на реальних даних.

### 2. Гейт у `_process_page`

На початку `_process_page`, після обчислення `ctx`:
```
if is_directory_page(cand, items):
    self._recover_business(items, ctx)   # best-effort, side-effect only
    return structural_provider           # НЕ емітимо офери з цієї сторінки
```
Дзеркалить editorial-suppression: офери не збираються, домен не «отруюється».

### 3. Витяг ідентичності — `extract_business(items, cand)`

Повертає `(name, city|None)`:
- `name`: `<title>` до першого « | » (fallback — де-слаг сегмента бізнесу з URL:
  `vinnytsia-language-school` → `vinnytsia language school`). Обрізати сміття
  («Знижка … для …» — брати хвіст після бренд-роздільників, або сам слаг як
  надійніше джерело).
- `city`: матч наявним газетиром (`gazetteer.json`) по тексту сторінки/адресі.

### 4. Резолвер бізнес→домен — `resolve_business_site(name, city, search)`

Best-effort, $0, реюз наявного пошук-провайдера (`providers.py`/`search_pass`):
- запит `"<name>" <city>` (без міста, якщо None);
- з результатів відкинути: агрегатори/директорії (`is_blocked_host`,
  `DIRECTORY_HOST_SEEDS`), соцмережі/маркетплейси/медіа (наявні блоклісти),
  іноземні (`is_foreign_host`/`is_ru_by_geo`);
- узяти top-1 UA-бізнес-домен з мʼяким порогом впевненості (overlap токенів
  назви ↔ домен/тайтл; за None-міста поріг суворіший);
- повернути `host` або `None`.

### 5. Інʼєкція в пошук (автономно) + dedupe

- dedupe: персистентний JSON-set `recovered_businesses` (ключ =
  `normalize(name)|city`); вже резолвлений бізнес не чіпаємо (прибирає
  re-resolve loop без окремого memo-стору).
- знайдений домен → **наявний `aggregator_store`** (`AggregatorDomainStore.add`)
  — він уже re-surface'ить бізнес-домени як website-`SourceCandidate` і краулер
  фетчить їх автономно (той самий шлях, що osm/brand/aggregator-фіди). Реюз =
  нуль нового crawl-коду. Позначаємо origin (див. п.6).

### 6. Видалення домену без офера (нова вимога)

- recovery-origin домени тримаємо в JSON-set `recovered_domains`;
- після краулу такого домену, якщо `domain_registry` фіксує empty-pass (0 оферів)
  — `aggregator_store.remove(host)` (нова дрібна функція) + прибрати з
  `recovered_domains`. Органічно-нахарвестені агрегатор-домени лишаються під
  наявним empty-skip (не чіпаємо їх поведінку).
- `AggregatorDomainStore.remove(host)`: видалити зі списку, скоригувати cursor.

### 7. Retro-пас (одноразово)

Дві частини (краулер admin-прав не має — ходить лише через X-API-Key internal):
- **Admin-крок:** 11 наявних myhelp-оферів відхиляє людина новою bulk-reject
  кнопкою ([[ubd-admin-query-term-bulk-actions]] — той самий патерн для оферів
  уже є в `OffersListView`). Або, якщо myhelp додати в host-блокліст — наявне
  авто-відхилення за хостом-джерелом підхопить ([[ubd-backend-auto-reject-blocked-source]]).
- **Краулер-крок (разова CLI-функція):** для кожного з 11
  `article_url`/`title` → `extract_business` → `resolve_business_site` →
  `aggregator_store.add`. Заразом real-data валідація
  ([[feedback-validate-full-pipeline-real-data]]).

## Крайові випадки

- Генерична назва (нац-мережа «Планета Фітнес») → обовʼязковий збіг міста +
  поріг; інакше skip (best-effort, нічого не втрачаємо проти сьогодні).
- Директорія, що лінкує назовні → наявна гілка `_outbound_hosts`+`aggregator_store`
  уже працює; name-resolver — доповнення для тих, що не лінкують (myhelp).
- Сайт бізнесу сам іноземний/блокований → наявні geo/lang-гейти дропнуть при
  краулі → 0 оферів → п.6 видаляє домен.
- Пошук нічого не дав → `None`, домен не додається — ок.

## Не в скоупі (v1)

- **Qwen-суддя** як confirmer детекту / extractor назви — `is_directory_page` і
  `extract_business` роблю окремими функціями з єдиним місцем виклику, щоб підмінити
  на judge-версію = один рядок, КОЛИ евристика справді почне промахуватись на
  чужих каталогах. Зараз YAGNI.
- Host-level самонавчальний directory-класифікатор (K=2 тощо) — сид-список +
  URL-патерн достатньо; розширюємо за доказом.
- Харвест соц-профілів як якорів ідентичності — крихко/блокується.

## Тести (валідація на реальних даних)

- `is_directory_page`: 11 myhelp-URL/title фікстур → усі True; кілька first-party
  бізнес-сторінок → False.
- `extract_business`: 452 → («vinnytsia language school», «Вінниця»); ще 2-3 з 11.
- `resolve_business_site`: mock-пошук → домен (з фільтрацією блоклістів) / None
  (порожній результат, лише агрегатори/соц).
- Гейт `_process_page`: директорна сторінка → 0 `submit_offer`, виклик recovery.
- `aggregator_store.remove`: додати→видалити, cursor коректний; empty-pass hook
  видаляє лише recovery-origin домен.
- dedupe: та сама назва двічі → один resolve.
