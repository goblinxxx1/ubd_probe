# Promo-Lexicon Autofill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Замінити статичний промо/relevance-словник самонавчальним конвеєром: єдиний `promo_lexicon` (seed+learned), labeler на детермінованих гейтах+якорях, корпус PASS/FAIL, snowball з прийнятих оферів, офлайн log-odds майнер, вето й audit CLI — детермінований core цілий, навчання офлайн, вихід→людський аудит.

**Architecture:** Живий гейт екстракції лишається regex-стем (детермінований). Кожен прогін пише корпус міток; майнер офлайн рахує weighted log-odds PASS↔FAIL, пропускає кандидатів крізь вето (multi-domain / PASS-collision / abstention) у чергу; людина `audit approve` дописує терм у LEARNED-дата-файл (у репо порожній), звідки його підхоплює живий гейт.

**Tech Stack:** Python 3.11, pytest, httpx, selectolax; pymorphy3 + pymorphy3-dicts-uk (офлайн-лематизація, версія запінена); FastAPI/SQLAlchemy (backend snowball-ендпоінт).

## Global Constraints

- Детермінований core екстракції: живий матчинг лишається regex word-start стем (як `discovery/lexicon.py`/`geo.py`); лематизатор — ТІЛЬКИ в офлайн-майнері.
- LEARNED-дата-файл (`promo_lexicon_learned.json`) у репо ПОРОЖНІЙ → наявні 269 crawler-тестів не змінюють поведінку.
- Жодної авто-публікації термів: вихід майнера untrusted → лише людський `audit approve` вводить терм у живий гейт.
- Нові конфіг-поля йдуть і в `_RawSettings`, і в `Config` dataclass, і в `load_config()` (три місця, `crawler/crawler/config.py`).
- Локальні стори — файли через `*_path`-конфіг (як `brand_domains_path`), дефолт-префікс `/data/`.
- pymorphy3 + pymorphy3-dicts-uk у `requirements.txt` з піном точної версії.
- Тести крос-модульні без мережі: майнер/вето/labeler працюють на fixture-даних.
- `miner_min_domain_support` (N) дефолт = 3.
- Стиль: короткі докстрінги-призначення, snake_case, як у наявному коді краулера.

---

### Task 1: Модуль `promo_lexicon` (SEED == поточні токени, LEARNED-плумбінг)

Створити єдиний source-of-truth, поки що з ТОЧНО тими самими токенами, що зараз розкидані (рефактор без зміни поведінки). LEARNED-механізм є, але порожній.

**Files:**
- Create: `crawler/crawler/discovery/promo_lexicon.py`
- Test: `crawler/tests/test_promo_lexicon.py`

**Interfaces:**
- Produces:
  - `SEED_OFFER_TRIGGERS: tuple[str, ...]` — стеми-тригери «це оффер».
  - `SEED_URL_TOKENS: tuple[str, ...]` — трансліт-токени для URL-шляху.
  - `DISCOUNT_CTX: re.Pattern`, `FREE: re.Pattern`, `INCREASE: re.Pattern`.
  - `reload_learned(path: str | None) -> None` — (пере)завантажує LEARNED зі списку JSON `[{"term": str, ...}]`; відсутній файл/None → порожньо.
  - `offer_triggers() -> tuple[str, ...]` — `SEED_OFFER_TRIGGERS + <learned terms>`.
  - `url_is_promo(url: str) -> bool` — токен у percent-decoded lowercase шляху.

- [ ] **Step 1: Написати тест, що падає**

```python
# crawler/tests/test_promo_lexicon.py
import json
from crawler.discovery import promo_lexicon as pl


def test_seed_offer_triggers_match_current_gate():
    # ті самі 7 стемів, що були в heuristic._OFFER_TRIGGERS
    for stem in ("знижк", "акці", "промокод", "безкоштов", "безплатн", "діє до",
                 "спецпропоз", "розпродаж"):
        assert stem in pl.SEED_OFFER_TRIGGERS


def test_url_is_promo_matches_tokens():
    assert pl.url_is_promo("https://shop.ua/sale/winter")
    assert pl.url_is_promo("https://shop.ua/%D0%B0%D0%BA%D1%86%D1%96%D1%97")  # акції
    assert not pl.url_is_promo("https://shop.ua/about")


def test_learned_terms_augment_offer_triggers(tmp_path):
    pl.reload_learned(None)
    assert "уцінк" not in pl.offer_triggers()
    f = tmp_path / "learned.json"
    f.write_text(json.dumps([{"term": "уцінк"}]), encoding="utf-8")
    pl.reload_learned(str(f))
    assert "уцінк" in pl.offer_triggers()
    pl.reload_learned(None)  # reset for other tests
    assert "уцінк" not in pl.offer_triggers()
```

- [ ] **Step 2: Запустити — має впасти**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_promo_lexicon.py -v`
Expected: FAIL — `ModuleNotFoundError: crawler.discovery.promo_lexicon`.

- [ ] **Step 3: Реалізувати модуль**

```python
# crawler/crawler/discovery/promo_lexicon.py
"""Єдиний source-of-truth промо/relevance-словника: курований SEED + навчений
LEARNED (у репо порожній, наповнюється audit CLI). Живий матчинг — regex word-start
стем, детермінований (як geo.py/lexicon.py)."""

import json
import re
from urllib.parse import unquote, urlsplit

# --- SEED: точна копія теперішніх розкиданих токенів (без розширення на цьому кроці) ---
SEED_OFFER_TRIGGERS: tuple[str, ...] = (
    "знижк", "акці", "промокод", "безкоштов", "безплатн", "діє до",
    "спецпропоз", "розпродаж",
)
SEED_URL_TOKENS: tuple[str, ...] = (  # ТОЧНА копія walker._PROMO_URL_TOKENS (26)
    "sale", "promo", "akci", "akcii", "aktsi", "znizhk", "znyzhk", "rozprodazh",
    "discount", "discounts", "offer", "offers", "deal", "deals", "black-friday",
    "blackfriday", "specialpropoz", "spec-propoz", "cyber-monday",
    "акці", "акция", "знижк", "розпродаж", "спецпропоз", "дисконт", "вигід",
)

DISCOUNT_CTX = re.compile(
    r"знижк|акці|розпродаж|спецпропоз|промокод|економ|вигід|-\s*\d", re.IGNORECASE)
FREE = re.compile(r"безкоштов|безплатн|\bfree\b", re.IGNORECASE)
INCREASE = re.compile(
    r"зростан|подорожч|підвищенн\w*\s+варт|дорожч|буде\s+[\d\s]+грн", re.IGNORECASE)

_learned_terms: tuple[str, ...] = ()


def reload_learned(path: str | None) -> None:
    global _learned_terms
    if not path:
        _learned_terms = ()
        return
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        _learned_terms = tuple(
            e["term"] for e in data if isinstance(e, dict) and e.get("term"))
    except (OSError, ValueError, KeyError, TypeError):
        _learned_terms = ()


def offer_triggers() -> tuple[str, ...]:
    return SEED_OFFER_TRIGGERS + _learned_terms


def url_is_promo(url: str) -> bool:  # семантика як у walker.url_is_promo
    path = unquote(urlsplit(url or "").path).lower()
    return any(tok in path for tok in SEED_URL_TOKENS)
```

- [ ] **Step 4: Запустити — має пройти**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_promo_lexicon.py -v`
Expected: PASS (усі 3).

- [ ] **Step 5: Коміт**

```bash
git add crawler/crawler/discovery/promo_lexicon.py crawler/tests/test_promo_lexicon.py
git commit -m "feat(crawler): promo_lexicon module (seed==current tokens + learned plumbing)"
```

---

### Task 2: Перевести `heuristic.py` і `walker.py` на `promo_lexicon` (без зміни поведінки)

**Files:**
- Modify: `crawler/crawler/extract/heuristic.py:30-38` (прибрати локальні `_OFFER_TRIGGERS`, `_DISCOUNT_CTX`, `_FREE`, `_INCREASE`; використати `promo_lexicon`)
- Modify: `crawler/crawler/discovery/walker.py:16-29` (прибрати локальні `_PROMO_URL_TOKENS`, `url_is_promo`; делегувати в `promo_lexicon`)
- Test: наявні `crawler/tests/test_heuristic.py`, `test_promo_url_filter.py`, `test_walker.py` (регрес).

