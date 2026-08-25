# Judge Long-Page Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Зробити так, щоб семантичний суддя не падав з 400 на довгих сторінках, і щоб один поганий кандидат не глушив суд для всього проходу.

**Architecture:** Обрізаємо `body` в промпті судді до 2000 символів (перестає переповнювати llama.cpp ctx-size 4096). Розділяємо помилки судді на `JudgeUnavailable` (нема з'єднання → breaker глушить прохід) і `JudgeError` (усе решта → skip лише цього кандидата, fail-open). Обидва fail-open (keep=True) — additive-філософія судді збережена.

**Tech Stack:** Python 3.12, httpx (`MockTransport` для тестів), pytest.

## Global Constraints

- Робоча директорія виконавця: `D:\ubd_probe\crawler`.
- Запуск тестів: `.venv/Scripts/python.exe -m pytest <шлях> -q` (з директорії `crawler`).
- Українська в коментарях/повідомленнях (російська заборонена — [[language-preference]]).
- Без нових config-ключів; без зміни llama `--ctx-size`.
- Гілка вже створена: `fix/judge-longpage-resilience`. Мердж у main наприкінці.
- Fail-open: будь-яка помилка судді → `keep=True` (нуль регресії проти сьогодні).

## File Structure

- Modify `crawler/crawler/judge/llama.py` — константа обрізання + `_candidate_text` truncation; клас `JudgeUnavailable`; класифікація винятків у `verdict`.
- Modify `crawler/crawler/judge/gate.py` — розділені `except` для `JudgeUnavailable` vs `JudgeError`.
- Modify `crawler/tests/test_judge_llama.py` — тести обрізання + класифікації винятків.
- Modify `crawler/tests/test_relevance_gate.py` — оновити breaker-семантику + новий тест `JudgeUnavailable`.

---

### Task 1: Обрізати body в промпті судді

**Files:**
- Modify: `crawler/crawler/judge/llama.py` (метод `_candidate_text`, ~ряд 52-57)
- Test: `crawler/tests/test_judge_llama.py`

**Interfaces:**
- Produces: модульна константа `_MAX_BODY_CHARS = 2000`; `LlamaCppJudge._candidate_text(cand) -> str` обрізає `body` до 2000 символів + `…`.

- [ ] **Step 1: Написати failing-тести**

Додати в кінець `crawler/tests/test_judge_llama.py`:

```python
def test_candidate_text_truncates_long_body():
    j = LlamaCppJudge(_client(lambda r: httpx.Response(200, json={})), model="m")

    class C:
        title = "T"; discount_type = "percent"; discount_value = 20
        article_url = "u"; body = "x" * 5000

    text = j._candidate_text(C())
    assert "x" * 2000 + "…" in text
    assert "x" * 2001 not in text          # не більше 2000 підряд перед трьома крапками


def test_candidate_text_keeps_short_body():
    j = LlamaCppJudge(_client(lambda r: httpx.Response(200, json={})), model="m")

    class C:
        title = "T"; discount_type = "free"; discount_value = None
        article_url = "u"; body = "short body"

    text = j._candidate_text(C())
    assert "short body" in text and "…" not in text
```

- [ ] **Step 2: Запустити — переконатись, що падають**

Run: `.venv/Scripts/python.exe -m pytest tests/test_judge_llama.py -q`
Expected: FAIL (`test_candidate_text_truncates_long_body` — тіло не обрізане, `"x"*2001 in text`).

- [ ] **Step 3: Реалізувати обрізання**

У `crawler/crawler/judge/llama.py` додати константу перед класом `LlamaCppJudge` (напр. одразу після `_EXAMPLES`):

```python
# Довгі юр-сторінки («правила акції») переповнюють ctx-size 4096 → 400 Bad Request.
# Судді юр-boilerplate ні до чого — обрізаємо тіло до безпечного бюджету (голова
# несе тайтл/тип сторінки, що й вирішує genuine).
_MAX_BODY_CHARS = 2000
```

Замінити метод `_candidate_text`:

```python
    def _candidate_text(self, cand) -> str:
        disc = f"{getattr(cand, 'discount_type', None)} {getattr(cand, 'discount_value', None)}"
        body = getattr(cand, "body", "") or ""
        if len(body) > _MAX_BODY_CHARS:
            body = body[:_MAX_BODY_CHARS] + "…"
        return (f"{getattr(cand, 'title', '') or ''}\n"
                f"{body}\n"
                f"знижка: {disc}\n"
                f"url: {getattr(cand, 'article_url', '') or ''}")
```

- [ ] **Step 4: Запустити — переконатись, що проходять**

Run: `.venv/Scripts/python.exe -m pytest tests/test_judge_llama.py -q`
Expected: PASS (усі, включно з наявними).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/judge/llama.py crawler/tests/test_judge_llama.py
git commit -m "fix(judge): обрізати body в промпті до 2000 символів (проти 400 на довгих сторінках)"
```

---

### Task 2: Класифікувати помилки судді (`JudgeUnavailable` vs `JudgeError`)

**Files:**
- Modify: `crawler/crawler/judge/llama.py` (додати `import httpx`, клас `JudgeUnavailable`, гілки `except` у `verdict`)
- Test: `crawler/tests/test_judge_llama.py`

**Interfaces:**
- Produces: `class JudgeUnavailable(JudgeError)`; `verdict` кидає `JudgeUnavailable` при `httpx.ConnectError`/`httpx.ConnectTimeout`, інакше `JudgeError`.
- Consumes (Task 1): `_candidate_text` (без змін).

- [ ] **Step 1: Написати failing-тести**

Спершу оновити import у шапці `crawler/tests/test_judge_llama.py`:

```python
from crawler.judge.llama import LlamaCppJudge, JudgeError, JudgeUnavailable
```

Додати тести:

```python
def test_connect_error_raises_judge_unavailable():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)
    j = LlamaCppJudge(_client(handler), model="qwen2.5-7b-instruct")
    try:
        j.verdict(_Cand())
        assert False, "expected JudgeUnavailable"
    except JudgeUnavailable:
        pass


