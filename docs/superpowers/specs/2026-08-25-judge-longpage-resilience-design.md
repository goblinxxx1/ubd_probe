# Судья на довгих сторінках: обрізання промпту + розчеплення breaker

**Дата:** 2026-08-25
**Гілка:** `fix/judge-longpage-resilience`

## Проблема (root cause, доведено)

Discovered-офери 417/418/419 (wog.ua «офіційні правила акції» — юр-документи) потрапили
в чергу модерації як мотлох. Дві причини:

1. **Екстрактор-леак (окремо, не в цьому треку):** гейт аудиторії — «мішок термінів»:
   `військові дії` (форс-мажор) → `warrior`; `ЗСУ` (бенефіціар благодійності) → `warrior`.
2. **Семантичний суддя не спіймав, бо сам упав.** `LlamaCppJudge._candidate_text`
   вкладає в промпт **увесь `body` без обрізання**. Body цих сторінок = 10 250 / 4 308 /
   24 824 символів. Разом із system-промптом + 5 few-shot — перевищує llama.cpp
   `--ctx-size 4096` → сервер вертає **400 Bad Request**.
   Лог: `2026-08-25 07:21:32 WARNING crawler.judge.gate: relevance judge unavailable,
   degrading to keep-all this pass: Client error '400 Bad Request'` — рівно перед
   створенням 417 (07:21:33) і 418 (07:21:38).
3. **Breaker глушить весь прохід.** `RelevanceGate.keep` на БУДЬ-який виняток ставить
   `self._broken=True` → keep-all до кінця проходу. Тож після 400 усі наступні офери
   (417/418/419) пройшли **без суду**. У judge-кеші лише 3 записи (легіт-офери, оцінені
   ДО падіння).

**Гірка іронія:** сторінки, що НАЙБІЛЬШЕ потребують семантичного суду (величезні
юр-«правила» з випадковим audience-словом), — саме ті, що переповнюють контекст і
оминають суддю.

## Рішення

Скоуп: **2 файли**, без нових config-ключів, без зміни `ctx-size` (лікує симптом,
жере RAM, завжди є більша сторінка).

### Fix #1 — обрізати body в промпті (`crawler/judge/llama.py`)

- `_candidate_text`: кап `body` до `_MAX_BODY_CHARS = 2000` (голова + `…` якщо обрізано).
- `title` / `discount` / `url` лишаються цілими (короткі, високосигнальні).
- Достатньо голови: перші ~2k rules-сторінки = «ОФІЦІЙНІ ПРАВИЛА… порядок проведення
  та умови», що лягає під наявний few-shot #2 судді _«пункт оферти/умови → genuine=False»_.
  Похований далі випадковий audience-токен зрізається — і добре: суддя судить, ЧИМ є
  сторінка, а не про випадкове слово.

### Fix #2 — розчепити breaker (`crawler/judge/llama.py` + `crawler/judge/gate.py`)

- Новий виняток `JudgeUnavailable(JudgeError)`.
- `llama.verdict`:
  - `except (httpx.ConnectError, httpx.ConnectTimeout)` → `JudgeUnavailable` (нема з'єднання);
  - `except Exception` → `JudgeError` (усе решта: 400, read-timeout, 5xx, парсинг).
- `gate.keep`:
  - `except JudgeUnavailable` → `self._broken=True` + `return True` (деградує прохід, як зараз);
  - `except JudgeError` → `return True` **лише цього кандидата**, breaker НЕ чіпати, у кеш не писати.
- Обидва шляхи fail-open (keep=True) — additive-філософія судді збережена.
  Одна погана сторінка більше НЕ глушить суд для решти проходу.

## Тести (TDD, спершу failing)

`crawler/tests/test_*` (розширити наявні judge-тести):
- `_candidate_text`: body>2000 → рівно 2000+`…`; короткий body — без змін; title/url цілі.
- `verdict`: fake-клієнт кидає `httpx.ConnectError` → `JudgeUnavailable`;
  `httpx.HTTPStatusError`(400) і `httpx.ReadTimeout` → `JudgeError`.
- `gate.keep`: `JudgeError` → `True` і breaker НЕ зламаний (наступний виклик знову судить,
  через spy-judge); `JudgeUnavailable` → `True` і breaker зламаний (наступний keep без
  виклику судді).
- Наявні judge-тести лишаються зелені.

## Жива валідація

Після фіксу: зібрати кандидата з реальних даних офера 418 і викликати **живий** llama
через контейнер краулера — підтвердити, що тепер вертається вердикт (очікувано
genuine=False «правила акції»), а не 400.

## Поза скоупом (свідомо)

- Екстрактор-леак (bag-of-terms audience, `військові дії`→warrior, rules-сторінки як
  target) — окремий трек. Тут лагодимо ЛИШЕ семантичний бекстоп.
- Наявні 417/418/419 — модератор відхиляє (для того черга й є).
- Підняття `ctx-size`.