**Interfaces:**
- Consumes: `promo_lexicon.offer_triggers()`, `.DISCOUNT_CTX`, `.FREE`, `.INCREASE`, `.url_is_promo`.

- [ ] **Step 1: Переписати heuristic-гейт на модуль**

У `crawler/crawler/extract/heuristic.py` прибрати рядки 30–38 (`_OFFER_TRIGGERS`, `_PERCENT` лишити, `_FIXED` лишити, `_FREE`, `_DISCOUNT_CTX`, `_INCREASE` — перенести на модуль) і додати імпорт:

```python
from crawler.discovery import promo_lexicon as pl
```

Замінити тіло гейта в `extract` (було рядки 63–65):

```python
        if not any(t in low for t in pl.offer_triggers()):
            return None
        if pl.INCREASE.search(low) and not pl.DISCOUNT_CTX.search(low):
            return None
```

І у визначенні discount_type замінити `_FREE`→`pl.FREE`, `_DISCOUNT_CTX`→`pl.DISCOUNT_CTX` (рядки 70–73). `_PERCENT`/`_FIXED` лишаються локальними.

- [ ] **Step 2: Переписати walker URL-фільтр на модуль**

У `crawler/crawler/discovery/walker.py` прибрати `_PROMO_URL_TOKENS` (рядки 18–24) і тіло `url_is_promo` (рядки 26–29), замінивши на делегування:

```python
from crawler.discovery.promo_lexicon import url_is_promo  # re-export for callers
```

(Рядок `promo = [u for u in found if _same_domain(u, domain) and url_is_promo(u)]` лишається робочим через re-export.)

- [ ] **Step 3: Запустити регрес — усе зелене**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_heuristic.py tests/test_promo_url_filter.py tests/test_walker.py -v`
Expected: PASS (усі наявні — поведінка збережена).

- [ ] **Step 4: Повний прогін краулер-тестів**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS (269 як було).

- [ ] **Step 5: Коміт**

```bash
git add crawler/crawler/extract/heuristic.py crawler/crawler/discovery/walker.py
git commit -m "refactor(crawler): source promo tokens from promo_lexicon (no behaviour change)"
```

---

### Task 3: Розширити SEED куруваними промо-термами

Тепер додаємо recall. Кожен новий стем — з тестом-прикладом; повний краулер-сют лишається зеленим.

**Files:**
- Modify: `crawler/crawler/discovery/promo_lexicon.py` (`SEED_OFFER_TRIGGERS`, `SEED_URL_TOKENS`)
- Test: `crawler/tests/test_promo_lexicon.py`

- [ ] **Step 1: Тест, що падає**

```python
def test_expanded_offer_triggers_present():
    for stem in ("уцінк", "ліквідац", "бонус", "кешбек", "подарунок",
                 "тільки сьогодні", "супер ціна", "гаряч пропозиц",
                 "друга за пів ціни", "спеціальна ціна"):
        assert stem in pl.SEED_OFFER_TRIGGERS


def test_new_trigger_makes_offer_recognisable():
    from crawler.extract.base import CategoryIndex, get_extractor
    from crawler.models import RawItem
    cats = CategoryIndex(target=[{"id": 10, "name": "Ветеран", "slug": "veteran"}], offer=[])
    ex = get_extractor("heuristic")
    item = RawItem(source_id=1, platform="website", key="k",
                   text="Уцінка на зимову колекцію для ветеранів")
    assert ex.extract(item, "Shop", cats) is not None
```

- [ ] **Step 2: Запустити — падає**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_promo_lexicon.py::test_expanded_offer_triggers_present tests/test_promo_lexicon.py::test_new_trigger_makes_offer_recognisable -v`
Expected: FAIL (`assert 'уцінк' in ...`).

- [ ] **Step 3: Розширити SEED**

У `promo_lexicon.py` доповнити кортежі (зберігаючи наявні):

```python
SEED_OFFER_TRIGGERS = (
    # --- ядро (як було) ---
    "знижк", "акці", "промокод", "безкоштов", "безплатн", "діє до",
    "спецпропоз", "розпродаж",
    # --- розширення (курований маркетинг-лексикон) ---
    "уцінк", "ліквідац", "бонус", "кешбек", "подарунок", "тільки сьогодні",
    "супер ціна", "супер-ціна", "гаряч пропозиц", "друга за пів ціни",
    "спеціальна ціна", "спец ціна", "вигідна пропозиц", "знижен",
)
SEED_URL_TOKENS = (
    # --- ядро (ТОЧНО як у walker, 26) ---
    "sale", "promo", "akci", "akcii", "aktsi", "znizhk", "znyzhk", "rozprodazh",
    "discount", "discounts", "offer", "offers", "deal", "deals", "black-friday",
    "blackfriday", "specialpropoz", "spec-propoz", "cyber-monday",
    "акці", "акция", "знижк", "розпродаж", "спецпропоз", "дисконт", "вигід",
    # --- розширення ---
    "utsinka", "bonus", "cashback", "special", "specialna", "spec-cina", "hot",
)
```

- [ ] **Step 4: Запустити нові + повний сют**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS (269 наявних + нові; жоден наявний не зламався).

- [ ] **Step 5: Коміт**

```bash
git add crawler/crawler/discovery/promo_lexicon.py crawler/tests/test_promo_lexicon.py
git commit -m "feat(crawler): expand curated promo lexicon (recall)"
```

---

### Task 4: Конфіг-кнопки автонаповнення

**Files:**
- Modify: `crawler/crawler/config.py` (`_RawSettings`, `Config`, `load_config`)
- Test: `crawler/tests/test_config_autofill.py` (Create)

**Interfaces:**
- Produces (на `Config`): `corpus_path: str`, `corpus_max_mb: float`, `promo_lexicon_learned_path: str`, `snowball_state_path: str`, `autofill_enabled: bool`, `miner_min_domain_support: int`, `miner_min_logodds: float`, `miner_max_candidates_per_run: int`.

- [ ] **Step 1: Тест, що падає**

```python
# crawler/tests/test_config_autofill.py
from crawler.config import Config


def test_config_has_autofill_defaults():
    c = Config(internal_api_url="x", crawler_api_key="k", extractor="heuristic",
               active_discovery=False, request_timeout=1.0, min_delay_seconds=1.0)
    assert c.promo_lexicon_learned_path.endswith("promo_lexicon_learned.json")
    assert c.miner_min_domain_support == 3
    assert c.autofill_enabled is False
    assert c.corpus_max_mb > 0
```

- [ ] **Step 2: Запустити — падає**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_config_autofill.py -v`
Expected: FAIL (`AttributeError`/`TypeError`).

- [ ] **Step 3: Додати поля в три місця**

У `_RawSettings` (після рядка 51):

```python
    corpus_path: str = "/data/corpus.jsonl"
    corpus_max_mb: float = 50.0
    promo_lexicon_learned_path: str = "/data/promo_lexicon_learned.json"
    snowball_state_path: str = "/data/snowball_state.json"
    autofill_enabled: bool = False
    miner_min_domain_support: int = 3
    miner_min_logodds: float = 1.5
    miner_max_candidates_per_run: int = 50
```

У `Config` dataclass (після рядка 95) ті самі поля з тими самими дефолтами. У `load_config()` (перед закриттям `)` на рядку 162) додати їх передачу:

```python
        corpus_path=s.corpus_path,
        corpus_max_mb=s.corpus_max_mb,
        promo_lexicon_learned_path=s.promo_lexicon_learned_path,
        snowball_state_path=s.snowball_state_path,
        autofill_enabled=s.autofill_enabled,
        miner_min_domain_support=s.miner_min_domain_support,
        miner_min_logodds=s.miner_min_logodds,
        miner_max_candidates_per_run=s.miner_max_candidates_per_run,
```

- [ ] **Step 4: Запустити — пройде**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_config_autofill.py -q`
Expected: PASS.

- [ ] **Step 5: Коміт**

```bash
git add crawler/crawler/config.py crawler/tests/test_config_autofill.py
git commit -m "feat(crawler): autofill config knobs"
```

---

### Task 5: Позитивний якір — `RawItem.has_offer_schema` + WebsiteFetcher