def test_http_400_raises_plain_judge_error_not_unavailable():
    def handler(request):
        return httpx.Response(400, text="context length exceeded")
    j = LlamaCppJudge(_client(handler), model="qwen2.5-7b-instruct")
    try:
        j.verdict(_Cand())
        assert False, "expected JudgeError"
    except JudgeUnavailable:
        assert False, "400 має бути per-candidate JudgeError, не Unavailable"
    except JudgeError:
        pass


def test_read_timeout_raises_plain_judge_error_not_unavailable():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)
    j = LlamaCppJudge(_client(handler), model="qwen2.5-7b-instruct")
    try:
        j.verdict(_Cand())
        assert False, "expected JudgeError"
    except JudgeUnavailable:
        assert False, "read-timeout має бути per-candidate JudgeError, не Unavailable"
    except JudgeError:
        pass
```

- [ ] **Step 2: Запустити — переконатись, що падають**

Run: `.venv/Scripts/python.exe -m pytest tests/test_judge_llama.py -q`
Expected: FAIL (`ImportError: cannot import name 'JudgeUnavailable'`).

- [ ] **Step 3: Реалізувати**

У `crawler/crawler/judge/llama.py` додати `import httpx` у блок імпортів (після `import logging`):

```python
import httpx
```

Додати клас одразу після наявного `class JudgeError(Exception): pass`:

```python
class JudgeUnavailable(JudgeError):
    """Суддя недосяжний (нема з'єднання) — ламає breaker у RelevanceGate, щоб
    деградувати ВЕСЬ прохід. Відрізняється від per-candidate JudgeError (погане
    тіло / HTTP 4xx-5xx / read-timeout / парсинг), який скіпає лише цього кандидата."""
    pass
