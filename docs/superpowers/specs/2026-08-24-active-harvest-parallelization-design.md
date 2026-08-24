# Паралелізація активного harvest (новий трек)

**Дата:** 2026-08-24
**Статус:** затверджено (brainstorm)
**Скоуп:** `ActiveHarvester.harvest` (активний прохід). Scheduler, cadence, пасив — поза скоупом (пасив уже зроблено, [[ubd-crawler-passive-parallelization]]).

## Проблема

Активний `harvest` серійний ([harvest.py:65](crawler/crawler/discovery/harvest.py:65)): цикл `for idx, cand in enumerate(candidates)`, всередині — серійний per-URL fetch. На відміну від пасиву, активний має ДВІ особливості, яких у пасиві не було:

1. **Глобальний бюджет-лічильник** (`used >= self._budget` → зупинка проходу) — механізм термінації.
2. **`stop`-індекс** (повертається з `harvest`) керує `_mark_consumed_search_phrases`: пошукова фраза позначається harvested, лише коли ВСІ її кандидати оглянуті до `stop` (позиційна семантика). Це і живить SERP-пагінацію ([[ubd-crawler-serp-pagination]]).

Наївний пул зламав би і бюджет (недетерміновано, які кандидати фетчаться), і облік фраз (позиційний `stop` втрачає сенс при out-of-order).

## Взаємодія з SERP-пагінацією (перевірено)

**Просування per-phrase page-курсору повністю UPSTREAM від harvest.** `record_page_result` ([search_state.py:166](crawler/crawler/discovery/search_state.py:166)) рухає сторінку за **search-time** кількістю нових кандидатів (`new_by_phrase`), правило двох порожніх (dry≥2→стоп) і `page_cap` — теж там; викликається в `search_pass.run()` ([search_pass.py:82](crawler/crawler/discovery/search_pass.py:82)) ДО harvest. → **Паралелізація harvest не торкається просування сторінок.**

Єдина точка звʼязку harvest→пошук: `stop`-індекс → `_mark_consumed_search_phrases` → `mark_harvested(keys)` ([search_state.py:214](crawler/crawler/discovery/search_state.py:214)) ставить `harvested:True` на кеш-записи `(фраза,сторінка)`, щоб `drain()` не перевидавав. Тобто harvest впливає на пошук РІВНО через `stop`-індекс.

## Рішення: two-phase (plan → execute) з execution-re-check