**Files:**
- Modify: `crawler/crawler/models.py:13-23` (додати поле)
- Modify: `crawler/crawler/fetchers/website.py` (детекція schema.org `Offer`, проставити прапорець)
- Test: `crawler/tests/test_website_fetcher.py` (додати кейс)

**Interfaces:**
- Produces: `RawItem.has_offer_schema: bool = False`.

- [ ] **Step 1: Тест, що падає**

```python
# додати у crawler/tests/test_website_fetcher.py
def test_offer_schema_flag_set(monkeypatch):
    from crawler.fetchers.website import WebsiteFetcher
    html = ('<html><body><article>'
            'Знижка 20% для ветеранів у кафе на розі, діє до 31.12'
            '<script type="application/ld+json">'
            '{"@type":"Offer","price":"100"}</script>'
            '</article></body></html>')

    class _Resp:
        text = html
        def raise_for_status(self): pass

    class _Client:
        def get(self, url, follow_redirects=True): return _Resp()

    items, _ = WebsiteFetcher(_Client()).fetch(
        {"id": 1, "url_or_handle": "http://shop.ua"}, None)
    assert items and items[0].has_offer_schema is True
```

- [ ] **Step 2: Запустити — падає**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_website_fetcher.py::test_offer_schema_flag_set -v`
Expected: FAIL (`AttributeError: has_offer_schema`).

- [ ] **Step 3: Реалізувати**

У `crawler/crawler/models.py` в `RawItem` додати поле (після `locality`):

```python
    has_offer_schema: bool = False
```

У `crawler/crawler/fetchers/website.py` додати хелпер і проставляння. Після `_extract_locality` додати:

```python
def _has_offer_schema(tree) -> bool:
    for node in tree.css('script[type="application/ld+json"]'):
        raw = node.text() or ""
        if '"offer"' in raw.lower():
            return True
    return False
```

У `fetch`, після `locality = _extract_locality(tree)` (рядок 127):

```python
            has_offer = _has_offer_schema(tree)
```

і у конструкторі `RawItem(...)` (рядки 142–145) додати `has_offer_schema=has_offer`.

- [ ] **Step 4: Запустити — пройде (+ повний сют)**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_website_fetcher.py -q`
Expected: PASS.

- [ ] **Step 5: Коміт**

```bash
git add crawler/crawler/models.py crawler/crawler/fetchers/website.py crawler/tests/test_website_fetcher.py
git commit -m "feat(crawler): positive anchor — RawItem.has_offer_schema from JSON-LD Offer"
```

---

### Task 6: `learn/labeler.py` — мітка + якорі

**Files:**
- Create: `crawler/crawler/learn/__init__.py` (порожній)
- Create: `crawler/crawler/learn/labeler.py`
- Test: `crawler/tests/test_labeler.py`

**Interfaces:**
- Produces: `label_item(item, extracted_is_offer: bool) -> LabelRecord` де
  `LabelRecord(label: str, host: str, neg_anchor: bool, pos_anchor: bool)`;
  `label` = `"pass"` якщо `extracted_is_offer` інакше `"fail"`.

- [ ] **Step 1: Тест, що падає**

```python
# crawler/tests/test_labeler.py
from crawler.learn.labeler import label_item
from crawler.models import RawItem


def _item(url, has_schema=False):
    return RawItem(source_id=1, platform="website", key="k",
                   text="Знижка 20%", url=url, has_offer_schema=has_schema)


def test_pass_label_and_positive_anchor():
    rec = label_item(_item("https://shop.ua/sale", has_schema=True), True)
    assert rec.label == "pass"
    assert rec.host == "shop.ua"
    assert rec.pos_anchor is True
    assert rec.neg_anchor is False


def test_negative_anchor_from_blocklist():
    rec = label_item(_item("https://nv.ua/news"), False)
    assert rec.label == "fail"
    assert rec.neg_anchor is True
```

- [ ] **Step 2: Запустити — падає**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_labeler.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Реалізувати**

```python
# crawler/crawler/learn/labeler.py
"""Детермінований labeler: мітка PASS/FAIL з гейта екстракції + якорі
(negative = blocklist-host, positive = schema.org Offer)."""

from dataclasses import dataclass
from urllib.parse import urlsplit

from crawler.discovery.blocklist import is_blocked_host


@dataclass
class LabelRecord:
    label: str          # "pass" | "fail"
    host: str
    neg_anchor: bool
    pos_anchor: bool


def _host(url: str | None) -> str:
    return urlsplit(url or "").netloc.lower().removeprefix("www.")


def label_item(item, extracted_is_offer: bool) -> LabelRecord:
    host = _host(getattr(item, "url", None))
    return LabelRecord(
        label="pass" if extracted_is_offer else "fail",
        host=host,
        neg_anchor=is_blocked_host(host),
        pos_anchor=bool(getattr(item, "has_offer_schema", False)),
    )
```

- [ ] **Step 4: Запустити — пройде**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_labeler.py -q`
Expected: PASS.

- [ ] **Step 5: Коміт**

```bash
git add crawler/crawler/learn/__init__.py crawler/crawler/learn/labeler.py crawler/tests/test_labeler.py
git commit -m "feat(crawler): learn/labeler — deterministic label + anchors"
```

---

### Task 7: `learn/corpus.py` — `CorpusRecorder` (JSONL + ротація)

**Files:**
- Create: `crawler/crawler/learn/corpus.py`
- Test: `crawler/tests/test_corpus.py`

**Interfaces:**
- Produces:
  - `CorpusRecorder(path: str, max_mb: float)`; метод `record(item, extracted_is_offer: bool, *, snowball: bool = False) -> None` пише рядок JSONL `{text, label, host, neg_anchor, pos_anchor, snowball, ts}`.
  - `read_corpus(path: str) -> list[dict]` — читач для майнера/тестів.

- [ ] **Step 1: Тест, що падає**

```python
# crawler/tests/test_corpus.py
from crawler.learn.corpus import CorpusRecorder, read_corpus
from crawler.models import RawItem


def _item(text, url="https://shop.ua/sale"):
    return RawItem(source_id=1, platform="website", key="k", text=text, url=url)


def test_record_appends_jsonl(tmp_path):
    p = tmp_path / "corpus.jsonl"
    rec = CorpusRecorder(str(p), max_mb=10)
    rec.record(_item("Знижка 20%"), True)
    rec.record(_item("Просто новина", url="https://nv.ua/x"), False)
    rows = read_corpus(str(p))
    assert len(rows) == 2
    assert rows[0]["label"] == "pass" and rows[0]["host"] == "shop.ua"
    assert rows[1]["label"] == "fail"


def test_rotation_trims_oldest(tmp_path):
    p = tmp_path / "corpus.jsonl"
    rec = CorpusRecorder(str(p), max_mb=0.0001)  # ~100 bytes
    for i in range(200):
        rec.record(_item(f"Знижка номер {i} " * 3), True)
    size_mb = p.stat().st_size / (1024 * 1024)
    assert size_mb <= 0.0002  # ротація тримає розмір біля межі
    assert len(read_corpus(str(p))) >= 1
```

- [ ] **Step 2: Запустити — падає**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_corpus.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Реалізувати**

```python
# crawler/crawler/learn/corpus.py
"""JSONL-стор корпусу міток PASS/FAIL для офлайн-майнера. Append + ротація за розміром."""

import json
import os
import time

from crawler.learn.labeler import label_item