```

Замінити хвіст `verdict` (блок `try/except`) — саме `except`:

```python
        try:
            r = self._client.post("/v1/chat/completions", json=body, timeout=self._timeout)
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            return Verdict(genuine=bool(parsed["genuine"]),
                           page_scoped=bool(parsed["page_scoped"]),
                           reason=str(parsed.get("reason", "")))
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise JudgeUnavailable(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 — per-candidate: скіп цього, суд триває
            raise JudgeError(str(exc)) from exc
```

- [ ] **Step 4: Запустити — переконатись, що проходять**

Run: `.venv/Scripts/python.exe -m pytest tests/test_judge_llama.py -q`
Expected: PASS (усі, включно з наявними `test_llama_judge_http_error_raises_judge_error` (500) і `test_llama_judge_bad_json_raises_judge_error`).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/judge/llama.py crawler/tests/test_judge_llama.py
git commit -m "fix(judge): JudgeUnavailable для нема-з'єднання vs JudgeError для решти"
```

---

### Task 3: Розділити breaker у RelevanceGate

**Files:**
- Modify: `crawler/crawler/judge/gate.py` (`keep`, ~ряд 30-34)
- Test: `crawler/tests/test_relevance_gate.py`

**Interfaces:**
- Consumes (Task 2): `JudgeUnavailable`, `JudgeError` з `crawler.judge.llama`.
- Produces: `RelevanceGate.keep` — `JudgeUnavailable` ставить `self._broken=True` (деградує прохід); `JudgeError` скіпає лише цього кандидата (breaker незмінний).

- [ ] **Step 1: Оновити наявний тест + додати новий (failing)**

У `crawler/tests/test_relevance_gate.py` оновити import:

```python
from crawler.judge.llama import JudgeError, JudgeUnavailable
```

**Замінити** наявний `test_judge_error_degrades_and_trips_breaker` на нову семантику:

```python
def test_judge_error_skips_candidate_without_tripping_breaker(tmp_path):
    j = FakeJudge(exc=JudgeError("bad content / 400"))
    g = _gate(tmp_path, j)
    assert g.keep(_Cand("a")) is True         # fail-open цього кандидата
    assert g.keep(_Cand("b")) is True         # breaker НЕ зламаний -> суддю викликано знову
    assert j.calls == 2


def test_judge_unavailable_trips_breaker(tmp_path):
    j = FakeJudge(exc=JudgeUnavailable("connection refused"))
    g = _gate(tmp_path, j)
    assert g.keep(_Cand("a")) is True         # деградація: лишає як сьогодні
    assert g.keep(_Cand("b")) is True         # breaker спрацював -> подальших викликів нема
    assert j.calls == 1
    g.reset_breaker()
    assert g.keep(_Cand("c")) is True
    assert j.calls == 2                         # breaker скинуто -> суддю викликано знову
```

- [ ] **Step 2: Запустити — переконатись, що падає**

Run: `.venv/Scripts/python.exe -m pytest tests/test_relevance_gate.py -q`
Expected: FAIL (`test_judge_error_skips_candidate_without_tripping_breaker`: наразі JudgeError ламає breaker → `j.calls == 1`, тест чекає `2`).

- [ ] **Step 3: Реалізувати розділені except**

У `crawler/crawler/judge/gate.py` додати import після `import logging`:

```python
from crawler.judge.llama import JudgeError, JudgeUnavailable
```

Замінити блок `try/except` у `keep`:

```python
        try:
            v = self._judge.verdict(candidate)
        except JudgeUnavailable as exc:
            self._broken = True
            log.warning("relevance judge unavailable, degrading to keep-all this pass: %s", exc)
            return True
        except JudgeError as exc:  # per-candidate: скіп лише цього, breaker незмінний
            log.warning("relevance judge skipped this candidate (fail-open): %s", exc)
            return True
```

(Решта методу — запис у кеш + `return v.genuine and v.page_scoped` — без змін. `verdict` гарантовано кидає лише `JudgeError`/`JudgeUnavailable`, тож дві гілки вичерпні.)

- [ ] **Step 4: Запустити — переконатись, що проходять**

Run: `.venv/Scripts/python.exe -m pytest tests/test_relevance_gate.py -q`
Expected: PASS (усі 4: disabled, junk-dropped, cache-hit, + два breaker-тести).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/judge/gate.py crawler/tests/test_relevance_gate.py
git commit -m "fix(judge): breaker ламається лише на JudgeUnavailable; JudgeError скіпає 1 кандидата"
```

---

### Task 4: Повний прогін + жива валідація на llama

**Files:** (без змін коду — верифікація)

**Interfaces:**
- Consumes: усі попередні таски.

- [ ] **Step 1: Повний прогін crawler-тестів**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: PASS (усе зелене, нуль регресій).

- [ ] **Step 2: Ребілд крауле-контейнера (щоб фікс потрапив у live)**

Run:
```bash
docker compose --profile crawler build crawler
docker compose --profile crawler up -d crawler
```
Expected: контейнер перезібрано й піднято.

- [ ] **Step 3: Жива валідація судді на реальних даних офера 418 (проти живого llama)**

Скрипт нижче тягне title/body/discount/url офера 418 з БД у файл, копіює у контейнер, і викликає **справжній** `LlamaCppJudge` проти `http://llama:8080`. Очікуємо ВЕРДИКТ (не 400/виняток), імовірно `genuine=False` («правила акції»).

Run (Git Bash, `MSYS_NO_PATHCONV=1`):
```bash
export MSYS_NO_PATHCONV=1
docker exec ubd_probe-db-1 sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" --default-character-set=utf8mb4 -N -B ubd -e "
SELECT CONCAT(title, CHAR(9), discount_type, CHAR(9), IFNULL(discount_value,\"\"), CHAR(9), article_url, CHAR(9), REPLACE(description, CHAR(10), \" \")) FROM offers WHERE id=418"' 2>/dev/null > /tmp/o418.tsv
docker cp /tmp/o418.tsv ubd_probe-crawler-1:/tmp/o418.tsv
docker exec ubd_probe-crawler-1 python -c "
import httpx
from crawler.judge.llama import LlamaCppJudge
row = open('/tmp/o418.tsv', encoding='utf-8').read().rstrip('\n').split('\t')
title, dt, dv, url, body = row[0], row[1], row[2], row[3], row[4]
class C:
    pass
c = C(); c.title=title; c.discount_type=dt; c.discount_value=dv; c.article_url=url; c.body=body
j = LlamaCppJudge(httpx.Client(base_url='http://llama:8080'), model='qwen2.5-7b-instruct', timeout=60.0)
v = j.verdict(c)
print('VERDICT genuine=%s page_scoped=%s reason=%s' % (v.genuine, v.page_scoped, v.reason))
"
```
Expected: рядок `VERDICT genuine=... page_scoped=... reason=...` **без винятку/400**. (Якщо `genuine=False` — суддя тепер відсіює цей мотлох; якщо `True` — суддя принаймні відпрацював, а leak лежить на extractor-треку.)

- [ ] **Step 4: (за потреби) повторити на офері 419 (найбільший body, 24824)**

Той самий скрипт з `id=419`. Expected: знову ВЕРДИКТ без 400 (тіло обрізане до 2000 у промпті).

---

## Self-Review

- **Spec coverage:** Fix #1 (truncation) → Task 1 ✓. Fix #2 (JudgeUnavailable + verdict) → Task 2 ✓; (gate split) → Task 3 ✓. Тести TDD → у кожній тасці ✓. Жива валідація → Task 4 ✓. Поза скоупом (extractor-leak, ctx-size, наявні 417-419) — не чіпаємо ✓.
- **Placeholders:** нема — увесь код і команди наведені дослівно.
- **Type consistency:** `JudgeUnavailable(JudgeError)` визначено в Task 2, спожито в Task 3 (import з `crawler.judge.llama`); `_MAX_BODY_CHARS` у Task 1; `_candidate_text`/`verdict`/`keep` сигнатури незмінні.
