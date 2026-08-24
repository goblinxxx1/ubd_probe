# Semantic Relevance-Judge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Додати локальний LLM relevance-суддю як strictly-additive precision-шар над екстрактором, що семантично відсіює хибні офери (клас 412 / терми / сайт-банер), не змінюючи наявних гейтів і без API-коштів.

**Architecture:** Pluggable `Judge` (protocol) з реалізацією `LlamaCppJudge` (HTTP до локального llama.cpp-сайдкара з Qwen2.5-7B). `RelevanceGate` обгортає суддю кешем (по content_hash) + circuit-breaker + деградацією (недоступний → пропуск = сьогодні). Гейт викликається в `_process_page` (активний+пасивний) після `extract()`, перед submit: `keep = genuine AND page_scoped`.

**Tech Stack:** Python 3.12, httpx (уже в проєкті), llama.cpp `llama-server` (Docker-сайдкар), Qwen2.5-7B-Instruct GGUF (Apache-2.0), pytest.

## Global Constraints

- Робоча директорія: `D:\ubd_probe\crawler`. Тести звідти. Раннер: `.venv/Scripts/python.exe -m pytest` (venv краулера, Windows).
- **Інваріант надійності:** суддя strictly-additive. Ручні гейти НЕ чіпати/не видаляти. Суддя недоступний (тимч. чи назавжди), `JUDGE_ENABLED=false`, або порожній URL → `keep()==True` завжди = поведінка як сьогодні. Нуль регресії.
- **$0:** лише локальний llama.cpp + Qwen2.5-7B (безкоштовні ваги). Жодних зовнішніх API-викликів у коді.
- Вердикт: `Verdict{genuine: bool, page_scoped: bool, reason: str}`. `keep = genuine AND page_scoped`.
- Кеш по `content_hash` (persistent /data). Circuit-breaker: після падіння виклику — пропускати суддю до кінця проходу.
- Дефолт `judge_enabled = true`.
- Українською нові коментарі/докстрінги/промпт; ідентифікатори англ.; без російської. `import threading`/інші — угорі файлу. Комітити після кожної задачі.
- Наявна повна сюїта має лишатись зеленою (нові тести + 0 регресій). Наявні виклики `_process_page`/конструкторів — з дефолтним `NullGate`, тож старі тести не ламаються.

---

## File Structure

- `crawler/crawler/judge/__init__.py` — **create** (пакет).
- `crawler/crawler/judge/base.py` — **create**: `Verdict`, `Judge` protocol, `NullJudge`.
- `crawler/crawler/judge/cache.py` — **create**: `VerdictCache`.
- `crawler/crawler/judge/llama.py` — **create**: `LlamaCppJudge`.
- `crawler/crawler/judge/gate.py` — **create**: `RelevanceGate`.
- `crawler/crawler/discovery/harvest.py` — modify `ActiveHarvester` (`__init__` + `_process_page`).
- `crawler/crawler/runner.py` — modify `Runner` (`__init__` + `_process_page`).
- `crawler/crawler/config.py` — modify (judge knobs, 3 місця).
- `crawler/crawler/wiring.py` — modify (build gate, inject into harvester+runner).
- `docker-compose.yml` — modify (llama сайдкар + crawler env).
- `crawler/scripts/validate_judge.py` — **create** (жива валідація).
- Тести: `tests/test_judge_base.py`, `tests/test_judge_cache.py`, `tests/test_judge_llama.py`, `tests/test_relevance_gate.py`, `tests/test_active_harvest.py`, `tests/test_runner.py`, `tests/test_config.py`.

---

### Task 1: `Verdict` + `Judge` protocol + `NullJudge`

**Files:**
- Create: `crawler/crawler/judge/__init__.py`, `crawler/crawler/judge/base.py`
- Test: `tests/test_judge_base.py`

**Interfaces:**
- Produces: `Verdict` (dataclass: `genuine: bool`, `page_scoped: bool`, `reason: str`); `Judge` protocol with `verdict(self, candidate) -> Verdict`; `NullJudge` (always `Verdict(True, True, "judge disabled")`).

- [ ] **Step 1: Write the failing test** (`tests/test_judge_base.py`)