class CorpusRecorder:
    def __init__(self, path: str, max_mb: float):
        self._path = path
        self._max_bytes = int(max_mb * 1024 * 1024)

    def record(self, item, extracted_is_offer: bool, *, snowball: bool = False) -> None:
        rec = label_item(item, extracted_is_offer)
        row = {
            "text": getattr(item, "text", "") or "",
            "label": rec.label, "host": rec.host,
            "neg_anchor": rec.neg_anchor, "pos_anchor": rec.pos_anchor,
            "snowball": snowball, "ts": int(time.time()),
        }
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        with open(self._path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._rotate()

    def _rotate(self) -> None:
        try:
            if os.path.getsize(self._path) <= self._max_bytes:
                return
            with open(self._path, encoding="utf-8") as fh:
                lines = fh.readlines()
        except OSError:
            return
        # прибрати найстаріші, поки не влізе (лишити хоч 1 рядок)
        while len(lines) > 1 and sum(len(x.encode()) for x in lines) > self._max_bytes:
            lines.pop(0)
        with open(self._path, "w", encoding="utf-8") as fh:
            fh.writelines(lines)


def read_corpus(path: str) -> list[dict]:
    rows = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    except OSError:
        return []
    return rows
```

- [ ] **Step 4: Запустити — пройде**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_corpus.py -q`
Expected: PASS.

- [ ] **Step 5: Коміт**

```bash
git add crawler/crawler/learn/corpus.py crawler/tests/test_corpus.py
git commit -m "feat(crawler): learn/corpus — CorpusRecorder (JSONL + rotation)"
```

---

### Task 8: Вклинити `CorpusRecorder` у конвеєр (`runner.py` + `harvest.py`)

**Files:**
- Modify: `crawler/crawler/runner.py` (`__init__` приймає `corpus_recorder=None`; писати мітку в `_crawl_source`)
- Modify: `crawler/crawler/discovery/harvest.py` (`__init__` приймає `corpus_recorder=None`; писати мітку в `_process_page`)
- Test: `crawler/tests/test_corpus_wiring.py`

**Interfaces:**
- Consumes: `CorpusRecorder.record(item, is_offer)`.

- [ ] **Step 1: Тест, що падає**

```python
# crawler/tests/test_corpus_wiring.py
from crawler.runner import Runner
from crawler.models import RawItem


class _Rec:
    def __init__(self): self.calls = []
    def record(self, item, is_offer, **kw): self.calls.append((item.text, is_offer))


class _Api:
    def list_target_categories(self): return []
    def list_offer_categories(self): return []
    def list_sources(self, is_active=True):
        return [{"id": 1, "type": "website", "name": "Shop", "url_or_handle": "http://x"}]
    def get_crawl_state(self, sid): return {"last_seen_key": None}
    def set_crawl_state(self, sid, key): pass
    def submit_offer(self, p): pass
    def submit_suggestion(self, p): pass
    def expire_stale(self, d): return {"expired": 0}


class _Fetcher:
    def fetch(self, source, key):
        return [RawItem(source_id=1, platform="website", key="k",
                        text="Знижка 20% для ветеранів", url="http://x")], "k"


class _Extractor:
    def extract(self, item, provider, cats):
        return object() if "знижка" in item.text.lower() else None


def test_runner_records_corpus():
    rec = _Rec()
    Runner(_Api(), {"website": _Fetcher()}, _Extractor(), rate_limiter=_RL(),
           corpus_recorder=rec).run()
    assert ("Знижка 20% для ветеранів", True) in [(t, b) for t, b in rec.calls]


class _RL:
    def wait(self, *a, **k): pass
```

- [ ] **Step 2: Запустити — падає**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_corpus_wiring.py -v`
Expected: FAIL (`TypeError: unexpected keyword 'corpus_recorder'`).

- [ ] **Step 3: Реалізувати вклинення**

У `crawler/crawler/runner.py` `__init__` додати параметр і поле:

```python
    def __init__(self, api_client, fetchers, extractor, rate_limiter,
                 discovery=None, keywords=None, harvester=None, brand_feed=None,
                 freshness_ttl_days=30, corpus_recorder=None):
        ...
        self._corpus = corpus_recorder
```

У `_crawl_source`, у циклі по items (рядок 73–79), одразу після `cand = self._extractor.extract(...)`:

```python
            if self._corpus is not None:
                self._corpus.record(item, cand is not None)
```

У `crawler/crawler/discovery/harvest.py` `ActiveHarvester.__init__` додати `corpus_recorder=None` → `self._corpus = corpus_recorder`. У `_process_page`, замість поточного list-comprehension зробити явний цикл, що і лейблить, і збирає passing:

```python
    def _process_page(self, cand, items, cats, known, summary) -> None:
        passing = []
        for it in items:
            is_offer = self._extractor.extract(it, "", cats) is not None
            if self._corpus is not None:
                self._corpus.record(it, is_offer)
            if is_offer:
                passing.append(it)
        ctx = build_page_ctx(cand, passing)
        ...  # решта без змін
```

- [ ] **Step 4: Запустити — пройде (+ повний сют)**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_corpus_wiring.py tests/test_active_harvest.py tests/test_runner.py -q`
Expected: PASS.

- [ ] **Step 5: Коміт**

```bash
git add crawler/crawler/runner.py crawler/crawler/discovery/harvest.py crawler/tests/test_corpus_wiring.py
git commit -m "feat(crawler): wire CorpusRecorder into runner + active harvester"
```

---

### Task 9: Backend — ендпоінт `GET /api/internal/approved-offers`

**Files:**
- Modify: `backend/app/crud/offer.py` (додати `list_published_since`)
- Modify: `backend/app/routers/internal.py` (новий ендпоінт + response-модель)
- Test: `backend/tests/test_internal.py` (додати кейси)

**Interfaces:**
- Produces: `GET /api/internal/approved-offers?since=<iso8601|порожньо>` → `list[{text: str, host: str, approved_at: str}]`, лише `OfferStatus.published`, `updated_at > since`. `text` = `title + "\n" + description`; `host` — з `site_url`/`article_url`.

- [ ] **Step 1: Тест, що падає**

```python
# додати у backend/tests/test_internal.py
def test_approved_offers_returns_published(client, db_session):
    from app.models import Offer
    from app.models.enums import CreatedBy, OfferStatus, OfferType
    o = Offer(type=OfferType.discount, title="Знижка 20%", description="для ветеранів",
              provider="Shop", site_url="https://shop.ua/sale",
              status=OfferStatus.published, created_by=CreatedBy.admin)
    db_session.add(o); db_session.commit()
    r = client.get("/api/internal/approved-offers",
                   headers={"X-API-Key": settings.crawler_api_key})
    assert r.status_code == 200
    body = r.json()
    assert any("Знижка 20%" in row["text"] and row["host"] == "shop.ua" for row in body)


def test_approved_offers_requires_api_key(client):
    assert client.get("/api/internal/approved-offers").status_code == 401
```

- [ ] **Step 2: Запустити — падає**

Run (потрібен `mysql-container`): `docker start mysql-container; cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_internal.py::test_approved_offers_returns_published -v`
Expected: FAIL (404 — маршруту нема).

- [ ] **Step 3: Реалізувати CRUD + маршрут**

У `backend/app/crud/offer.py` додати:

```python
def list_published_since(db, since=None):
    from app.models.enums import OfferStatus
    q = db.query(Offer).filter(Offer.status == OfferStatus.published)
    if since is not None:
        q = q.filter(Offer.updated_at > since)
    return q.order_by(Offer.updated_at.asc()).all()
```

У `backend/app/routers/internal.py` додати модель і ендпоінт:

```python
from datetime import datetime
from urllib.parse import urlsplit


class ApprovedOfferOut(BaseModel):
    text: str
    host: str
    approved_at: datetime


def _host(url):
    return urlsplit(url or "").netloc.lower().removeprefix("www.")


@router.get("/approved-offers", response_model=list[ApprovedOfferOut])
def list_approved_offers(since: datetime | None = None, db: Session = Depends(get_db)):
    rows = offer_crud.list_published_since(db, since)
    return [
        ApprovedOfferOut(
            text=f"{o.title}\n{o.description or ''}".strip(),
            host=_host(o.site_url or o.article_url),
            approved_at=o.updated_at,
        )
        for o in rows
    ]
```

- [ ] **Step 4: Запустити — пройде**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_internal.py -q`
Expected: PASS.

- [ ] **Step 5: Коміт**

```bash
git add backend/app/crud/offer.py backend/app/routers/internal.py backend/tests/test_internal.py
git commit -m "feat(backend): internal GET /approved-offers for crawler snowball"
```

---

### Task 10: Crawler — `api_client.list_approved_offers` + `learn/snowball.py`

**Files:**
- Modify: `crawler/crawler/api_client.py` (метод `list_approved_offers`)
- Create: `crawler/crawler/learn/snowball.py`
- Test: `crawler/tests/test_snowball.py`

**Interfaces:**
- Consumes: `CorpusRecorder.record(item, True, snowball=True)`; `api.list_approved_offers(since)`.
- Produces: `SnowballIngestor(api, recorder, state_path).ingest() -> int` — тягне нові published-офери, пише як сильний PASS, просуває курсор `since`; повертає кількість.

- [ ] **Step 1: Тест, що падає**

```python
# crawler/tests/test_snowball.py
from crawler.learn.snowball import SnowballIngestor


class _Api:
    def __init__(self, rows): self._rows = rows
    def list_approved_offers(self, since): return self._rows


class _Rec:
    def __init__(self): self.calls = []
    def record(self, item, is_offer, **kw): self.calls.append((item.text, is_offer, kw))


def test_ingest_records_strong_pass(tmp_path):
    api = _Api([{"text": "Знижка для ветеранів", "host": "shop.ua",
                 "approved_at": "2026-07-22T10:00:00"}])
    rec = _Rec()
    n = SnowballIngestor(api, rec, str(tmp_path / "s.json")).ingest()
    assert n == 1
    text, is_offer, kw = rec.calls[0]
    assert is_offer is True and kw.get("snowball") is True


def test_cursor_persisted(tmp_path):
    sp = str(tmp_path / "s.json")
    api = _Api([{"text": "x", "host": "shop.ua", "approved_at": "2026-07-22T10:00:00"}])
    SnowballIngestor(api, _Rec(), sp).ingest()
    import json
    assert json.load(open(sp))["since"] == "2026-07-22T10:00:00"
```

- [ ] **Step 2: Запустити — падає**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_snowball.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Реалізувати**

У `crawler/crawler/api_client.py` додати метод (поряд з іншими GET; використати наявний `self._client`/патерн — узгодити з існуючими методами файлу):

```python
    def list_approved_offers(self, since: str | None = None):
        params = {"since": since} if since else {}
        resp = self._client.get(f"{self._base}/api/internal/approved-offers",
                                params=params, headers=self._headers)
        resp.raise_for_status()
        return resp.json()
```

*(Якщо імена полів у `ApiClient` інші — узгодити з рештою методів того ж файлу.)*

```python
# crawler/crawler/learn/snowball.py
"""Snowball: прийняті модератором (published) офери → корпус як сильний PASS."""

import json
import os

from crawler.models import RawItem


class SnowballIngestor:
    def __init__(self, api, recorder, state_path: str):
        self._api = api
        self._rec = recorder
        self._state_path = state_path

    def _since(self):
        try:
            return json.load(open(self._state_path, encoding="utf-8")).get("since")
        except (OSError, ValueError):
            return None

    def _save_since(self, since):
        os.makedirs(os.path.dirname(self._state_path) or ".", exist_ok=True)
        json.dump({"since": since}, open(self._state_path, "w", encoding="utf-8"))

    def ingest(self) -> int:
        rows = self._api.list_approved_offers(self._since()) or []
        n = 0
        newest = None
        for row in rows:
            item = RawItem(source_id=0, platform="website", key="snowball",
                           text=row.get("text", ""),
                           url=f"https://{row.get('host', '')}")
            self._rec.record(item, True, snowball=True)
            n += 1
            newest = row.get("approved_at") or newest
        if newest:
            self._save_since(newest)
        return n
```

- [ ] **Step 4: Запустити — пройде**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_snowball.py -q`
Expected: PASS.

- [ ] **Step 5: Коміт**

```bash
git add crawler/crawler/api_client.py crawler/crawler/learn/snowball.py crawler/tests/test_snowball.py
git commit -m "feat(crawler): snowball ingestor — published offers → strong PASS corpus"
```

---

### Task 11: `learn/tokenize.py` — лематизація (pymorphy3), пін залежності

**Files:**
- Modify: `crawler/requirements.txt` (додати пін)
- Create: `crawler/crawler/learn/tokenize.py`
- Test: `crawler/tests/test_tokenize.py`

**Interfaces:**
- Produces: `tokenize(text: str) -> list[str]` — леми укр. слів (довжина ≥3) + біграми лем; детерміновано за піном словника.

- [ ] **Step 1: Додати залежність**

У `crawler/requirements.txt` додати рядки (пін точних версій):

```
pymorphy3==2.0.2
pymorphy3-dicts-uk==2.4.1.1.1663094765
```

Встановити: `cd crawler && ./.venv/Scripts/python.exe -m pip install pymorphy3==2.0.2 pymorphy3-dicts-uk==2.4.1.1.1663094765`

- [ ] **Step 2: Тест, що падає**

```python
# crawler/tests/test_tokenize.py
from crawler.learn.tokenize import tokenize


def test_lemmatizes_inflected_forms():
    toks = tokenize("знижки знижок знижкою")
    assert toks.count("знижка") >= 3  # усі форми → одна лема


def test_includes_bigrams():
    toks = tokenize("спеціальна ціна")
    assert "спеціальний ціна" in toks or "спеціальна ціна" in toks
```

- [ ] **Step 3: Запустити — падає**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_tokenize.py -v`
Expected: FAIL (`ModuleNotFoundError: crawler.learn.tokenize`).

- [ ] **Step 4: Реалізувати**

```python
# crawler/crawler/learn/tokenize.py
"""Офлайн-токенізація для майнера: леми укр. слів + біграми. Детерміновано за
піном pymorphy3-dicts-uk. Використовується ЛИШЕ в майнері, не в живому гейті."""

import re

import pymorphy3

_WORD = re.compile(r"[a-zа-яїієґ']{3,}", re.IGNORECASE)
_morph = pymorphy3.MorphAnalyzer(lang="uk")


def _lemma(word: str) -> str:
    parsed = _morph.parse(word.lower())
    return parsed[0].normal_form if parsed else word.lower()


def tokenize(text: str) -> list[str]:
    lemmas = [_lemma(w) for w in _WORD.findall(text or "")]
    bigrams = [f"{a} {b}" for a, b in zip(lemmas, lemmas[1:])]
    return lemmas + bigrams
```

- [ ] **Step 5: Запустити — пройде, коміт**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_tokenize.py -q`
Expected: PASS.

```bash
git add crawler/requirements.txt crawler/crawler/learn/tokenize.py crawler/tests/test_tokenize.py
git commit -m "feat(crawler): learn/tokenize — pinned pymorphy3 lemmatization (offline)"
```

---

### Task 12: `learn/miner.py` — weighted log-odds контраст

**Files:**
- Create: `crawler/crawler/learn/miner.py`
- Test: `crawler/tests/test_miner.py`

**Interfaces:**
- Consumes: `read_corpus` рядки (`{text, label, host, neg_anchor, snowball}`), `tokenize`.
- Produces: `TermScore(term, z, pass_count, fail_count, domains: set[str], in_neg_anchor: bool)`; `mine(rows, known_stems, snowball_weight=3) -> list[TermScore]` — сортовано за `z` спадно; терми, вже присутні в `known_stems` (як підрядок), відсіяні.

- [ ] **Step 1: Тест, що падає**

```python
# crawler/tests/test_miner.py
from crawler.learn.miner import mine


def _row(text, label, host, neg=False):
    return {"text": text, "label": label, "host": host, "neg_anchor": neg, "snowball": False}


def test_pass_associated_term_scores_positive():
    rows = ([_row("уцінка на все", "pass", f"d{i}.ua") for i in range(5)]
            + [_row("звичайна новина міста", "fail", f"n{i}.ua") for i in range(5)])
    scores = mine(rows, known_stems=())
    top = {s.term for s in scores if s.z > 1.5}
    assert "уцінка" in top


def test_known_stem_excluded():
    rows = ([_row("знижка знижка", "pass", "a.ua")]
            + [_row("новина", "fail", "b.ua")])
    scores = mine(rows, known_stems=("знижк",))
    assert all("знижк" not in s.term for s in scores)
```

- [ ] **Step 2: Запустити — падає**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_miner.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Реалізувати (Monroe weighted log-odds, informative Dirichlet prior)**

```python
# crawler/crawler/learn/miner.py
"""Офлайн контраст-майнер: weighted log-odds з informative Dirichlet prior
(Monroe, Colaresi, Quinn 2008) між PASS та FAIL корпусами. Не сира частота."""

import math
from collections import defaultdict
from dataclasses import dataclass, field

from crawler.learn.tokenize import tokenize


@dataclass
class TermScore:
    term: str
    z: float
    pass_count: int
    fail_count: int
    domains: set = field(default_factory=set)
    in_neg_anchor: bool = False


def mine(rows, known_stems=(), snowball_weight: int = 3, alpha: float = 0.01):
    y_pass, y_fail = defaultdict(float), defaultdict(float)
    domains = defaultdict(set)
    neg = defaultdict(bool)
    for r in rows:
        w = snowball_weight if r.get("snowball") else 1
        toks = set(tokenize(r.get("text", "")))
        for t in toks:
            if r.get("label") == "pass":
                y_pass[t] += w
                domains[t].add(r.get("host", ""))
            else:
                y_fail[t] += w
            if r.get("neg_anchor"):
                neg[t] = True

    vocab = set(y_pass) | set(y_fail)
    a0 = alpha * len(vocab)
    n_pass = sum(y_pass.values()) + a0
    n_fail = sum(y_fail.values()) + a0

    out = []
    for t in vocab:
        if any(k in t for k in known_stems):
            continue
        yp, yf = y_pass[t] + alpha, y_fail[t] + alpha
        delta = math.log(yp / (n_pass - yp)) - math.log(yf / (n_fail - yf))
        var = 1.0 / yp + 1.0 / yf
        z = delta / math.sqrt(var)
        out.append(TermScore(term=t, z=z, pass_count=int(y_pass[t]),
                             fail_count=int(y_fail[t]), domains=domains[t],
                             in_neg_anchor=neg[t]))
    out.sort(key=lambda s: s.z, reverse=True)
    return out
```

- [ ] **Step 4: Запустити — пройде, коміт**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_miner.py -q`
Expected: PASS.

```bash
git add crawler/crawler/learn/miner.py crawler/tests/test_miner.py
git commit -m "feat(crawler): learn/miner — weighted log-odds contrast"
```

---

### Task 13: `learn/vetoes.py` — multi-domain / PASS-collision / abstention

**Files:**
- Create: `crawler/crawler/learn/vetoes.py`
- Test: `crawler/tests/test_vetoes.py`

**Interfaces:**
- Consumes: `TermScore` (з Task 12).
- Produces: `survivors(scores, min_domains=3, min_z=1.5, max_candidates=50) -> list[TermScore]` — застосовує три вето послідовно.

- [ ] **Step 1: Тест, що падає**

```python
# crawler/tests/test_vetoes.py
from crawler.learn.miner import TermScore
from crawler.learn.vetoes import survivors


def _ts(term, z, domains, neg=False):
    return TermScore(term=term, z=z, pass_count=len(domains), fail_count=0,
                     domains=set(domains), in_neg_anchor=neg)


def test_multi_domain_support_required():
    ok = _ts("уцінка", 3.0, ["a.ua", "b.ua", "c.ua"])
    weak = _ts("рідкість", 3.0, ["a.ua"])
    out = survivors([ok, weak], min_domains=3, min_z=1.5)
    terms = {s.term for s in out}
    assert "уцінка" in terms and "рідкість" not in terms


def test_pass_collision_and_abstention():
    collide = _ts("розклад", 3.0, ["a.ua", "b.ua", "c.ua"], neg=True)
    lowz = _ts("може", 0.5, ["a.ua", "b.ua", "c.ua"])
    out = survivors([collide, lowz], min_domains=3, min_z=1.5)
    assert out == []
```

- [ ] **Step 2: Запустити — падає**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_vetoes.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Реалізувати**

```python
# crawler/crawler/learn/vetoes.py
"""Запобіжники перед тим, як кандидат-терм потрапляє в чергу аудиту:
multi-domain support (анти-overfit), PASS-collision (не тягнути gov/media),
abstention (низька впевненість)."""


def survivors(scores, min_domains: int = 3, min_z: float = 1.5,
              max_candidates: int = 50):
    out = []
    for s in scores:
        if s.z < min_z:                       # abstention
            continue
        if s.in_neg_anchor:                   # PASS-collision з negative anchor
            continue
        if len({d for d in s.domains if d}) < min_domains:  # multi-domain support
            continue
        out.append(s)
        if len(out) >= max_candidates:
            break
    return out
```

- [ ] **Step 4: Запустити — пройде, коміт**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_vetoes.py -q`
Expected: PASS.

```bash
git add crawler/crawler/learn/vetoes.py crawler/tests/test_vetoes.py
git commit -m "feat(crawler): learn/vetoes — multi-domain / PASS-collision / abstention"
```

---

### Task 14: `learn/audit.py` — черга кандидатів + CLI approve/reject → LEARNED

**Files:**
- Create: `crawler/crawler/learn/audit.py`
- Test: `crawler/tests/test_audit.py`

**Interfaces:**
- Produces:
  - `write_candidates(path, survivors) -> None` — пише `candidates.json` `[{term, z, support, examples?}]`.
  - `approve(term, candidates_path, learned_path) -> None` — переносить терм у LEARNED (`[{"term", "z", "approved_at"}]`), прибирає з кандидатів.
  - `reject(term, candidates_path, stoplist_path) -> None` — у стоплист.
  - `load_stoplist(path) -> tuple[str, ...]`.

- [ ] **Step 1: Тест, що падає**

```python
# crawler/tests/test_audit.py
import json
from crawler.learn.audit import write_candidates, approve, reject, load_stoplist
from crawler.learn.miner import TermScore


def _ts(term):
    return TermScore(term=term, z=3.0, pass_count=5, fail_count=0,
                     domains={"a.ua", "b.ua", "c.ua"})


def test_approve_moves_term_to_learned(tmp_path):
    cand = str(tmp_path / "candidates.json")
    learned = str(tmp_path / "learned.json")
    write_candidates(cand, [_ts("уцінка")])
    approve("уцінка", cand, learned)
    terms = [e["term"] for e in json.load(open(learned, encoding="utf-8"))]
    assert "уцінка" in terms
    assert all(e["term"] != "уцінка" for e in json.load(open(cand, encoding="utf-8")))


def test_reject_adds_to_stoplist(tmp_path):
    cand = str(tmp_path / "candidates.json")
    stop = str(tmp_path / "stop.json")
    write_candidates(cand, [_ts("розклад")])
    reject("розклад", cand, stop)
    assert "розклад" in load_stoplist(stop)
```

- [ ] **Step 2: Запустити — падає**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_audit.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Реалізувати**

```python
# crawler/crawler/learn/audit.py
"""Черга кандидат-термів + CLI аудиту. approve → LEARNED-дата-файл (єдиний шлях
у живий гейт), reject → стоплист. Промоція завжди через людину."""

import argparse
import json
import os
import time


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _save(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def write_candidates(path, survivors) -> None:
    _save(path, [{"term": s.term, "z": round(s.z, 3),
                  "support": len({d for d in s.domains if d})} for s in survivors])


def approve(term, candidates_path, learned_path) -> None:
    learned = _load(learned_path, [])
    if not any(e.get("term") == term for e in learned):
        cand = next((c for c in _load(candidates_path, []) if c.get("term") == term), {})
        learned.append({"term": term, "z": cand.get("z"),
                        "approved_at": int(time.time())})
        _save(learned_path, learned)
    _save(candidates_path, [c for c in _load(candidates_path, []) if c.get("term") != term])


def reject(term, candidates_path, stoplist_path) -> None:
    stop = _load(stoplist_path, [])
    if term not in stop:
        stop.append(term)
        _save(stoplist_path, stop)
    _save(candidates_path, [c for c in _load(candidates_path, []) if c.get("term") != term])


def load_stoplist(path) -> tuple[str, ...]:
    return tuple(_load(path, []))


def _main(argv=None):  # pragma: no cover - CLI wrapper
    p = argparse.ArgumentParser(prog="audit")
    sub = p.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list"); ls.add_argument("--candidates", required=True)
    ap = sub.add_parser("approve"); ap.add_argument("term")
    ap.add_argument("--candidates", required=True); ap.add_argument("--learned", required=True)
    rj = sub.add_parser("reject"); rj.add_argument("term")
    rj.add_argument("--candidates", required=True); rj.add_argument("--stoplist", required=True)
    a = p.parse_args(argv)
    if a.cmd == "list":
        for c in _load(a.candidates, []):
            print(f"{c['term']}\tz={c.get('z')}\tsupport={c.get('support')}")
    elif a.cmd == "approve":
        approve(a.term, a.candidates, a.learned); print(f"approved: {a.term}")
    elif a.cmd == "reject":
        reject(a.term, a.candidates, a.stoplist); print(f"rejected: {a.term}")


if __name__ == "__main__":  # pragma: no cover
    _main()
```

- [ ] **Step 4: Запустити — пройде, коміт**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_audit.py -q`
Expected: PASS.

```bash
git add crawler/crawler/learn/audit.py crawler/tests/test_audit.py
git commit -m "feat(crawler): learn/audit — candidate queue + CLI approve/reject → LEARNED"
```

---

### Task 15: Майнер поважає стоплист + `run_miner` оркестратор

Звʼязати майнер+вето+стоплист+запис кандидатів в одну офлайн-команду.

**Files:**
- Create: `crawler/crawler/learn/run_miner.py`
- Modify: `crawler/crawler/learn/miner.py` (приймати `stoplist` у `mine`)
- Test: `crawler/tests/test_run_miner.py`

**Interfaces:**
- Consumes: `read_corpus`, `mine`, `survivors`, `write_candidates`, `load_stoplist`, `promo_lexicon.offer_triggers`, config.
- Produces: `run_miner(config) -> int` — читає корпус, майнить (known = SEED+LEARNED стеми, мінус стоплист), вето, пише candidates.json; повертає к-ть кандидатів.

- [ ] **Step 1: Тест, що падає**

```python
# crawler/tests/test_run_miner.py
import json
from crawler.learn.run_miner import run_miner


class _Cfg:
    corpus_path = None
    promo_lexicon_learned_path = None
    miner_min_domain_support = 3
    miner_min_logodds = 1.5
    miner_max_candidates_per_run = 50


def test_run_miner_writes_candidates(tmp_path):
    corpus = tmp_path / "corpus.jsonl"
    lines = ([{"text": "уцінка на все", "label": "pass", "host": f"d{i}.ua",
               "neg_anchor": False, "snowball": False} for i in range(4)]
             + [{"text": "звичайна новина", "label": "fail", "host": f"n{i}.ua",
                 "neg_anchor": False, "snowball": False} for i in range(4)])
    corpus.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines),
                      encoding="utf-8")
    cfg = _Cfg()
    cfg.corpus_path = str(corpus)
    cfg.promo_lexicon_learned_path = str(tmp_path / "learned.json")
    cfg.candidates_path = str(tmp_path / "candidates.json")
    cfg.stoplist_path = str(tmp_path / "stop.json")
    n = run_miner(cfg)
    assert n >= 1
    terms = [c["term"] for c in json.load(open(cfg.candidates_path, encoding="utf-8"))]
    assert "уцінка" in terms
