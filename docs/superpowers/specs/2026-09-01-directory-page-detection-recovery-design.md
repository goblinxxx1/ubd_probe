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
4. **Retro (автономно, БЕЗ людини/кнопок):** наявні каталог-офери (11 myhelp)
   авто-відхиляються бекенд-sweep'ом при реєстрації directory-хоста; їхні назви
   краулер прогоняє через п.2.

**Інваріант** ([[ubd-crawler-autonomy-invariant]]): усе автоматично, безкоштовно,
**без участі людини і без жодної нової UI-кнопки**. Жодних платних API (Google
Places тощо) — лише наявний DDG/SearXNG-пошук. LLM-суддя (Qwen, $0) СВІДОМО поза
v1 (див. «Не в скоупі»). Наявна bulk-reject кнопка оферів
([[ubd-admin-query-term-bulk-actions]]) — окрема фіча, цим треком НЕ
використовується і НЕ розширюється.

## Дизайн

Переважно краулер (`crawler/crawler/discovery/`), головна точка вбудови —
`_process_page` у `harvest.py` (там, де editorial-suppression і source_hint);
плюс невелика бекенд-частина (п.7) для автономного авто-відхилення наявних/майбутніх
каталог-оферів.

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
    self._register_directory_host(ctx.host)  # internal API, ідемпотентно (п.7)
    self._recover_business(items, ctx)       # best-effort, side-effect only
    return structural_provider               # НЕ емітимо офери з цієї сторінки
```
Дзеркалить editorial-suppression: офери не збираються, домен не «отруюється».
Реєстрація хоста (п.7) — first-detection тригер бекенд-sweep'у наявних оферів;
обидва виклики best-effort (див. «Робастність»).

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

### 7. Directory-хост: реєстрація + бекенд авто-відхилення (повністю автономно)

Коли краулер вперше детектить directory-сторінку (п.2), він **реєструє хост як
directory** через наявний internal API (X-API-Key; краулер admin-прав не має).
Бекенд на реєстрації робить ДВІ речі — це і є автономне «retro без кнопок»:

- **Sweep наявних:** soft-reject усіх уже наявних оферів цього хоста, СУВОРО
  scoped — `created_by=crawler` **І** `status=pending_review` **І** точний хост
  (site_url/article_url) == directory-хост. Мітка причини «directory-source».
  Це відхиляє 11 myhelp-оферів без людини. Published / людино-курійовані —
  недоторкані. Reversible (rejected = мʼякий кошик). Ідемпотентно (повторна
  реєстрація нічого нового не робить).
- **Gate майбутніх:** `create_offer` відхиляє нові офери, чий хост-джерело —
  зареєстрований directory-хост (belt-and-suspenders до крауперної suppression;
  дзеркало наявного `_blocked_source_host`, [[ubd-backend-auto-reject-blocked-source]]).

**ВАЖЛИВО — directory-хост ≠ no-fetch блокліст.** Directory-хост лишається
**fetchable**: краулер і далі бачить його сторінки через active-search і
recover'ить з них бізнеси (п.2-5). No-fetch зупинив би recovery. Directory-список
персиститься окремо від `blocked_hosts` (той — no-fetch); нова таблиця/поле
`directory_hosts` АБО прапорець на blocked_host з reason=`directory`+`fetchable`.

Retro для 11 myhelp = природний наслідок: перша ж детекція myhelp-сторінки
реєструє хост → sweep прибирає 11, а `resolve_business_site` по їхніх назвах
підіймає реальні бізнеси. Заразом real-data валідація
([[feedback-validate-full-pipeline-real-data]]).

## Крайові випадки

- Генерична назва (нац-мережа «Планета Фітнес») → обовʼязковий збіг міста +
  поріг; інакше skip (best-effort, нічого не втрачаємо проти сьогодні).
- Директорія, що лінкує назовні → наявна гілка `_outbound_hosts`+`aggregator_store`
  уже працює; name-resolver — доповнення для тих, що не лінкують (myhelp).
- Сайт бізнесу сам іноземний/блокований → наявні geo/lang-гейти дропнуть при
  краулі → 0 оферів → п.6 видаляє домен.
- Пошук нічого не дав → `None`, домен не додається — ок.

## Робастність (автономно і не ламатися)

Ключова вимога: працює само, без людини, і збій однієї частини не валить пайплайн.

- **Recovery — суто side-effect, best-effort:** `_recover_business` загорнутий у
  `try/except` (як наявний per-page `except` у `_harvest_one`); будь-яка помилка
  (пошук, парсинг, мережа) логується і НЕ зупиняє harvest. Офери інших сторінок
  не страждають.
- **Sweep — вузько scoped + reversible + ідемпотентний:** чіпає лише
  crawler+pending+точний-хост; повторна реєстрація no-op; помилково зачеплене
  відновлюється (мʼякий кошик). Не може знищити published/курійоване.
- **Directory-хост fetchable** — recovery не самоблокується (no-fetch зупинив би
  її). Список directory окремо від no-fetch blocklist.
- **Detection вузький** — сид-хост + конкретний URL-патерн + « | »; низькі
  false-positives, щоб не глушити реальні first-party офери.
- **Dedupe + removal** тримають систему обмеженою: назва не резолвиться двічі,
  мертвий домен видаляється — без нескінченного росту роботи/фіду.
- **Все на наявних гейтах** (geo/lang/blocklist/registry) — resolver не вводить
  нового шляху довіри; іноземне/рос/блоковане відсікається як і раніше.
- **Internal API, не admin** — краулерна реєстрація directory-хоста йде через
  X-API-Key internal-ендпоінт (краулер не має і не потребує admin-прав).

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
- Гейт `_process_page`: директорна сторінка → 0 `submit_offer`, виклик recovery
  + реєстрація хоста.
- `aggregator_store.remove`: додати→видалити, cursor коректний; empty-pass hook
  видаляє лише recovery-origin домен.
- dedupe: та сама назва двічі → один resolve.
- **Бекенд sweep (автономне retro):** реєстрація directory-хоста → наявні
  crawler+pending офери цього хоста стають `rejected`; published/інший-хост/
  не-crawler — недоторкані; повторна реєстрація ідемпотентна.
- **Бекенд create-gate:** новий crawler-офер із зареєстрованого directory-хоста
  → відхиляється на створенні.
- **Робастність:** `_recover_business`, що кидає виняток, НЕ валить `_harvest_one`
  (офери решти сторінок емітяться); падіння internal-реєстрації логується й не
  зупиняє harvest.