Обґрунтування (перевірено вебом): це канонічна розвилка «static/two-phase plan-execute» vs «work-stealing queue»; задокументований компроміс — статичне/two-phase дає **детермінізм і відтворюваність** ціною балансування, work-stealing — навпаки. Нам визначальний детермінізм (облік бюджету+фраз = коректність), а балансування не потрібне (feed'и round-robin-інтерлівлять домени; домінує fetch). Тож two-phase.

- **Фаза 1 `_plan(candidates, budget)` — СЕРІЙНА:** проходить кандидатів по порядку, застосовує чисті/дешеві skip-гейти (geo/foreign/low-value/news/blocklist/revisit-seen_within/known/known_hosts) з їх in-scan side-ефектами (`geo_block_store.add`). Веде транзитний `selected_hosts: set` і трактує хост як «щойно бачений» для `seen_within`-гейта, щойно його обрано (cooldown ≫ тривалості проходу → ТОЧНА реплікація серійної same-host-супресії без fetch'ів). Лічить бюджет по РЕАЛЬНИХ fetch-кандидатах. Повертає `(ordered_fetch_list, stop)`, де `stop` = той самий індекс, що й серійний код.
- **Фаза 2 `_execute(ordered_fetch_list)` — ПАРАЛЕЛЬНА:** `ThreadPoolExecutor(max_workers=active_workers)`, диспетч у порядку pre-scan; кожен таск НА СТАРТІ **re-check** execution-feedback гейтів проти поточного спільного стану (`is_blocked_host` — уже з lang/media-блоками цього проходу; `normalize_ref in known`). Now-blocked/known → скіп без fetch (examined, як серійно). Інакше `_harvest_one` + `registry.record` + media-block post-processing. Per-task локальний summary; злиття після join.
- `harvest` повертає той самий `stop` → `_mark_consumed_search_phrases` **без змін**.

**Чесна межа (закладено явно):** бітова тотожність із серійним `stop` у ВСІХ випадках недосяжна — feedback-супресії (lang/media/known) залежать від порядку завершення fetch'ів, а він за паралелізму інший. Дизайн дає максимум практично можливого: детермінований examined-префікс (консумпція фраз коректна, self-consistent, БЕЗ ВТРАТ — погранична фраза щонайбільше перевидасться `drain()`, ідемпотентно), бюджет по реальних fetch'ах, re-check усуває практично всі зайві fetch'і. Same-host `seen_within` відтворюється ТОЧНО (симуляція `selected_hosts`).

## Розширення потокобезпечності

Пасивний трек уже зробив потокобезпечними: `DomainRateLimiter` (per-domain лок), `DomainRegistry`, `CorpusRecorder`, `RobotsPolicy`, `LockedSet`. Активний **додає internal `threading.Lock`** трьом сторам (той самий патерн `add→_save` з фіксованим tmp-шляхом, та сама гонка, що ловили в RobotsPolicy):

- `GeoBlockStore.add/_save` ([geo_block.py:37](crawler/crawler/discovery/geo_block.py:37)) — виклик у pre-scan-фазі (серійній), лок як консистентність/захист.
- `LangBlockStore.add/_save` ([lang_block.py:37](crawler/crawler/discovery/lang_block.py:37)) — у execution → лок обовʼязковий.
- `AggregatorDomainStore.add/_save` ([aggregator_feed.py:50](crawler/crawler/discovery/aggregator_feed.py:50)) — read-modify-write `_data`+`_save`, у execution → лок обовʼязковий.
- `media_blocker.block` check-then-act (два таски бачать `media_block_due` true) — прийнятний minor: backend-блок ідемпотентний.

`known` — `LockedSet` (уже є); `summary` — per-task локальний + злиття.

## Потік даних

```
run_active → harvester.harvest(candidates, cats, known, summary, known_hosts):
  # Фаза 1 — серійна
  ordered_fetch, stop = _plan(candidates, budget)   # чисті гейти + selected_hosts + geo_block.add
  # Фаза 2 — паралельна
  with ThreadPoolExecutor(max_workers=active_workers) as ex:
     futures = [ex.submit(_execute_one, cand, local_summary) for cand in ordered_fetch]
     for f in as_completed(futures): merge(local)
        # _execute_one: re-check is_blocked_host/known → skip|(_harvest_one+record+media-block)
  return stop
runner._mark_consumed_search_phrases(candidates, stop)   # без змін
```

## Обробка помилок

Per-candidate ізоляція збережена: виняток у таску → `local_summary["errors"] += 1` + лог (як зараз, [harvest.py:113](crawler/crawler/discovery/harvest.py:113)), у межах таску (щоб один домен не топив пул).

## Конфіг

Нова ручка `active_workers` (env `ACTIVE_WORKERS` → `config` → `wiring` → `ActiveHarvester`), дефолт **4**. Звичайний конфіг; `1` = серійний відкат (диспетч у порядку, один воркер). Пул створюється лише в `harvest`; пасив/scheduler не чіпаються.

## Тестування (verify-by-execution)

- **`_plan` детермінізм:** на фікстурах відтворює серійний `(ordered_fetch, stop)`, включно з budget-boundary та skip-гейтами.
- **Same-host `seen_within` симуляція:** два кандидати одного хоста в батчі → другий не в fetch-list (як серійно), БЕЗ реального fetch у pre-scan.
- **Re-check:** кандидат, чий хост заблоковано під час проходу, скіпається в execution без fetch.
- **Злиття summary:** offers/errors/suggestions = серійний baseline.
- **`active_workers=1`:** еквівалентність серійному.
- **Нові локи:** concurrency-тести geo/lang/aggregator сторів (N потоків → файл валідний, без втрат).
- **Жива Docker-перевірка:** ребілд + активний прохід при `ACTIVE_WORKERS=4` vs `1` → сумарні offers/suggestions зіставні, errors=0, політ збережено, пагінація-курсори просуваються як і раніше.

## Поза скоупом (YAGNI)

Scheduler, cadence активного проходу, async-перепис, зміна SERP-пагінації. Бітова тотожність stop з серійним (недосяжна — див. «Чесна межа»).