```

- [ ] **Step 2: Запустити — падає**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_run_miner.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Реалізувати**

У `crawler/crawler/learn/miner.py` розширити сигнатуру `mine(rows, known_stems=(), stoplist=(), snowball_weight=3, alpha=0.01)` і у циклі відсіву додати: `if t in stoplist: continue`.

```python
# crawler/crawler/learn/run_miner.py
"""Офлайн-оркестратор: корпус → майнер → вето → черга кандидатів."""

from crawler.discovery import promo_lexicon as pl
from crawler.learn.audit import load_stoplist, write_candidates
from crawler.learn.corpus import read_corpus
from crawler.learn.miner import mine
from crawler.learn.vetoes import survivors


def run_miner(config) -> int:
    pl.reload_learned(getattr(config, "promo_lexicon_learned_path", None))
    rows = read_corpus(config.corpus_path)
    known = pl.offer_triggers()
    stop = load_stoplist(getattr(config, "stoplist_path", None))
    scores = mine(rows, known_stems=known, stoplist=stop)
    keep = survivors(scores, min_domains=config.miner_min_domain_support,
                     min_z=config.miner_min_logodds,
                     max_candidates=config.miner_max_candidates_per_run)
    write_candidates(config.candidates_path, keep)
    return len(keep)
```

- [ ] **Step 4: Запустити — пройде, коміт**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_run_miner.py tests/test_miner.py -q`
Expected: PASS.

