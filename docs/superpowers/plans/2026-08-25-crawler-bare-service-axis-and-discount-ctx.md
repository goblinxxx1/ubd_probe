# Гола вісь `{сервіс}+{аудиторія}` + розширення `DISCOUNT_CTX` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Підняти recall краулера двома ADDITIVE змінами — на боці запиту (гола вісь `{сервіс} {аудиторія}`) і на боці детекції знижки (типографські тире/мінус, «мінус», кешбек, спеціальна ціна).

**Architecture:** Дві незалежні точкові зміни в `crawler/`, кожна суто адитивна й покрита юніт-тестами. `build_grid` дістає новий блок у КІНЕЦЬ (byte-stable префікс → живий стан на волюмі не ламається). `DISCOUNT_CTX` — один регекс, розширений безпечними альтернативами (co-requirement `%`/`грн` стримує шум). Backend/схема/API/фронти не чіпаються.

**Tech Stack:** Python 3.12, pytest. Модулі: `crawler/crawler/discovery/query_grid.py`, `crawler/crawler/discovery/promo_lexicon.py`. Тести: `crawler/tests/`.

## Global Constraints

- **Мова:** лише українські форми в лексиконах/регексах. Російські форми (напр. «кэшбек») НЕ додавати — мова агресора.
- **ADDITIVE:** нічого наявного не видаляти й не звужувати; лише додавати. Відкат = git revert одного коміту на таску.
- **Byte-stability гріду:** будь-яке додавання до `build_grid` йде в КІНЕЦЬ `out`; префікс (база 351 + гео-блок + сервісний модифікатор-блок) лишається байт-ідентичним. Це зберігає живі `grid_cursor`/кеш/phrase-pages на волюмі `ubd-crawler-state`.
- **Тести — офлайн:** без мережі та без LLM (юніт на регексах/гріді + один end-to-end через `HeuristicExtractor`).
- **Запуск тестів:** з venv краулера — `cd crawler && .venv/Scripts/python.exe -m pytest tests/<file> -v` (`testpaths=["tests"]`, тож шлях `tests/…`, не `crawler/tests/…`). Docker-образ краулера НЕ містить `tests/`/pytest.

---

### Task 1: Розширення `DISCOUNT_CTX` (recall детекції знижки)

**Files:**
- Modify: `crawler/crawler/discovery/promo_lexicon.py:34-36`
- Test: `crawler/tests/test_promo_lexicon.py` (додати тест-функцію)
- Test: `crawler/tests/test_heuristic.py` (додати end-to-end крос-перевірку)

