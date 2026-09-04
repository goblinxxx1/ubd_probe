# Censoring-aware discovery — design

Дата: 2026-09-04
Гілка: `feat/censoring-aware-discovery`

## Проблема

Discovery плутає три незалежні речі:

| | що це | приклад (проба 2026-09-04, запит «взуття одяг знижка УБД») |
|---|---|---|
| (a) доступність рушія | транзиторно, залежить від IP/навантаження | brave: 10 через `ddgs`, «too many requests» через SearXNG; duckduckgo/startpage: CAPTCHA |
| (b) продуктивність фрази | чи запит виводить офери | той самий запит: 10 реальних оферів на google/brave |
| (c) релевантність | чи URL — справді UA-офер | bing віддав 10 англ. «HSE hazard symbols» — сміття |

**Механізм рецидиву.** `SearchPass` міряє урожай фрази `new_by_phrase` по тому, що випало в цьому проході, і живить ним EWMA + `dry_streak` (`search_state.record_yields`) та `effective_ttl`. Коли (a) транзиторно впало (капча/ратуліміт/кулдаун), краулер бачить `new_count=0` і зараховує його як **реальний нуль продуктивності**: після `cold_tries=3` `effective_ttl` множиться до ×8 → **продуктивну фразу штучно душать**, хоча офери існують.

Це класична помилка credit-assignment: **цензуроване спостереження ≠ нуль**. Bandit-література (MAB with missing data) прямо каже: пропущений reward треба ігнорувати (не оновлювати руку), а не штрафувати.

Попередній фікс (`fix/ddg-empty-not-block`, у main) закрив лише один прояв: «порожня видача» більше не кулить *бекенд*. Цей трек закриває загальний корінь — на рівні **урожаю фрази**.

## Рішення (ядро)

Ввести точний per-виклик сигнал **served vs censored** і рахувати урожай фрази лише коли її канал реально відповів.

- **served** = ≥1 бекенд/рушій цього виклику реально відповів (справжня видача АБО справжня порожнеча) → був хоча б один `record_success`.
- **censored** = жодного `record_success`: усі спроби — блок/ратуліміт/таймаут/backoff.

Чому не переюзати наявний `degraded`: після fix `fix/ddg-empty-not-block` навіть «усі бекенди віддали legit-empty» ставить `degraded=True`. Тобто `degraded` = «0 кандидатів» (і від порожнечі, і від цензури) — не розрізняє. Потрібен окремий сигнал.

## Потік даних (мінімально інвазивно, зворотньо-сумісно)

1. **`RotatingDdgProvider.__call__`** — локальний `served`, `True` на кожному `record_success` (справжні результати ТА legit-empty). Наприкінці виставляє атрибут `self.last_served: bool`. Global-backoff короткий шлях → `served=False`.
2. **`SearchCache.__call__`** — пробрасує `last_served` від внутрішнього провайдера; cache-hit → `served=True` (раніше вже віддали).
3. **`SearxngProvider.__call__`** — `self.last_served` за HTTP-наслідком: 200 з масивом `results` (хай порожнім) = served; HTTP-помилка / виняток / усі engines unresponsive = censored.
4. **`ActiveDiscovery.run`** — після кожного `provider(kw, page)` читає `getattr(self._provider, "last_served", True)` і накопичує `self.last_served_phrases: set[str]`. Дефолт `True` = fail-safe: незнайомий провайдер рахується served → поведінка не деградує.
5. **`SearchPass.run`** — об'єднує `last_served_phrases` по всіх `plans`. `record_yields` та `record_page_result` викликає **лише для served-фраз**. Цензуровані фрази не чіпає: без `dry_streak++`, без роздування `effective_ttl`, без просування page-курсора. Курсор гріда просувається як і раніше (фрази прочитані), але цензурована фраза лишається «due» на базовій каденції — не штрафується.

## Config

- Дефолт `search_backends`: `startpage,duckduckgo,yahoo,brave,mojeek` → `startpage,duckduckgo,yahoo,brave`. Причина: mojeek задокументовано слабкий для UA; після fix він безпечний, але марно з'їдає ~1/5 слотів ротації. Знявши — ротація частіше влучає в робочі бекенди.
- Оновити `crawler/.env.example` (коментар/значення) і `test_config.py`.

## Помилки / крайові випадки

- Усе best-effort. Невідомий сигнал `served` → вважаємо served (не гірше за поточну поведінку).
- Повністю цензурований прохід → нічого не пишемо (як зараз при `any_success=False`). Новина: **частково** цензурований прохід більше не штрафує зачеплені фрази.
- SERP page-курсор цензурованої фрази теж не рухаємо (інакше «пропустили б» сторінку, якої не бачили).

## Тести (TDD)

- `RotatingDdgProvider.last_served`: `True` на results; `True` на legit-empty («No results found.»); `False` коли всі спроби — ratelimit/timeout; `False` під global-backoff.
- `SearchCache`: пробрасує `last_served`; cache-hit → `True`.
- `SearxngProvider.last_served`: `True` на HTTP-200 (навіть порожньому); `False` на помилці/виключенні.
- `ActiveDiscovery`: `last_served_phrases` містить лише served-фрази; незнайомий провайдер → усі served.
- `SearchPass`: цензурована фраза — БЕЗ `record_yields`/`record_page_result`; served-фраза — З ними; частково-цензурований батч розділяється коректно.
- `test_config`: новий дефолт пулу без mojeek.

## Свідомо поза скоупом (Фаза 2, за даними)

- Per-engine health-облік для SearXNG-рушіїв і маршрутизація фраз через здорові+врожайні рушії.
- Data-driven чистка SearXNG engine-set (не за однією пробою).
- Агрегація 2-3 рушіїв/фразу за прохід (throttle-ризик).

Рішення: спершу полагодити credit-assignment, поміряти ефект, і лише за потреби додавати керування рушіями. Усе в межах інваріанту краулера (автономно, безкоштовно, один IP, без проксі).