```bash
git add crawler/crawler/learn/run_miner.py crawler/crawler/learn/miner.py crawler/tests/test_run_miner.py
git commit -m "feat(crawler): run_miner orchestrator (corpus→miner→vetoes→candidates)"
```

---

### Task 16: Bootstrap CLI + wiring рекордера/snowball у `build_runner`

**Files:**
- Create: `crawler/crawler/learn/bootstrap.py`
- Modify: `crawler/crawler/wiring.py` (`build_runner`: створити `CorpusRecorder`, `reload_learned`, передати в `Runner`/`ActiveHarvester`, запустити snowball best-effort)
- Test: `crawler/tests/test_bootstrap.py`, `crawler/tests/test_wiring.py` (розширити)

**Interfaces:**
- Consumes: `_build_brand_feed`, `WebsiteFetcher`, `DomainWalker`, `CorpusRecorder`, `HeuristicExtractor`.
- Produces: `bootstrap(config, limit=None) -> int` — ганяє website-фетч+walker по brand-feed доменах, лейблить, пише корпус; повертає к-ть записів.

- [ ] **Step 1: Тест bootstrap, що падає**

```python
# crawler/tests/test_bootstrap.py
from crawler.learn.bootstrap import bootstrap


class _Cfg:
    corpus_path = None
    corpus_max_mb = 10.0
    extractor = "heuristic"
    request_timeout = 5.0
    # brand-feed вимкнено у тесті → bootstrap має коректно повернути 0
    brand_feed_enabled = False


def test_bootstrap_no_brandfeed_returns_zero(tmp_path):
    cfg = _Cfg()
    cfg.corpus_path = str(tmp_path / "corpus.jsonl")
    assert bootstrap(cfg) == 0
```

