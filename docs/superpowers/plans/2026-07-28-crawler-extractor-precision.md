# Точність екстрактора (discount-gate + free-синоніми) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Екстрактор емітить офер лише за наявності конкретної знижки (`%`/`грн`/free-синонім), за прапором `require_discount` (config-дефолт True), + розширена FREE-детекція, щоб гейт не втрачав реальні free/подарунок-офери. Черга модерації перестає заливатися прозою/нав-меню/T&C-фрагментами.

**Architecture:** Crawler-only. `HeuristicExtractor` дістає `require_discount` (class-default False = permissive, щоб наявні прямі-конструктор тести лишались зелені); config-дефолт True вмикає гейт у продакшні через wiring. FREE-regex у `promo_lexicon.py` розширюється безумовно (детекція, не за прапором). Ретро-очищення живої черги — post-merge ops.

**Tech Stack:** Python, pytest; crawler-пакет `crawler/crawler/`, тести `crawler/tests/`.

## Global Constraints

- Crawler baseline **420** тестів має лишитися зеленим; нові додаються зверху.
- Запуск тестів: `cd crawler && ./.venv/Scripts/python.exe -m pytest -q` (Windows, crawler-only, без backend/DB/mysql).
- Пакет під `crawler/crawler/…`; тести `crawler/tests/…`.
- `require_discount`: **class-default `False`** (permissive) у `HeuristicExtractor`/`get_extractor`; **config-дефолт `True`** (Settings+Config+load_config, 3 spots, дзеркало `domain_rating_enabled`).
- `content_hash` рахується з `(title, provider, text)` — FREE-розширення не міняє дедуп-ключів.
- Гейт: `if self._require_discount and discount_type is None: return None`, одразу після блоку обчислення `discount_type`.

---

### Task 1: Розширення FREE-детекції + `_FIXED` повна форма

**Files:**
- Modify: `crawler/crawler/discovery/promo_lexicon.py:31` (FREE regex)
- Modify: `crawler/crawler/extract/heuristic.py:32` (`_FIXED` regex)
- Test: `crawler/tests/test_heuristic.py`

**Interfaces:**
- Consumes: наявні `HeuristicExtractor()` (class-default `require_discount=False` — цей таск НЕ вводить гейт, тож офери емітяться як зараз), `pl.FREE`.
- Produces: `pl.FREE` матчить нові синоніми; extractor дає `discount_type="free"` на них і `"fixed"` на `"N гривень"`.

- [ ] **Step 1: Write the failing tests**

Append to `crawler/tests/test_heuristic.py`:

```python
from crawler.discovery import promo_lexicon as pl
from crawler.extract.heuristic import HeuristicExtractor
from crawler.extract.base import CategoryIndex
from crawler.models import RawItem


def test_free_synonyms_detected():
    for phrase in ["безоплатне обслуговування", "у подарунок кава",
                   "в подарунок десерт", "каву даром", "0 грн за вхід"]:
        assert pl.FREE.search(phrase.lower()), phrase


def test_bare_podarunok_not_matched():
    # "купіть подарунок" must NOT be read as a free offer
    assert not pl.FREE.search("купіть подарунок другу")


def test_extractor_free_synonym_gives_free_type():
    # text contains "ветеран" -> classify() yields target slug "veteran"; "безоплатне" -> free
    ex = HeuristicExtractor()
    item = RawItem(source_id=1, platform="website", key="k",
                   text="Безоплатне обслуговування для ветеранів у нашому центрі")
    res = ex.extract(item, "Center", CategoryIndex(target=[{"id": 10, "slug": "veteran"}], offer=[]))
    assert res is not None
    assert res.discount_type == "free"


def test_extractor_hryven_full_form_gives_fixed():
    ex = HeuristicExtractor()
    item = RawItem(source_id=1, platform="website", key="k",
                   text="Знижка 200 гривень для ветеранів на послуги")
    res = ex.extract(item, "Shop", CategoryIndex(target=[{"id": 10, "slug": "veteran"}], offer=[]))
    assert res is not None
    assert res.discount_type == "fixed"
    assert res.discount_value == "200"
```