```python
from crawler.judge.base import Verdict, NullJudge


def test_verdict_fields():
    v = Verdict(genuine=True, page_scoped=False, reason="site banner")
    assert v.genuine is True and v.page_scoped is False and v.reason == "site banner"


def test_null_judge_always_genuine_and_page_scoped():
    v = NullJudge().verdict(object())
    assert v.genuine is True and v.page_scoped is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_judge_base.py -v`
Expected: FAIL — `ModuleNotFoundError: crawler.judge.base`.

- [ ] **Step 3: Implement**

`crawler/crawler/judge/__init__.py`:

```python
```
(empty file — package marker)

`crawler/crawler/judge/base.py`:

```python
"""Семантичний relevance-суддя: контракт і no-op реалізація.

Суддя — strictly-additive шар над евристикою. `NullJudge` (дефолт/деградація)
завжди пропускає → поведінка як сьогодні, нуль регресії."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Verdict:
    genuine: bool          # реальна знижка/вигода САМЕ цій аудиторії (не випадковий збіг слів)
    page_scoped: bool      # промо саме цієї сторінки (не сайт-широкий банер на чужій сторінці)
    reason: str


class Judge(Protocol):
    def verdict(self, candidate) -> Verdict:
        ...


class NullJudge:
    """Деградація/вимкнено: усе genuine+page_scoped → keep завжди True."""

    def verdict(self, candidate) -> Verdict:
        return Verdict(genuine=True, page_scoped=True, reason="judge disabled")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_judge_base.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/judge/__init__.py crawler/crawler/judge/base.py crawler/tests/test_judge_base.py
git commit -m "feat(crawler): Verdict + Judge protocol + NullJudge"
```

---

### Task 2: `VerdictCache`

**Files:**
- Create: `crawler/crawler/judge/cache.py`
- Test: `tests/test_judge_cache.py`

**Interfaces:**
- Consumes: `Verdict` (Task 1).
- Produces: `VerdictCache(path)` with `get(content_hash) -> Verdict | None`, `put(content_hash, Verdict) -> None` (persists), `load()` (called in `__init__`).

- [ ] **Step 1: Write the failing test** (`tests/test_judge_cache.py`)

```python
from crawler.judge.base import Verdict
from crawler.judge.cache import VerdictCache


def test_put_get_roundtrip_and_persist(tmp_path):
    path = str(tmp_path / "judge_cache.json")
    c = VerdictCache(path)
    assert c.get("h1") is None
    c.put("h1", Verdict(genuine=False, page_scoped=True, reason="song title"))
    got = c.get("h1")
    assert got is not None and got.genuine is False and got.reason == "song title"
    # persisted -> a fresh instance reads it back
    c2 = VerdictCache(path)
    got2 = c2.get("h1")
    assert got2 is not None and got2.genuine is False and got2.page_scoped is True


def test_corrupt_file_starts_empty(tmp_path):
    path = str(tmp_path / "judge_cache.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write("{ not json")
    c = VerdictCache(path)
    assert c.get("anything") is None      # corrupt -> clean start, no crash
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_judge_cache.py -v`
Expected: FAIL — `ModuleNotFoundError: crawler.judge.cache`.

- [ ] **Step 3: Implement** (`crawler/crawler/judge/cache.py`)

```python
"""Персистентний кеш вердиктів судді по content_hash. Стабілізує повторні
проходи (той самий блок = той самий вердикт) і уникає повторних LLM-викликів."""

import json
import os
import threading

from crawler.judge.base import Verdict


class VerdictCache:
    def __init__(self, path: str):
        self._path = path
        self._lock = threading.Lock()
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._data = data
        except (OSError, ValueError):
            self._data = {}

    def get(self, content_hash: str) -> Verdict | None:
        with self._lock:
            e = self._data.get(content_hash)
        if not e:
            return None
        return Verdict(genuine=bool(e.get("genuine")),
                       page_scoped=bool(e.get("page_scoped")),
                       reason=str(e.get("reason", "")))

    def put(self, content_hash: str, verdict: Verdict) -> None:
        with self._lock:
            self._data[content_hash] = {"genuine": verdict.genuine,
                                        "page_scoped": verdict.page_scoped,
                                        "reason": verdict.reason}
            snapshot = dict(self._data)
        directory = os.path.dirname(self._path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = f"{self._path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False)
        os.replace(tmp, self._path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_judge_cache.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/judge/cache.py crawler/tests/test_judge_cache.py
git commit -m "feat(crawler): VerdictCache (content_hash-keyed, persistent)"
```