- [ ] **Step 2: Запустити — падає**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_bootstrap.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Реалізувати bootstrap**

```python
# crawler/crawler/learn/bootstrap.py
"""Одноразовий наповнювач корпусу: website-фетч + walker по brand-feed доменах,
щоб майнер мав дані вже до перших живих прогонів."""

import logging

from crawler.extract.base import CategoryIndex, get_extractor
from crawler.learn.corpus import CorpusRecorder
from crawler.models import SourceCandidate

log = logging.getLogger(__name__)


def bootstrap(config, limit=None) -> int:
    if not getattr(config, "brand_feed_enabled", False):
        return 0
    import httpx
    from crawler.discovery.walker import DomainWalker  # локальні імпорти — дешевий шлях за False
    from crawler.fetchers.website import WebsiteFetcher
    from crawler.wiring import _build_brand_feed, _build_walker, _http_client

    client = _http_client(config.request_timeout)
    feed = _build_brand_feed(config)
    walker, _ = _build_walker(config, client)
    fetcher = WebsiteFetcher(client)
    extractor = get_extractor(config.extractor)
    recorder = CorpusRecorder(config.corpus_path, config.corpus_max_mb)
    cats = CategoryIndex(target=[], offer=[])

    n = 0
    cands = feed.candidates(set())
    for cand in (cands[:limit] if limit else cands):
        try:
            plan = walker.walk(cand)
            for url in plan.urls:
                src = {"id": None, "type": "website", "url_or_handle": url, "name": cand.name}
                items, _ = fetcher.fetch(src, None)
                for it in items:
                    recorder.record(it, extractor.extract(it, "", cats) is not None)
                    n += 1
        except Exception as exc:  # noqa: BLE001 — best-effort
            log.warning("bootstrap failed for %s: %s", cand.url_or_handle, exc)
    return n
```

- [ ] **Step 4: Wiring у `build_runner`**

У `crawler/crawler/wiring.py` `build_runner`, перед `return Runner(...)`:

```python
    corpus_recorder = None
    if config.autofill_enabled:
        from crawler.learn.corpus import CorpusRecorder
        from crawler.learn.snowball import SnowballIngestor
        pl_mod = __import__("crawler.discovery.promo_lexicon", fromlist=["reload_learned"])
        pl_mod.reload_learned(config.promo_lexicon_learned_path)
        corpus_recorder = CorpusRecorder(config.corpus_path, config.corpus_max_mb)
        if harvester is not None:
            harvester._corpus = corpus_recorder  # той самий рекордер у харвестері
        try:
            SnowballIngestor(api, corpus_recorder, config.snowball_state_path).ingest()
        except Exception as exc:  # noqa: BLE001 — snowball best-effort
            log.warning("snowball ingest failed: %s", exc)
```