**Interfaces:**
- Consumes: наявний `promo_lexicon.DISCOUNT_CTX` (re.Pattern), `get_extractor("heuristic", require_discount=True)`, `RawItem`, `CategoryIndex`.
- Produces: розширений `DISCOUNT_CTX`, що додатково матчить: `–`/`−` (типографські тире+цифра), `мінус \d`, `кешбек`, `спеціальн… цін…`. Публічний інтерфейс не змінюється (той самий об'єкт `DISCOUNT_CTX`).

- [ ] **Step 1: Написати падаючий юніт-тест на нові форми**

У `crawler/tests/test_promo_lexicon.py` додати в кінець файлу:

```python
def test_discount_ctx_recognizes_typographic_and_word_forms():
    # типографські тире — реальні сайти рендерять – / − , не ASCII-дефіс
    assert _pl.DISCOUNT_CTX.search("військовим –15%") is not None   # en dash U+2013
    assert _pl.DISCOUNT_CTX.search("військовим −15%") is not None   # minus U+2212
    assert _pl.DISCOUNT_CTX.search("військовим -15%") is not None   # ASCII (регресія)
    # словоформа «мінус» і додаткові знижкові маркери
    assert _pl.DISCOUNT_CTX.search("ветеранам мінус 15%") is not None
    assert _pl.DISCOUNT_CTX.search("кешбек 10% військовим") is not None
    assert _pl.DISCOUNT_CTX.search("спеціальна ціна для ветеранів") is not None
    assert _pl.DISCOUNT_CTX.search("спеціальні ціни для військових") is not None
    # СВІДОМО не матчимо (шумовий клас)
    assert _pl.DISCOUNT_CTX.search("військовим —15%") is None       # em dash U+2014 (буліт)
    assert _pl.DISCOUNT_CTX.search("комісія 15% від суми") is None  # голе % без контексту
    assert _pl.DISCOUNT_CTX.search("акційний набір 1+1 військовим") is not None  # «акці» вже ловить
    # наявні негативи-омографи лишаються негативами
    assert _pl.DISCOUNT_CTX.search("права акціонера") is None
```

- [ ] **Step 2: Запустити — переконатись, що падає**

Run: `cd crawler && .venv/Scripts/python.exe -m pytest tests/test_promo_lexicon.py::test_discount_ctx_recognizes_typographic_and_word_forms -v`
Expected: FAIL — асерти на `–15%`, `−15%`, `мінус 15%`, `кешбек`, `спеціальна ціна` падають (зараз ці форми не матчаться).

- [ ] **Step 3: Розширити регекс**

У `crawler/crawler/discovery/promo_lexicon.py` замінити рядки 34–36:

```python
DISCOUNT_CTX = re.compile(
    r"знижк|акці(?!онер)|розпродаж|спецпропоз|промокод|економ|вигід|"
    r"кешбек|спеціальн\w*\s+цін|мінус\s*\d|[-–−]\s*\d",
    re.IGNORECASE)
```

(`[-–−]` — ASCII-дефіс `-` першим (літеральний), en dash `–` U+2013, мінус `−` U+2212. Em dash `—` СВІДОМО відсутній.)

- [ ] **Step 4: Запустити — переконатись, що проходить**

Run: `cd crawler && .venv/Scripts/python.exe -m pytest tests/test_promo_lexicon.py -v`
Expected: PASS — і нова функція, і наявні (`test_discount_ctx_excludes_shareholder_homograph` тощо).

- [ ] **Step 5: Написати end-to-end тест через екстрактор**

> **ВАЖЛИВО (виправлення під час виконання):** `HeuristicExtractor.extract` має ПЕРШИЙ гейт на `heuristic.py:104` — `if not any(t in low for t in pl.offer_triggers()): return None`. Тобто сторінка мусить містити промо-слово з `SEED_OFFER_TRIGGERS` (знижк/акці/промокод/безкоштов/уцінк/бонус/кешбек/супер ціна/спеціальна ціна/діє до…). Голе «−15%» без промо-слова офером НЕ стає (свідома точність — лишаємо). Тому e2e бере текст із offer-trigger «уцінка», якого НЕМАЄ в `DISCOUNT_CTX`, — так саме en-dash `–15%` постачає знижковий контекст (до лати повертало None).

У `crawler/tests/test_heuristic.py` додати:

```python
def test_percent_extracted_with_typographic_minus_via_trigger():
    # «уцінка» проходить гейт offer_triggers, але сама НЕ в DISCOUNT_CTX;
    # en-dash «–15%» має тепер дати знижковий контекст → percent екстрактиться
    # (до розширення DISCOUNT_CTX цей кейс повертав None).
    ex = get_extractor("heuristic", require_discount=True)
    cand = ex.extract(_item("Уцінка ветеранам –15% на всі послуги"), "Магазин", CATS)
    assert cand is not None
    assert cand.discount_type == "percent"
    assert cand.discount_value == "15"
```

(`–` — EN DASH U+2013; файл лишати UTF-8.)

- [ ] **Step 6: Запустити — переконатись, що проходить**

Run: `cd crawler && .venv/Scripts/python.exe -m pytest tests/test_heuristic.py::test_percent_extracted_with_typographic_minus_via_trigger -v`
Expected: PASS (весь гейт-шлях offer_triggers→percent→DISCOUNT_CTX спрацьовує).

- [ ] **Step 7: Commit**

```bash
git add crawler/crawler/discovery/promo_lexicon.py crawler/tests/test_promo_lexicon.py crawler/tests/test_heuristic.py
git commit -m "feat(crawler): DISCOUNT_CTX ловить типографські тире/мінус, кешбек, спеціальну ціну"
```

---

### Task 2: Гола вісь `{сервіс} {аудиторія}` у гріді (recall запиту)

**Files:**
- Modify: `crawler/crawler/discovery/query_grid.py:122-126` (додати блок у `build_grid`)
- Test: `crawler/tests/test_query_grid.py:112-122` (оновити наявний byte-stability тест) + додати новий тест

**Interfaces:**
- Consumes: наявні `build_grid(cities, services)`, константи `SERVICE_MODIFIERS`, `SERVICE_AUDIENCES`, хелпер `_add`.
- Produces: `build_grid(services=[...])` тепер повертає ДОДАТКОВО `{svc} {aud}` для кожного `svc`×`SERVICE_AUDIENCES` — по +3 запити/сервіс, дописані ПІСЛЯ модифікатор-блоку. Сигнатура незмінна.

- [ ] **Step 1: Оновити наявний byte-stability тест під новий обсяг**

У `crawler/tests/test_query_grid.py` замінити тіло `test_services_block_appended_after_geo` (рядки 112–122) на:

```python
def test_services_block_appended_after_geo():
    from crawler.discovery.query_grid import SERVICE_MODIFIERS, SERVICE_AUDIENCES
    base = build_grid()                       # 1701, no services
    g = build_grid(services=["стоматологія", "автосервіс"])
    assert g[:len(base)] == base              # byte-stable: services appended after
    added = len(g) - len(base)
    # per service: modifier-block (2×3=6) + bare axis (3) = 9
    per_svc = len(SERVICE_MODIFIERS) * len(SERVICE_AUDIENCES) + len(SERVICE_AUDIENCES)
    assert added == 2 * per_svc
    # модифікатор-блок (precision) лишається
    assert "стоматологія знижка військовим" in g
    assert "автосервіс безкоштовно ветеранам" in g
    # гола вісь (recall): сервіс + аудиторія без модифікатора
    assert "стоматологія військовим" in g
    assert "автосервіс ветеранам" in g
```

- [ ] **Step 2: Додати цільовий тест голої осі (порядок + обсяг)**

У `crawler/tests/test_query_grid.py` після `test_services_block_appended_after_geo` додати:

```python
def test_bare_service_axis_appended_after_modifier_block():
    from crawler.discovery.query_grid import SERVICE_MODIFIERS, SERVICE_AUDIENCES
    g = build_grid(services=["автомийка"])
    # усі модифікатор-запити сервісу передують усім голим запитам сервісу
    mod_idx = max(g.index(f"автомийка {m} {a}")
                  for m in SERVICE_MODIFIERS for a in SERVICE_AUDIENCES)
    bare_idx = min(g.index(f"автомийка {a}") for a in SERVICE_AUDIENCES)
    assert mod_idx < bare_idx
    # рівно +3 голі запити/сервіс
    for a in SERVICE_AUDIENCES:
        assert f"автомийка {a}" in g
    assert len([q for q in g if q in {f"автомийка {a}" for a in SERVICE_AUDIENCES}]) == 3
```

- [ ] **Step 3: Запустити — переконатись, що падають**

Run: `cd crawler && .venv/Scripts/python.exe -m pytest tests/test_query_grid.py::test_services_block_appended_after_geo tests/test_query_grid.py::test_bare_service_axis_appended_after_modifier_block -v`
Expected: FAIL — голих форм `"автомийка військовим"` у гріді ще немає; `added` менший за очікуваний.

- [ ] **Step 4: Додати блок голої осі в `build_grid`**

У `crawler/crawler/discovery/query_grid.py`, у функції `build_grid`, одразу ПІСЛЯ наявного сервісного блоку (після рядка `_add(f"{svc} {mod} {aud}".strip())`, перед `return out`) додати:

```python
    for svc in svc_list:                     # A2: гола вісь svc → audience (recall lever)
        for aud in SERVICE_AUDIENCES:        # без модифікатора: «автомийка військовим»
            _add(f"{svc} {aud}".strip())
```

- [ ] **Step 5: Запустити — переконатись, що проходять (і решта гріду не зламалась)**

Run: `cd crawler && .venv/Scripts/python.exe -m pytest tests/test_query_grid.py -v`
Expected: PASS — усі тести гріду, включно з `test_base_prefix_is_byte_stable`, `test_services_none_or_empty_is_byte_eq`, обидва оновлені/нові.

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/discovery/query_grid.py crawler/tests/test_query_grid.py
git commit -m "feat(crawler): гола вісь {сервіс}{аудиторія} у гріді (byte-stable, +3/сервіс)"
```

---

### Task 3: Повний прогін тестів краулера + редеплой

**Files:** (немає змін коду — верифікація й викат)

- [ ] **Step 1: Прогнати весь тест-набір краулера**

Run: `cd crawler && .venv/Scripts/python.exe -m pytest -q`
Expected: усі тести PASS (нуль регресій у гейтах/гріді/екстракторі).

- [ ] **Step 2: Редеплой краулера за рунбуком**

Виконати кроки з [docs/runbook-redeploy-crawler.md](../../runbook-redeploy-crawler.md): `git push` → `build --no-cache crawler` → `up -d --force-recreate crawler searxng`. `llama` не чіпати (розділ 3.5 рунбука).

- [ ] **Step 3: Пост-деплой перевірка**

Run: `docker compose logs --tail=15 crawler`
Expected: свіжі `200 OK`; за пару проходів у логах з'являються голі запити виду `{сервіс} {аудиторія}` (напр. `автомийка військовим`). Живий `grid_cursor` продовжується з місця зупинки (префікс byte-stable — стан на волюмі валідний).

---

## Self-Review

**Spec coverage:**
- Частина A (гола вісь) → Task 2 ✅
- Частина B (лати `DISCOUNT_CTX`: `[-–−]\d`, `мінус\d`, `кешбек`, `спеціальн…цін`) → Task 1 ✅ (em-dash/голе%/бонус/1+1 свідомо відкинуто — покрито негативними асертами в Task 1 Step 1)
- Byte-stability + збереження живого стану → Task 2 (тести) + Task 3 Step 3 ✅
- TDD-тести (grid, DISCOUNT_CTX, end-to-end heuristic) → Tasks 1–2 ✅
- Guardrail'и не чіпаються (ADDITIVE) → Global Constraints ✅

**Placeholder scan:** плейсхолдерів немає; увесь код і команди конкретні.

**Type/name consistency:** `SERVICE_AUDIENCES`/`SERVICE_MODIFIERS`/`_add`/`svc_list` — точні наявні імена з `query_grid.py`; `DISCOUNT_CTX`, `get_extractor`, `RawItem`, `CategoryIndex`, `_item`, `CATS`, `cand.discount_type`/`cand.discount_value` — точні з наявних тестів. `спеціальн\w*\s+цін` (стем «цін») свідомо ловить ціна/ціни/ціною.