Note: the real target slug for text containing "ветеран" is `"veteran"` (from `crawler/crawler/discovery/lexicon.py` `TARGET_LEXICON`, line ~60: `("Ветеран", "veteran", ...)`). The `id` in the test `CategoryIndex` is arbitrary; the `slug` must be `"veteran"` so `target_slugs` is non-empty (otherwise `extract` returns None on the target gate, not the discount gate).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_heuristic.py -k "free_synonyms or bare_podarunok or free_synonym_gives or hryven_full" -v`
Expected: FAIL — `безоплатн`/`подарунок`/`даром`/`0 грн`/`гривень` not yet in the patterns.

- [ ] **Step 3: Broaden FREE regex**

In `crawler/crawler/discovery/promo_lexicon.py`, replace line 31:

```python
FREE = re.compile(r"безкоштов|безплатн|\bfree\b", re.IGNORECASE)
```

with:

```python
FREE = re.compile(
    r"безкоштов|безплатн|безоплатн|\bfree\b|"
    r"[ву]\s+подарунок|у\s+дарунок|"      # кваліфіковані форми; голе "подарунок" над-матчить
    r"даром|задарма|0\s*(?:грн|₴)",
    re.IGNORECASE)
```

- [ ] **Step 4: Add full-form `гривень` to `_FIXED`**

In `crawler/crawler/extract/heuristic.py`, replace line 32:

```python
_FIXED = re.compile(r"(\d[\d\s]{0,7})\s*(?:грн|₴|uah)", re.IGNORECASE)
```

with:

```python
_FIXED = re.compile(r"(\d[\d\s]{0,7})\s*(?:грн|гривень|₴|uah)", re.IGNORECASE)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_heuristic.py -v`
Expected: PASS (new + all pre-existing heuristic tests green).

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/discovery/promo_lexicon.py crawler/crawler/extract/heuristic.py crawler/tests/test_heuristic.py
git commit -m "feat(crawler): broaden FREE detection (synonyms) + hryven full form"
```

---

### Task 2: discount-гейт у екстракторі + `get_extractor` параметр

**Files:**
- Modify: `crawler/crawler/extract/heuristic.py` (`HeuristicExtractor.__init__`, gate in `extract`)
- Modify: `crawler/crawler/extract/base.py:20-22` (`get_extractor` signature)
- Test: `crawler/tests/test_heuristic.py`

**Interfaces:**
- Consumes: `_FIXED`/`FREE` (Task 1).
- Produces: `HeuristicExtractor(require_discount: bool = False)` з `self._require_discount`; `get_extractor(name: str, require_discount: bool = False) -> Extractor`. Пізніший таск (wiring) передає `require_discount=config.require_discount`.

- [ ] **Step 1: Write the failing tests**

Append to `crawler/tests/test_heuristic.py`:

```python
def _target_cats():
    return CategoryIndex(target=[{"id": 10, "slug": "veteran"}], offer=[])


def _no_discount_offer_item():
    # offer trigger ("знижки") + target ("ветеранів") but NO concrete %/грн/free
    return RawItem(source_id=1, platform="website", key="k",
                   text="Знижки для ветеранів у нашому магазині завжди актуальні")


def test_gate_drops_no_discount_when_required():
    ex = HeuristicExtractor(require_discount=True)
    assert ex.extract(_no_discount_offer_item(), "Shop", _target_cats()) is None


def test_gate_keeps_offer_with_discount_when_required():
    ex = HeuristicExtractor(require_discount=True)
    item = RawItem(source_id=1, platform="website", key="k",
                   text="Знижка 15% для ветеранів у нашому магазині")
    res = ex.extract(item, "Shop", _target_cats())
    assert res is not None and res.discount_type == "percent"


def test_default_permissive_keeps_no_discount_offer():
    ex = HeuristicExtractor()  # class-default require_discount=False -> byte-eq to pre-track
    assert ex.extract(_no_discount_offer_item(), "Shop", _target_cats()) is not None


def test_get_extractor_passes_require_discount():
    from crawler.extract.base import get_extractor
    ex = get_extractor("heuristic", require_discount=True)
    assert ex._require_discount is True
    assert get_extractor("heuristic")._require_discount is False
```