і в `return Runner(...)` додати `corpus_recorder=corpus_recorder`.

*(Прим.: `harvester._corpus` — прямий доступ прийнятний, бо wiring — «складач» тих самих обʼєктів; альтернатива — передати рекордер у `ActiveHarvester(...)` конструктор на рядку 104. Обрати конструктор, якщо хочеться чистіше: додати `corpus_recorder=corpus_recorder` в `ActiveHarvester(...)`.)*

- [ ] **Step 5: Тест wiring (autofill off → рекордер None)**

Додати у `crawler/tests/test_wiring.py`:

```python
def test_build_runner_autofill_off_has_no_recorder(monkeypatch):
    from crawler.config import Config
    from crawler.wiring import build_runner
    cfg = Config(internal_api_url="http://x", crawler_api_key="k", extractor="heuristic",
                 active_discovery=False, request_timeout=1.0, min_delay_seconds=1.0,
                 autofill_enabled=False, brand_feed_enabled=False,
                 sitemap_depth_enabled=False)
    r = build_runner(cfg)
    assert r._corpus is None
```

- [ ] **Step 6: Запустити — пройде, коміт**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_bootstrap.py tests/test_wiring.py -q`
Expected: PASS.

```bash
git add crawler/crawler/learn/bootstrap.py crawler/crawler/wiring.py crawler/tests/test_bootstrap.py crawler/tests/test_wiring.py
git commit -m "feat(crawler): bootstrap CLI + wire recorder/snowball into build_runner (autofill-gated)"
```

---

### Task 17: Наскрізний інтеграційний тест (критерій готовності §2)

**Files:**
- Create: `crawler/tests/test_autofill_e2e.py`

**Interfaces:**
- Consumes: усе вище (`CorpusRecorder`, `run_miner`, `approve`, `promo_lexicon`).

- [ ] **Step 1: Написати наскрізний тест**

```python
# crawler/tests/test_autofill_e2e.py
"""§2: bootstrapped корпус → майнер → вето → approve → живий гейт ловить новий терм."""
import json
from crawler.discovery import promo_lexicon as pl
from crawler.learn.audit import approve
from crawler.learn.run_miner import run_miner
from crawler.extract.base import CategoryIndex, get_extractor
from crawler.models import RawItem


class _Cfg:
    miner_min_domain_support = 3
    miner_min_logodds = 1.5
    miner_max_candidates_per_run = 50


def _cats():
    return CategoryIndex(target=[{"id": 10, "name": "Ветеран", "slug": "veteran"}], offer=[])


def test_end_to_end_autofill(tmp_path):
    # 1) корпус: 'кешбек' у PASS на 4 доменах, шум у FAIL
    corpus = tmp_path / "corpus.jsonl"
    rows = ([{"text": "кешбек для ветеранів", "label": "pass", "host": f"d{i}.ua",
              "neg_anchor": False, "snowball": False} for i in range(4)]
            + [{"text": "новина міста сьогодні", "label": "fail", "host": f"n{i}.ua",
               "neg_anchor": False, "snowball": False} for i in range(4)])
    corpus.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows),
                      encoding="utf-8")

    cfg = _Cfg()
    cfg.corpus_path = str(corpus)
    cfg.promo_lexicon_learned_path = str(tmp_path / "learned.json")
    cfg.candidates_path = str(tmp_path / "candidates.json")
    cfg.stoplist_path = str(tmp_path / "stop.json")

    # SEED ще НЕ містить 'кешбек'? — містить (Task 3). Для чистоти e2e беремо форму поза SEED:
    # заміна тексту на вигаданий промо-стем, якого нема в SEED.
    rows2 = [dict(r, text=r["text"].replace("кешбек", "рібейт")) for r in rows]
    corpus.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows2),
                      encoding="utf-8")

    # 2) майнер+вето → кандидати
    n = run_miner(cfg)
    assert n >= 1
    cand_terms = [c["term"] for c in json.load(open(cfg.candidates_path, encoding="utf-8"))]
    assert "рібейт" in cand_terms

    # 3) approve → LEARNED
    approve("рібейт", cfg.candidates_path, cfg.promo_lexicon_learned_path)

    # 4) живий гейт тепер ловить новий терм
    pl.reload_learned(cfg.promo_lexicon_learned_path)
    ex = get_extractor("heuristic")
    item = RawItem(source_id=1, platform="website", key="k",
                   text="Рібейт для ветеранів у нашому магазині")
    assert ex.extract(item, "Shop", _cats()) is not None
    pl.reload_learned(None)  # reset global
```

- [ ] **Step 2: Запустити — має пройти**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_autofill_e2e.py -v`
Expected: PASS.

- [ ] **Step 3: Повний прогін — детермінований контракт цілий**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — усі наявні 269 + нові тести зелені.

- [ ] **Step 4: Коміт**

```bash
git add crawler/tests/test_autofill_e2e.py
git commit -m "test(crawler): end-to-end autofill acceptance (§2 spec)"
```

---

### Task 18: `.env.example` + документація запуску

**Files:**
- Modify: `crawler/.env.example` (нові кнопки)
- Modify: `RUN.md` (розділ автонаповнення: bootstrap → miner → audit)

- [ ] **Step 1: Додати кнопки в `.env.example`**

```
AUTOFILL_ENABLED=false
CORPUS_PATH=/data/corpus.jsonl
CORPUS_MAX_MB=50
PROMO_LEXICON_LEARNED_PATH=/data/promo_lexicon_learned.json
SNOWBALL_STATE_PATH=/data/snowball_state.json
MINER_MIN_DOMAIN_SUPPORT=3
MINER_MIN_LOGODDS=1.5
MINER_MAX_CANDIDATES_PER_RUN=50
```

- [ ] **Step 2: Додати розділ у `RUN.md`**

Короткий розділ «Автонаповнення промо-лексикону»: (1) `AUTOFILL_ENABLED=true`; (2) bootstrap `python -m crawler.learn.bootstrap`; (3) майнінг `python -m crawler.learn.run_miner`; (4) аудит `python -m crawler.learn.audit list/approve/reject`; наголос: approve — єдиний шлях у живий гейт.

- [ ] **Step 3: Коміт**

```bash
git add crawler/.env.example RUN.md
git commit -m "docs(crawler): autofill env knobs + run instructions"
```

---

## Self-Review

**1. Spec coverage:**
- §4 promo_lexicon (seed+learned) → Tasks 1–3. ✅
- §5.2 labeler + якорі → Task 6 (+ pos anchor Task 5). ✅
- §5.3 CorpusRecorder → Tasks 7–8. ✅
- §5.4 snowball (backend+crawler) → Tasks 9–10. ✅
- §5.5 bootstrap → Task 16. ✅
- §5.6 miner log-odds → Task 12 (+ orchestrator Task 15). ✅
- §5.7 лематизатор (pinned, offline-only) → Task 11. ✅
- §5.8 вето → Task 13. ✅
- §5.9 audit CLI + промоція → Task 14. ✅
- §6 детермінований контракт + e2e → Tasks 2/17. ✅
- §7 конфіг-кнопки → Task 4. ✅

**2. Placeholder scan:** без TBD/TODO; код наведено в кожному кроці; CLI-`_main` під `# pragma: no cover` свідомо.

**3. Type consistency:** `TermScore` (Task 12) поля `term/z/pass_count/fail_count/domains/in_neg_anchor` вжиті однаково в Tasks 13/14/15/17; `LabelRecord` (Task 6) → `CorpusRecorder` (Task 7); `reload_learned`/`offer_triggers` (Task 1) → Tasks 15/16/17; `list_approved_offers` (Task 10) ↔ ендпоінт (Task 9).

**Відкритий нюанс для виконавця:** точні піни `pymorphy3`/`pymorphy3-dicts-uk` (Task 11) звірити з доступними у PyPI на момент виконання; якщо версія недоступна — взяти найближчу стабільну й зафіксувати точним піном.