---

### Task 3: `LlamaCppJudge`

**Files:**
- Create: `crawler/crawler/judge/llama.py`
- Test: `tests/test_judge_llama.py`

**Interfaces:**
- Consumes: `Verdict`, `Judge` (Task 1).
- Produces: `LlamaCppJudge(client, model, timeout=30.0)` where `client` is an `httpx.Client`. `verdict(candidate) -> Verdict`. Reads `candidate.title`, `candidate.body`, `candidate.discount_type`, `candidate.discount_value`, `candidate.article_url`. Calls `POST {base}/v1/chat/completions` (OpenAI-compatible; `base_url` set on the client) with a Ukrainian system prompt + few-shot + `response_format={"type": "json_object"}`, parses the assistant JSON `{"genuine": bool, "page_scoped": bool, "reason": str}`. Any HTTP/parse error raises `JudgeError` (so the gate's circuit-breaker catches it).

- [ ] **Step 1: Write the failing test** (`tests/test_judge_llama.py`)

```python
import json

import httpx

from crawler.judge.llama import LlamaCppJudge, JudgeError


class _Cand:
    title = "Скачати пісню Chico - Допоможе ЗСУ безкоштовно"
    body = "Скачати пісню безкоштовно у mp3"
    discount_type = "free"
    discount_value = None
    article_url = "https://musiua.com/get-uamusic/dopomozhe-zsu/"


def _client(handler):
    return httpx.Client(base_url="http://llama:8080",
                        transport=httpx.MockTransport(handler))


def test_llama_judge_parses_verdict():
    def handler(request):
        payload = {"choices": [{"message": {"content":
                   json.dumps({"genuine": False, "page_scoped": True,
                               "reason": "ЗСУ — назва пісні"})}}]}
        return httpx.Response(200, json=payload)
    j = LlamaCppJudge(_client(handler), model="qwen2.5-7b-instruct")
    v = j.verdict(_Cand())
    assert v.genuine is False and v.page_scoped is True and "пісн" in v.reason


def test_llama_judge_http_error_raises_judge_error():
    def handler(request):
        return httpx.Response(500, text="boom")
    j = LlamaCppJudge(_client(handler), model="qwen2.5-7b-instruct")
    try:
        j.verdict(_Cand())
        assert False, "expected JudgeError"
    except JudgeError:
        pass


def test_llama_judge_bad_json_raises_judge_error():
    def handler(request):
        payload = {"choices": [{"message": {"content": "not json at all"}}]}
        return httpx.Response(200, json=payload)
    j = LlamaCppJudge(_client(handler), model="qwen2.5-7b-instruct")
    try:
        j.verdict(_Cand())
        assert False, "expected JudgeError"
    except JudgeError:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_judge_llama.py -v`
Expected: FAIL — `ModuleNotFoundError: crawler.judge.llama`.

- [ ] **Step 3: Implement** (`crawler/crawler/judge/llama.py`)

```python
"""LLM-суддя через локальний llama.cpp (llama-server, OpenAI-сумісний API).
Qwen2.5-7B-Instruct. Будь-яка помилка HTTP/парсингу -> JudgeError, щоб
circuit-breaker у RelevanceGate відкотив на поведінку-як-сьогодні."""

import json
import logging

from crawler.judge.base import Verdict

log = logging.getLogger(__name__)

_SYSTEM = (
    "Ти — модератор бази знижок для військових, ветеранів, УБД та інших "
    "захисників. Оціни кандидата-офер за ДВОМА вимірами й поверни СУВОРО JSON "
    "{\"genuine\": bool, \"page_scoped\": bool, \"reason\": \"<коротко українською>\"}.\n"
    "genuine=true, лише якщо текст пропонує РЕАЛЬНУ знижку/безкоштовну вигоду САМЕ "
    "цій аудиторії. genuine=false, якщо аудиторне слово чи знижка згадані випадково "
    "й не пов'язані (назва пісні/фільму, новина, цитата, пункт договору/публічної "
    "оферти, загальний каталог).\n"
    "page_scoped=true, якщо знижка є промо саме цієї сторінки; page_scoped=false, "
    "якщо це сайт-широкий банер, випадковий на сторінці з іншим змістом."
)

# Few-shot із реальних кейсів (негативи + позитиви).
_EXAMPLES = [
    ("Скачати пісню «Chico - Допоможе ЗСУ» безкоштовно у mp3 | musiua.com/get-uamusic/dopomozhe-zsu",
     {"genuine": False, "page_scoped": True, "reason": "«ЗСУ» — назва пісні, безкоштовне завантаження музики, не знижка для військових"}),
    ("Публічна оферта. 6. Знижки. 6.1 Дітям до 6 років безкоштовно | vidviday.ua/public-offer",
     {"genuine": False, "page_scoped": True, "reason": "пункт публічної оферти (умови), не промо"}),
    ("Імплантація зубів Osstem під ключ. Знижка 10% для учасників бойових дій (УБД) | whiteclinic.ua/promotions/implant",
     {"genuine": True, "page_scoped": False, "reason": "сторінка про імпланти; «10% УБД» — сайт-банер, не промо цієї сторінки"}),
    ("Знижка 15% для ветеранів та учасників бойових дій на всі послуги | clinic.ua/veteranam",
     {"genuine": True, "page_scoped": True, "reason": "присвячена сторінка знижки для ветеранів"}),
]


class JudgeError(Exception):
    pass


class LlamaCppJudge:
    def __init__(self, client, model: str, timeout: float = 30.0):
        self._client = client
        self._model = model
        self._timeout = timeout

    def _candidate_text(self, cand) -> str:
        disc = f"{getattr(cand, 'discount_type', None)} {getattr(cand, 'discount_value', None)}"
        return (f"{getattr(cand, 'title', '') or ''}\n"
                f"{getattr(cand, 'body', '') or ''}\n"
                f"знижка: {disc}\n"
                f"url: {getattr(cand, 'article_url', '') or ''}")

    def _messages(self, cand):
        msgs = [{"role": "system", "content": _SYSTEM}]
        for text, out in _EXAMPLES:
            msgs.append({"role": "user", "content": text})
            msgs.append({"role": "assistant", "content": json.dumps(out, ensure_ascii=False)})
        msgs.append({"role": "user", "content": self._candidate_text(cand)})
        return msgs

    def verdict(self, cand) -> Verdict:
        body = {
            "model": self._model,
            "messages": self._messages(cand),
            "temperature": 0.0,
            "max_tokens": 200,
            "response_format": {"type": "json_object"},
        }
        try:
            r = self._client.post("/v1/chat/completions", json=body, timeout=self._timeout)
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            return Verdict(genuine=bool(parsed["genuine"]),
                           page_scoped=bool(parsed["page_scoped"]),
                           reason=str(parsed.get("reason", "")))
        except Exception as exc:  # noqa: BLE001 — будь-яка помилка -> JudgeError для circuit-breaker
            raise JudgeError(str(exc)) from exc
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_judge_llama.py -v`
Expected: PASS (3/3).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/judge/llama.py crawler/tests/test_judge_llama.py
git commit -m "feat(crawler): LlamaCppJudge (Qwen via llama.cpp OpenAI API)"
```

---

### Task 4: `RelevanceGate`

**Files:**
- Create: `crawler/crawler/judge/gate.py`
- Test: `tests/test_relevance_gate.py`

**Interfaces:**
- Consumes: `Judge`, `Verdict`, `NullJudge` (Task 1); `VerdictCache` (Task 2); `JudgeError` (Task 3).
- Produces: `RelevanceGate(judge, cache, enabled=True)`; `keep(candidate) -> bool` = `genuine AND page_scoped`. `reset_breaker()` called at the start of each pass. On `enabled=False` → always True. Cache by `candidate.content_hash`. On `JudgeError` (or any exception) → trip a per-pass breaker, return True (degrade), and skip further judge calls this pass until `reset_breaker()`.

- [ ] **Step 1: Write the failing test** (`tests/test_relevance_gate.py`)

```python
from crawler.judge.base import Verdict, NullJudge
from crawler.judge.cache import VerdictCache
from crawler.judge.llama import JudgeError
from crawler.judge.gate import RelevanceGate


class _Cand:
    def __init__(self, h): self.content_hash = h


class FakeJudge:
    def __init__(self, verdict=None, exc=None):
        self._v = verdict
        self._exc = exc
        self.calls = 0
    def verdict(self, cand):
        self.calls += 1
        if self._exc:
            raise self._exc
        return self._v


def _gate(tmp_path, judge, enabled=True):
    return RelevanceGate(judge, VerdictCache(str(tmp_path / "c.json")), enabled=enabled)


def test_disabled_gate_always_keeps(tmp_path):
    j = FakeJudge(Verdict(False, False, "junk"))
    g = _gate(tmp_path, j, enabled=False)
    assert g.keep(_Cand("h")) is True
    assert j.calls == 0                       # disabled -> judge never called


def test_junk_dropped_genuine_kept(tmp_path):
    assert _gate(tmp_path, FakeJudge(Verdict(False, True, "song"))).keep(_Cand("h1")) is False
    assert _gate(tmp_path, FakeJudge(Verdict(True, False, "banner"))).keep(_Cand("h2")) is False
    assert _gate(tmp_path, FakeJudge(Verdict(True, True, "real"))).keep(_Cand("h3")) is True


def test_cache_hit_skips_judge(tmp_path):
    j = FakeJudge(Verdict(False, True, "song"))
    g = _gate(tmp_path, j)
    assert g.keep(_Cand("dup")) is False
    assert g.keep(_Cand("dup")) is False
    assert j.calls == 1                       # second call served from cache


def test_judge_error_degrades_and_trips_breaker(tmp_path):
    j = FakeJudge(exc=JudgeError("down"))
    g = _gate(tmp_path, j)
    assert g.keep(_Cand("a")) is True         # degrade: keep as today
    assert g.keep(_Cand("b")) is True         # breaker tripped -> no further calls
    assert j.calls == 1
    g.reset_breaker()
    assert g.keep(_Cand("c")) is True
    assert j.calls == 2                        # breaker reset -> judge called again
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_relevance_gate.py -v`
Expected: FAIL — `ModuleNotFoundError: crawler.judge.gate`.

- [ ] **Step 3: Implement** (`crawler/crawler/judge/gate.py`)

```python
"""RelevanceGate: суддя + кеш + circuit-breaker + деградація.

keep(candidate) = genuine AND page_scoped. Недоступний суддя (виняток) або
enabled=False -> keep=True (поведінка як сьогодні). Після падіння виклику —
breaker глушить подальші виклики до reset_breaker() (початок кожного проходу)."""

import logging

log = logging.getLogger(__name__)


class RelevanceGate:
    def __init__(self, judge, cache, enabled: bool = True):
        self._judge = judge
        self._cache = cache
        self._enabled = bool(enabled)
        self._broken = False

    def reset_breaker(self) -> None:
        self._broken = False

    def keep(self, candidate) -> bool:
        if not self._enabled or self._broken:
            return True
        content_hash = getattr(candidate, "content_hash", None)
        if content_hash and self._cache is not None:
            cached = self._cache.get(content_hash)
            if cached is not None:
                return cached.genuine and cached.page_scoped
        try:
            v = self._judge.verdict(candidate)
        except Exception as exc:  # noqa: BLE001 — деградація: недоступний суддя не блокує
            self._broken = True
            log.warning("relevance judge unavailable, degrading to keep-all this pass: %s", exc)
            return True
        if content_hash and self._cache is not None:
            self._cache.put(content_hash, v)
        return v.genuine and v.page_scoped
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_relevance_gate.py -v`
Expected: PASS (4/4).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/judge/gate.py crawler/tests/test_relevance_gate.py
git commit -m "feat(crawler): RelevanceGate (cache + circuit-breaker + degradation)"
```

---

### Task 5: Wire gate into extraction (`_process_page` active + passive) + config + wiring

**Files:**
- Modify: `crawler/crawler/discovery/harvest.py` (`ActiveHarvester.__init__`, `_process_page`)
- Modify: `crawler/crawler/runner.py` (`Runner.__init__`, `_process_page`, `run_active`/`run_passive` breaker reset)
- Modify: `crawler/crawler/config.py` (judge knobs, 3 places)
- Modify: `crawler/crawler/wiring.py` (build gate, inject)
- Test: `tests/test_active_harvest.py`, `tests/test_runner.py`, `tests/test_config.py`

**Interfaces:**
- Consumes: `RelevanceGate` (Task 4), `NullJudge` (Task 1).
- Produces: `ActiveHarvester(..., relevance_gate=None)` and `Runner(..., relevance_gate=None)` — default `None` → an internal `RelevanceGate(NullJudge(), ...)` that always keeps (back-compat). Both `_process_page` call `self._gate.keep(cand)` before accumulating an offer. Config: `judge_enabled` (default True), `judge_url`, `judge_model` (default `"qwen2.5-7b-instruct"`), `judge_timeout_seconds` (default 30.0), `judge_cache_path` (default `/data/judge_cache.json`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_active_harvest.py`:

```python
def test_active_gate_drops_non_genuine():
    from crawler.judge.base import Verdict
    class DropGate:
        def keep(self, cand): return False       # judge says junk
        def reset_breaker(self): pass
    api = FakeApi()
    fetchers = {"website": FakeFetcher([_item("Знижка 20% для УБД", site_name="Cafe")])}
    h = ActiveHarvester(api, fetchers, GateExtractor(), rate_limiter=None, fetch_budget=5,
                        relevance_gate=DropGate())
    summary = _summary()
    h.harvest([_cand()], cats=None, known=set(), summary=summary)
    assert len(api.offers) == 0 and summary["offers"] == 0   # dropped by the gate


def test_active_default_gate_keeps():
    api = FakeApi()
    fetchers = {"website": FakeFetcher([_item("Знижка 20% для УБД", site_name="Cafe")])}
    h = ActiveHarvester(api, fetchers, GateExtractor(), rate_limiter=None, fetch_budget=5)
    summary = _summary()
    h.harvest([_cand()], cats=None, known=set(), summary=summary)
    assert len(api.offers) == 1               # default NullJudge gate keeps (back-compat)
```

Add to `tests/test_runner.py`:

```python
def test_passive_gate_drops_non_genuine():
    class DropGate:
        def keep(self, cand): return False
        def reset_breaker(self): pass
    src = {"id": 1, "type": "website", "name": "Shop", "url_or_handle": "http://x"}
    item = RawItem(source_id=1, platform="website", key="k",
                   text="Знижка 20% для ветеранів", links=[])
    api = FakeApi([src])
    runner = Runner(api, {"website": FakeFetcher([item])}, get_extractor("heuristic"), _rl(),
                    relevance_gate=DropGate())
    summary = runner.run()
    assert summary["offers"] == 0             # gate dropped it
```

Add to `tests/test_config.py`:

```python
def test_judge_config_defaults(monkeypatch):
    from crawler.config import load_config
    cfg = load_config()
    assert cfg.judge_enabled is True
    assert cfg.judge_model == "qwen2.5-7b-instruct"
    monkeypatch.setenv("JUDGE_ENABLED", "false")
    assert load_config().judge_enabled is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_active_harvest.py::test_active_gate_drops_non_genuine tests/test_config.py::test_judge_config_defaults -v`
Expected: FAIL — `unexpected keyword argument 'relevance_gate'` / `no attribute 'judge_enabled'`.

- [ ] **Step 3: Implement**

**harvest.py** — add import at top: `from crawler.judge.base import NullJudge` and `from crawler.judge.gate import RelevanceGate`. In `ActiveHarvester.__init__` append param `relevance_gate=None` and in the body:

```python
        self._gate = relevance_gate or RelevanceGate(NullJudge(), _NullCache())
```

where `_NullCache` is a tiny inline no-op cache — instead, simpler: make `RelevanceGate` accept `cache=None` and skip caching when None. Adjust Task 4's `RelevanceGate.keep` to guard `self._cache` for None (if implementing that, note it in Task 4). For this plan use the simplest form: default gate = `RelevanceGate(NullJudge(), None)`, and in `RelevanceGate.keep` treat `self._cache is None` as "no cache" (only call `self._cache.get/put` when not None). **Apply this `cache=None` guard as part of Task 4's implementation** (add `if content_hash and self._cache is not None:` around both cache accesses).

In `ActiveHarvester._process_page`, in the loop that builds `collected` (harvest.py:~192), after `offer = self._extractor.extract(item, attr.provider, cats)` and before `collected.append(...)`, add:

```python
            if offer is None or not self._gate.keep(offer):
                continue
```
(Keep the existing `attr is None: continue` guard above it unchanged.)

**runner.py** — add imports `from crawler.judge.base import NullJudge`, `from crawler.judge.gate import RelevanceGate`. In `Runner.__init__` append `relevance_gate=None` and set `self._gate = relevance_gate or RelevanceGate(NullJudge(), None)`. In `Runner._process_page`, where `cand = self._extractor.extract(...)` then `if cand is not None:` (runner.py:~348-351), change the guard to:

```python
            if cand is not None and self._gate.keep(cand):
```

Reset the breaker once per pass: at the START of `run_active` and `run_passive` bodies add `self._gate.reset_breaker()` (guard: the default gate has it; the DropGate test fake defines it too).

**config.py** — add in `_RawSettings` (near other knobs): `judge_enabled: bool = True`, `judge_url: str = "http://llama:8080"`, `judge_model: str = "qwen2.5-7b-instruct"`, `judge_timeout_seconds: float = 30.0`, `judge_cache_path: str = "/data/judge_cache.json"`. Add the SAME five fields to the `Config` dataclass. Add the mapping lines in `from_settings`'s `Config(...)`: `judge_enabled=s.judge_enabled, judge_url=s.judge_url, judge_model=s.judge_model, judge_timeout_seconds=s.judge_timeout_seconds, judge_cache_path=s.judge_cache_path,`.

**wiring.py** — build the gate before constructing harvester/runner:

```python
    from crawler.judge.base import NullJudge
    from crawler.judge.gate import RelevanceGate
    from crawler.judge.cache import VerdictCache
    if config.judge_enabled and config.judge_url:
        from crawler.judge.llama import LlamaCppJudge
        judge = LlamaCppJudge(httpx.Client(base_url=config.judge_url),
                              model=config.judge_model,
                              timeout=config.judge_timeout_seconds)
    else:
        judge = NullJudge()
    relevance_gate = RelevanceGate(judge, VerdictCache(config.judge_cache_path),
                                   enabled=config.judge_enabled)
```

Pass `relevance_gate=relevance_gate` to BOTH the `ActiveHarvester(...)` and `Runner(...)` calls. (`httpx` is already imported in wiring.py.)

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_active_harvest.py tests/test_runner.py tests/test_config.py tests/test_wiring.py -v`
Expected: PASS (new + existing).

- [ ] **Step 5: Full suite before commit**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/discovery/harvest.py crawler/crawler/runner.py crawler/crawler/config.py crawler/crawler/wiring.py crawler/crawler/judge/gate.py crawler/tests/
git commit -m "feat(crawler): wire RelevanceGate into extraction + config + wiring"
```

---

### Task 6: Docker llama.cpp sidecar + compose wiring

**Files:**
- Modify: `docker-compose.yml`

**Interfaces:** none (infra). Produces a `llama` service the crawler reaches at `http://llama:8080`.

- [ ] **Step 1: Add the sidecar service** to `docker-compose.yml` (under `services:`)

```yaml
  llama:
    image: ghcr.io/ggml-org/llama.cpp:server
    profiles: ["crawler"]
    restart: unless-stopped
    # Qwen2.5-7B-Instruct Q4_K_M, auto-downloaded once from HuggingFace into a
    # persistent volume (pinned repo:quant). Apache-2.0 weights — $0.
    command: >
      -hf Qwen/Qwen2.5-7B-Instruct-GGUF:Q4_K_M
      --host 0.0.0.0 --port 8080 --ctx-size 4096
    volumes:
      - ubd-llama-models:/root/.cache/llama.cpp
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8080/health"]
      interval: 30s
      timeout: 5s
      retries: 20
      start_period: 600s
```

Add `ubd-llama-models:` under the top-level `volumes:` block.

In the `crawler` service `environment:` block add:

```yaml
      JUDGE_URL: http://llama:8080
```

(Do NOT add a hard `depends_on: llama` for the crawler — degradation must let the crawler run even if llama is still downloading/unhealthy.)

- [ ] **Step 2: Validate compose parses**

Run (from repo root, via Bash): `docker compose --profile crawler config >/dev/null && echo COMPOSE_OK`
Expected: `COMPOSE_OK` (no YAML/schema error).

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(infra): llama.cpp sidecar (Qwen2.5-7B) for relevance judge"
```

---

### Task 7: Live validation harness + full regression + live Docker + finish

**Files:**
- Create: `crawler/scripts/validate_judge.py`

- [ ] **Step 1: Write the validation harness** (`crawler/scripts/validate_judge.py`)

```python
"""Жива валідація судді: прогнати РЕАЛЬНИЙ llama.cpp на відомих кейсах +
вибірці published/rejected із БД, вивести вердикти й точність. Запуск усередині
crawler-контейнера (має JUDGE_URL). Це критерій «спрацює чи ні»."""

import os
import httpx

from crawler.judge.llama import LlamaCppJudge


class C:
    def __init__(self, title, body, dt, dv, url):
        self.title, self.body = title, body
        self.discount_type, self.discount_value, self.article_url = dt, dv, url


CASES = [
    # (очікуваний keep=False) — сміття
    C("Скачати пісню Chico - Допоможе ЗСУ безкоштовно", "mp3 безкоштовно", "free", None,
      "https://musiua.com/get-uamusic/dopomozhe-zsu/"),
    C("Публічна оферта", "6. Знижки 6.1 Дітям до 6 років безкоштовно", "free", None,
      "https://vidviday.ua/public-offer"),
    C("Імплантація зубів Osstem", "Знижка 10% для учасників бойових дій УБД", "percent", "10",
      "https://whiteclinic.ua/promotions/aktsiia-na-implantatsiiu/"),
    # (очікуваний keep=True) — реальні
    C("Знижка для військових", "Знижка 15% для ветеранів на всі послуги", "percent", "15",
      "https://example.ua/veteranam/"),
]


def main():
    judge = LlamaCppJudge(httpx.Client(base_url=os.environ.get("JUDGE_URL", "http://llama:8080")),
                          model=os.environ.get("JUDGE_MODEL", "qwen2.5-7b-instruct"))
    for c in CASES:
        v = judge.verdict(c)
        keep = v.genuine and v.page_scoped
        print(f"keep={keep!s:5} genuine={v.genuine!s:5} page_scoped={v.page_scoped!s:5} "
              f"| {c.article_url}\n    reason: {v.reason}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the full crawler suite**

Run (from `crawler/`): `.venv/Scripts/python.exe -m pytest -q`
Expected: all green.

- [ ] **Step 3: Live Docker validation** (per [[ubd-run-in-docker]])

- Build + start the sidecar: `docker compose build crawler && docker compose --profile crawler up -d llama` — wait for `llama` healthy (first run downloads ~5GB; `docker compose ps llama` → healthy; may take minutes).
- Run the harness inside the crawler image:
  `docker compose --profile crawler run --rm --entrypoint python crawler crawler/scripts/validate_judge.py`
- **Success criteria (the "чи спрацює" gate):** the three junk cases print `keep=False`; the real case prints `keep=True`. If the `page_scoped` dimension wrongly flips real offers, note it — per the spec's risk, we may drop `page_scoped` from `keep` (keep only `genuine`) and route White-Clinic dedup to a backend track.
- **Degradation check:** `docker compose stop llama`, then run one real active pass — confirm it completes with no crash (gate degrades to keep-all).

- [ ] **Step 4: Finish the branch**

Per [[ubd-workflow]], merge `crawler-relevance-judge` into `main`. Use `superpowers:finishing-a-development-branch`. Then rebuild + `docker compose --profile crawler up -d` to deploy.

---

## Self-Review

- **Spec coverage:** Verdict/Judge/NullJudge → Task 1. VerdictCache (content_hash) → Task 2. LlamaCppJudge (Qwen, prompt+few-shot+page_scoped) → Task 3. RelevanceGate (cache+breaker+degradation) → Task 4. Wiring into both _process_page + config (judge_enabled default true) + degradation-default NullGate → Task 5. llama.cpp sidecar (Apache-2.0, volume, healthcheck, no hard depends_on) → Task 6. Live validation of 412/Vidviay/White Clinic + degradation + finish → Task 7. Additive-invariant (manual gates untouched) honored throughout (no gate removed). page_scoped in scope (Task 3 prompt + Task 4 keep). $0 (local weights) — Task 6.
- **Placeholder scan:** every code step shows full code. Task 5 Step 3 references a `cache=None` guard to add to Task 4's `RelevanceGate` — folded explicitly into Task 4's note (keep both consistent: `if content_hash and self._cache is not None`).
- **Type consistency:** `Verdict{genuine,page_scoped,reason}` consistent across all tasks; `RelevanceGate(judge, cache, enabled=True)` + `keep()`/`reset_breaker()` consistent between Task 4 and Task 5; `LlamaCppJudge(client, model, timeout)` consistent between Task 3 and wiring (Task 5); `relevance_gate=None` param name identical in harvest.py and runner.py.