(`_target_cats` / `_no_discount_offer_item` use target slug `"veteran"` — the real slug for "ветеран" per Task 1's note.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_heuristic.py -k "gate_drops or gate_keeps or default_permissive or get_extractor_passes" -v`
Expected: FAIL — `HeuristicExtractor.__init__` takes no `require_discount`; `get_extractor` takes no `require_discount`.

- [ ] **Step 3: Add `__init__` + gate to `HeuristicExtractor`**

In `crawler/crawler/extract/heuristic.py`, add an `__init__` just before `def extract` (the class currently has no `__init__`):

```python
class HeuristicExtractor:
    def __init__(self, require_discount: bool = False):
        self._require_discount = require_discount

    def extract(self, item: RawItem, provider: str,
                categories: CategoryIndex) -> OfferCandidate | None:
```

Then insert the gate immediately AFTER the discount-computation block (after the `elif (m := _FIXED.search(text)):` assignment, before the `valid_until = None` line):

```python
        elif (m := _FIXED.search(text)):
            discount_type, discount_value = "fixed", re.sub(r"\s", "", m.group(1))

        if self._require_discount and discount_type is None:
            return None

        valid_until = None
```

- [ ] **Step 4: Thread `require_discount` through `get_extractor`**

In `crawler/crawler/extract/base.py`, replace:

```python
def get_extractor(name: str) -> Extractor:
    if name == "heuristic":
        from crawler.extract.heuristic import HeuristicExtractor
        return HeuristicExtractor()
```

with:

```python
def get_extractor(name: str, require_discount: bool = False) -> Extractor:
    if name == "heuristic":
        from crawler.extract.heuristic import HeuristicExtractor
        return HeuristicExtractor(require_discount=require_discount)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_heuristic.py -v`
Expected: PASS (gate + permissive-default + get_extractor tests, plus Task 1 + pre-existing).

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/extract/heuristic.py crawler/crawler/extract/base.py crawler/tests/test_heuristic.py
git commit -m "feat(crawler): require_discount gate in extractor (permissive default)"
```

---

### Task 3: config-прапор `require_discount` + wiring

**Files:**
- Modify: `crawler/crawler/config.py` (`_RawSettings`, `Config`, `load_config` — 3 spots)
- Modify: `crawler/crawler/wiring.py:106` (pass `require_discount`)
- Test: `crawler/tests/test_config.py`, `crawler/tests/test_wiring.py`

**Interfaces:**
- Consumes: `get_extractor(name, require_discount)` (Task 2).
- Produces: `Config.require_discount: bool` (default True); wiring builds a gated extractor in production.

- [ ] **Step 1: Write the failing tests**

Append to `crawler/tests/test_config.py`:

```python
def test_require_discount_default_true(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)      # no .env -> defaults apply
    assert load_config().require_discount is True


def test_require_discount_env_override(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REQUIRE_DISCOUNT", "false")
    assert load_config().require_discount is False
```

Append to `crawler/tests/test_wiring.py` (mirror the existing `Config(...)` construction used by `test_build_runner_wires_all_platforms` — reuse its config kwargs, adding nothing else):

```python
def test_build_runner_wires_require_discount():
    from crawler.config import Config
    from crawler.wiring import build_runner
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=False, request_timeout=5.0, min_delay_seconds=0.0,
        require_discount=True,
    )
    runner = build_runner(cfg)
    assert runner._extractor._require_discount is True
```

If the `Config(...)` minimal kwargs above are insufficient (missing required fields), copy the exact kwargs from `test_build_runner_wires_all_platforms` in the same file and add `require_discount=True`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_config.py::test_require_discount_default_true tests/test_wiring.py::test_build_runner_wires_require_discount -v`
Expected: FAIL — `Config` has no `require_discount`; `load_config` doesn't set it.

- [ ] **Step 3: Add `require_discount` to config (3 spots)**

In `crawler/crawler/config.py`:

1. In `_RawSettings`, after `host_miner_max_candidates: int = 50` (line ~90):
```python
    require_discount: bool = True
```

2. In `Config` dataclass, after `host_miner_max_candidates: int = 50` (line ~173):
```python
    require_discount: bool = True
```

3. In `load_config()` return, after `host_miner_max_candidates=s.host_miner_max_candidates,` (line ~279):
```python
        require_discount=s.require_discount,
```

- [ ] **Step 4: Pass `require_discount` in wiring**

In `crawler/crawler/wiring.py`, replace line 106:

```python
    extractor = get_extractor(config.extractor)
```

with:

```python
    extractor = get_extractor(config.extractor, require_discount=config.require_discount)
```

- [ ] **Step 5: Run the targeted tests, then the FULL suite**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_config.py tests/test_wiring.py -v`
Expected: PASS.

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest -q`
Expected: all green — baseline 420 + new tests. (No pre-existing test emits a no-discount offer through a wired/config extractor: only `test_config`/`test_wiring` use `build_runner`, and `test_autofill_e2e` uses `get_extractor("heuristic")` with the permissive default — verified during planning.)

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/config.py crawler/crawler/wiring.py crawler/tests/test_config.py crawler/tests/test_wiring.py
git commit -m "feat(crawler): require_discount config flag (default True) wired into extractor"
```

---

## Post-merge live ops (not code — controller executes after merge + crawler rebuild)

After merging to `main` and rebuilding the crawler image (`docker compose --profile crawler up -d --build --no-deps crawler`), clear the existing junk pending offers from the live DB `ubd_probe-db-1` (target: `status='pending_review' AND type='discount' AND discount_type IS NULL`), child-first via FK, mirroring the earlier queue-clear:

```bash
docker exec ubd_probe-db-1 sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" ubd -e "
SET @ids = NULL;
DELETE offer_links FROM offer_links JOIN offers o ON offer_links.offer_id=o.id
  WHERE o.status=\"pending_review\" AND o.type=\"discount\" AND o.discount_type IS NULL;
DELETE offer_offer_categories FROM offer_offer_categories JOIN offers o ON offer_offer_categories.offer_id=o.id
  WHERE o.status=\"pending_review\" AND o.type=\"discount\" AND o.discount_type IS NULL;
DELETE offer_target_categories FROM offer_target_categories JOIN offers o ON offer_target_categories.offer_id=o.id
  WHERE o.status=\"pending_review\" AND o.type=\"discount\" AND o.discount_type IS NULL;
DELETE FROM offers WHERE status=\"pending_review\" AND type=\"discount\" AND discount_type IS NULL;
"'
```

Then verify a subsequent crawl pass produces **only** offers with a discount (spot-check `SELECT status, COUNT(*) FROM offers WHERE discount_type IS NULL AND status='pending_review'` → 0 new), and confirm real discounted offers still flow into the queue.

---

## Self-Review

**Spec coverage:**
- Компонент A (FREE-синоніми + `гривень`) → Task 1 ✅
- Компонент B (гейт + `require_discount` class-default False + `get_extractor`) → Task 2 ✅
- Компонент B (config-дефолт True 3 spots + wiring) → Task 3 ✅
- Ретро-очищення живої черги → Post-merge live ops ✅
- Тести (гейт drop/keep, byte-eq default, синоніми, гривень, config default+override, wiring wired) → Tasks 1–3 ✅

**Placeholder scan:** конкретний код у кожному кроці; єдина умовність — реальний target-slug для "ветеран" (Task 1 note явно каже прочитати `lexicon.py TARGET_LEXICON` і взяти правильний slug, щоб target-гейт не зловив None замість discount-гейту). Не плейсхолдер — інструкція звірки.

**Type consistency:** `require_discount: bool`, `self._require_discount`, `get_extractor(name, require_discount=False)`, `Config.require_discount` — узгоджені між Tasks 1–3.
