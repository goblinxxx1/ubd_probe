# Crawler Precision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut false-positive crawler offers (news/info Telegram channels, bare percentages, price-hike news) and fix missed location extraction, via four independent gates in the crawler's extract/attribution layer.

**Architecture:** All changes live in `crawler/`. A soft UBD-relevance gate and stricter discount parsing sit in `HeuristicExtractor.extract()`; a Telegram news/info gate sits in `attribute()`; location extraction is broadened in the website fetcher plus a gazetteer expansion. No DB schema, backend, or UI changes.

**Tech Stack:** Python crawler; `selectolax` HTML parser; `re`-based curated lexicons/gazetteer. Tests: `cd crawler && ./.venv/Scripts/python.exe -m pytest -q` (no network, no DB).

## Global Constraints

- **Scope: crawler logic only.** No DB schema, no backend endpoints, no admin/public UI, no LLM.
- **Relevance gate is soft:** create an offer only if `classify(blob, TARGET_LEXICON)` is non-empty (audience keyword matched) — `blob = provider + site_name + text`.
- **Location priority:** structured metadata → address/contact region → offer text. Gazetteer is a **curated** expansion (word-boundary surface forms), precision over recall.
- **Telegram gate:** reject a telegram channel as provider if its handle is in the blocklist **OR** its name/handle matches the news/info lexicon.
- **Discount parsing:** remove the bare `"%"` offer trigger; an `N%` counts as a discount only with a discount-context word present; a price-increase block with no discount context is not an offer.
- **Preserve behaviour:** existing crawler tests stay green; curated matching stays word-boundary based.

---

### Task 1: UBD-relevance gate + audience lexicon (ДСНС/поліція)

**Files:**
- Modify: `crawler/crawler/discovery/lexicon.py` (extend `TARGET_LEXICON`)
- Modify: `crawler/crawler/extract/heuristic.py` (`extract()` gate)
- Test: `crawler/tests/test_lexicon.py`, `crawler/tests/test_heuristic.py`

**Interfaces:**
- Consumes: `classify(text, lexicon)`, `TARGET_LEXICON` (existing).
- Produces: `extract()` returns `None` when no target-audience keyword matches.

- [ ] **Step 1: Write the failing tests**

Append to `crawler/tests/test_lexicon.py`:

```python
def test_target_lexicon_covers_dsns_and_police():
    from crawler.discovery.lexicon import classify, TARGET_LEXICON
    got = {slug for _, slug in classify("знижка для рятувальників ДСНС", TARGET_LEXICON)}
    assert "dsns" in got
    got2 = {slug for _, slug in classify("акція для поліцейських", TARGET_LEXICON)}
    assert "police" in got2
```

Append to `crawler/tests/test_heuristic.py`:

```python
def test_offer_without_target_audience_is_skipped():
    ex = get_extractor("heuristic")
    # real discount phrase, but no "для кого" audience signal -> not a UBD offer
    assert ex.extract(_item("Знижка 20% на все у нашому магазині"), "Shop", CATS) is None


def test_offer_for_dsns_passes_gate():
    ex = get_extractor("heuristic")
    cand = ex.extract(_item("Знижка 15% для рятувальників ДСНС"), "Магазин", CATS)
    assert cand is not None
    assert cand.discount_type == "percent"
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_lexicon.py tests/test_heuristic.py -q`
Expected: FAIL — no `dsns`/`police` slugs; `Знижка 20% на все` currently returns a candidate (no gate yet).

- [ ] **Step 3: Extend `TARGET_LEXICON`**

In `crawler/crawler/discovery/lexicon.py`, add two entries at the end of the `TARGET_LEXICON` list (after the IDP `("Внутрішньо переміщена особа", "idp", ...)` entry, before the closing `]`):

```python
    ("Працівник ДСНС", "dsns", _compile((
        "дснс", "рятувальник", "надзвичайних ситуац", "пожежник"))),
    ("Поліцейський", "police", _compile((
        "поліц", "нацполіц", "національної поліції"))),
```

- [ ] **Step 4: Add the relevance gate in `extract()`**

In `crawler/crawler/extract/heuristic.py`, in `HeuristicExtractor.extract()`, the block that computes `target_slugs` currently reads:

```python
        blob = f"{provider} {item.site_name or ''} {text}".lower()
        target_slugs = {slug for _, slug in classify(blob, TARGET_LEXICON)}
        target_ids = [c["id"] for c in categories.target if c["slug"] in target_slugs]
```

Insert the gate immediately after `target_slugs` is assigned:

```python
        blob = f"{provider} {item.site_name or ''} {text}".lower()
        target_slugs = {slug for _, slug in classify(blob, TARGET_LEXICON)}
        if not target_slugs:
            return None
        target_ids = [c["id"] for c in categories.target if c["slug"] in target_slugs]
```

- [ ] **Step 5: Run the tests**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_lexicon.py tests/test_heuristic.py -q`
Expected: PASS. If any *pre-existing* `test_heuristic.py` test that expects a candidate now fails, it is because its input text lacks an audience keyword — add `для ветеранів` to that test's input text (this does not change what the test asserts about discount/location). Confirm which by reading the failure; all shipped inputs already contain `ветеранів`/`військових`, so none should need it.

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/discovery/lexicon.py crawler/crawler/extract/heuristic.py \
        crawler/tests/test_lexicon.py crawler/tests/test_heuristic.py
git commit -m "feat(crawler): UBD-relevance gate + ДСНС/поліція audience lexicon"
```

---

### Task 2: Stricter discount parsing

**Files:**
- Modify: `crawler/crawler/extract/heuristic.py`
- Test: `crawler/tests/test_heuristic.py`

**Interfaces:**
- Consumes: `extract()` (Task 1 gate already present).
- Produces: a bare percentage no longer creates an offer; price-increase news returns `None`.

- [ ] **Step 1: Write the failing tests**

Append to `crawler/tests/test_heuristic.py`:

```python
def test_price_increase_without_discount_returns_none():
    ex = get_extractor("heuristic")
    # has a structural trigger ("діє до") + audience ("ветеранів") but it's a price HIKE
    txt = "Подорожчання проїзду для ветеранів діє до 15 липня, буде 544 грн"
    assert ex.extract(_item(txt), "Новини", CATS) is None


def test_bare_percentage_is_not_an_offer():
    ex = get_extractor("heuristic")
    # a percentage + audience word, but NO discount trigger word at all
    assert ex.extract(_item("18% студентів-ветеранів мають знижений тариф"), "Новини", CATS) is None


def test_sale_percent_still_parsed():
    ex = get_extractor("heuristic")
    cand = ex.extract(_item("Розпродаж 50% для військових"), "Shop", CATS)
    assert cand is not None
    assert cand.discount_type == "percent"
    assert cand.discount_value == "50"
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_heuristic.py -q`
Expected: FAIL — the price-hike and bare-percentage texts currently produce candidates (`%` is still a trigger; no price-increase guard).

- [ ] **Step 3: Prune the trigger + add the guard/context regexes**

In `crawler/crawler/extract/heuristic.py`, change `_OFFER_TRIGGERS` to drop the bare `"%"`:

```python
# Any of these signals that the text is an offer at all.
_OFFER_TRIGGERS = (
    "знижк", "акці", "промокод", "безкоштов", "безплатн", "діє до",
    "спецпропоз", "розпродаж",
)
```

Add these module-level regexes next to `_PERCENT` (after line with `_PERCENT = ...`):

```python
_DISCOUNT_CTX = re.compile(r"знижк|акці|розпродаж|спецпропоз|промокод|економ|вигід|-\s*\d", re.IGNORECASE)
_INCREASE = re.compile(r"зростан|подорожч|підвищенн\w*\s+варт|дорожч|буде\s+[\d\s]+грн", re.IGNORECASE)
```

- [ ] **Step 4: Apply the guard and the percent-context rule in `extract()`**

In `HeuristicExtractor.extract()`, right after the offer-trigger gate:

```python
        text = item.text or ""
        low = text.lower()
        if not any(t in low for t in _OFFER_TRIGGERS):
            return None
        if _INCREASE.search(low) and not _DISCOUNT_CTX.search(low):
            return None
```

Then change the percent branch of the discount parse so a percentage only counts with discount context:

```python
        discount_type = None
        discount_value = None
        if _FREE.search(low):
            discount_type = "free"
        elif (m := _PERCENT.search(text)) and _DISCOUNT_CTX.search(low):
            discount_type, discount_value = "percent", m.group(1)
        elif (m := _FIXED.search(text)):
            discount_type, discount_value = "fixed", re.sub(r"\s", "", m.group(1))
```

- [ ] **Step 5: Run the tests**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_heuristic.py -q`
Expected: PASS (new tests pass; existing `test_percent_discount_parsed` still passes — "Знижка 20%" has `знижк` context; `test_free_offer_parsed` still passes — `безкоштов`).

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/extract/heuristic.py crawler/tests/test_heuristic.py
git commit -m "feat(crawler): stricter discount parse (drop bare %, require context, guard price hikes)"
```

---

### Task 3: Broaden location extraction + gazetteer

**Files:**
- Modify: `crawler/crawler/discovery/geo.py` (`_CITIES`)
- Modify: `crawler/crawler/fetchers/website.py` (`_extract_locality`)
- Test: `crawler/tests/test_geo.py`, `crawler/tests/test_website_fetcher.py`

**Interfaces:**
- Consumes: `find_city` (existing).
- Produces: `_extract_locality(tree)` also reads microdata + address/contact region; `find_city` knows more towns.

- [ ] **Step 1: Write the failing tests**

Append to `crawler/tests/test_geo.py`:

```python
def test_kyiv_agglomeration_towns():
    assert find_city("м. Вишневе, вул. Київська 1") == "Вишневе"
    assert find_city("наш заклад в Ірпені") == "Ірпінь"
    assert find_city("Бровари, просп. Незалежності") == "Бровари"
```

Append to `crawler/tests/test_website_fetcher.py`:

```python
def test_locality_from_microdata():
    from selectolax.parser import HTMLParser
    from crawler.fetchers.website import _extract_locality
    html = '<html><body><span itemprop="addressLocality">Київ</span></body></html>'
    assert _extract_locality(HTMLParser(html)) == "Київ"


def test_locality_from_contact_region():
    from selectolax.parser import HTMLParser
    from crawler.fetchers.website import _extract_locality
    html = ('<html><body><main><p>Знижка 15% для УБД</p></main>'
            '<footer><address>м. Вишневе, вул. Київська 1</address></footer>'
            '</body></html>')
    assert _extract_locality(HTMLParser(html)) == "Вишневе"
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_geo.py tests/test_website_fetcher.py -q`
Expected: FAIL — `Вишневе`/`Ірпінь`/`Бровари` not in gazetteer; `_extract_locality` returns `None` for microdata/contact-region cases.

- [ ] **Step 3: Expand the gazetteer**

In `crawler/crawler/discovery/geo.py`, add these entries to the `_CITIES` dict (place after the `"Біла Церква"` entry, before the closing `}`):

```python
    "Вишневе": ("вишневе", "вишневому", "вишневого"),
    "Ірпінь": ("ірпінь", "ірпені", "ірпеня"),
    "Буча": ("буча", "бучі", "бучанськ"),
    "Бровари": ("бровари", "броварах", "броварів"),
    "Бориспіль": ("бориспіль", "борисполі", "борисполя"),
    "Фастів": ("фастів", "фастові", "фастова"),
    "Вишгород": ("вишгород", "вишгороді", "вишгорода"),
    "Обухів": ("обухів", "обухові", "обухова"),
    "Славутич": ("славутич", "славутичі", "славутича"),
```

- [ ] **Step 4: Broaden `_extract_locality`**

In `crawler/crawler/fetchers/website.py`, add the geo import at the top (next to the other imports):

```python
from crawler.discovery.geo import find_city
```

Then, in `_extract_locality(tree)`, replace the final `return None` with microdata + contact-region fallbacks:

```python
    for css in ('meta[property="og:locality"]', 'meta[name="geo.placename"]'):
        node = tree.css_first(css)
        if node is not None and node.attributes.get("content"):
            return node.attributes["content"].strip()
    node = tree.css_first('[itemprop="addressLocality"]')
    if node is not None:
        txt = node.text(strip=True)
        if txt:
            return txt
    parts = []
    for css in ("address", "footer", '[class*="contact"]', '[id*="contact"]',
                '[class*="address"]', '[class*="footer"]'):
        for n in tree.css(css):
            t = n.text(separator=" ", strip=True)
            if t:
                parts.append(t)
    return find_city(" ".join(parts))
```

(The first `for css in (...og:locality...)` block already exists — keep it; only the trailing `return None` is replaced by the microdata + contact-region logic, which itself ends by returning `find_city(...)` or `None`.)

- [ ] **Step 5: Run the tests**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_geo.py tests/test_website_fetcher.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/discovery/geo.py crawler/crawler/fetchers/website.py \
        crawler/tests/test_geo.py crawler/tests/test_website_fetcher.py
git commit -m "feat(crawler): extract locality from microdata/contact region + expand gazetteer"
```

---

### Task 4: Telegram news/info channel gate

**Files:**
- Modify: `crawler/crawler/discovery/blocklist.py`
- Modify: `crawler/crawler/discovery/attribution.py`
- Test: `crawler/tests/test_blocklist.py`, `crawler/tests/test_attribution.py`

**Interfaces:**
- Consumes: `attribute()` telegram branch (existing).
- Produces: `is_blocked_telegram(handle, name) -> bool`; `attribute()` returns `None` for blocked telegram channels.

- [ ] **Step 1: Write the failing tests**

Append to `crawler/tests/test_blocklist.py`:

```python
def test_is_blocked_telegram_handle():
    from crawler.discovery.blocklist import is_blocked_telegram
    assert is_blocked_telegram("https://t.me/nau_info", "КАІ • Корисна інфа") is True
    assert is_blocked_telegram("t.me/nau_info", None) is True
    assert is_blocked_telegram("@nau_info", None) is True


def test_is_blocked_telegram_news_name():
    from crawler.discovery.blocklist import is_blocked_telegram
    assert is_blocked_telegram("t.me/somechan", "Львівські новини") is True
    assert is_blocked_telegram("t.me/uni_kai", "Університет — інфо для студентів") is True


def test_is_blocked_telegram_allows_business():
    from crawler.discovery.blocklist import is_blocked_telegram
    assert is_blocked_telegram("t.me/kava_lviv", "Кав'ярня Львів") is False
```

Append to `crawler/tests/test_attribution.py`:

```python
def test_telegram_news_channel_rejected():
    item = _item("Розклад пар та стипендії", url="https://t.me/nau_info/753")
    ctx = build_page_ctx(SourceCandidate(name="КАІ • Корисна інфа", type="telegram",
                                         url_or_handle="https://t.me/nau_info"), [item])
    assert attribute(item, ctx) is None


def test_telegram_business_channel_attributed():
    item = _item("Знижка 10% для УБД", url="https://t.me/kava_lviv")
    ctx = build_page_ctx(SourceCandidate(name="Кав'ярня Львів", type="telegram",
                                         url_or_handle="https://t.me/kava_lviv"), [item])
    a = attribute(item, ctx)
    assert a is not None
    assert a.suggest_type == "telegram"
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_blocklist.py tests/test_attribution.py -q`
Expected: FAIL — no `is_blocked_telegram`; telegram channels are always attributed today.

- [ ] **Step 3: Add the telegram blocklist helper**

In `crawler/crawler/discovery/blocklist.py`, add at the end of the file:

```python
_TELEGRAM_HANDLES = {"nau_info"}

_CHANNEL_NEWS_LEXICON = (
    "новини", "новостей", "інфо", "news", "info", "університет", "студент",
    "коледж", "абітурієнт", "розклад", "оголошення", "вступ",
)


def _tg_handle(raw: str | None) -> str:
    s = (raw or "").strip().lower().removeprefix("@")
    if "t.me/" in s:
        s = s.split("t.me/", 1)[1]
    return s.strip("/").split("/")[0].split("?")[0]


def is_blocked_telegram(handle: str | None, name: str | None) -> bool:
    if _tg_handle(handle) in _TELEGRAM_HANDLES:
        return True
    text = f"{handle or ''} {name or ''}".lower()
    return any(w in text for w in _CHANNEL_NEWS_LEXICON)
```

- [ ] **Step 4: Hook it into `attribute()`**

In `crawler/crawler/discovery/attribution.py`, change the import line:

```python
from crawler.discovery.blocklist import is_blocked_host, is_blocked_telegram
```

Then change the telegram branch of `attribute()` to reject blocked channels first:

```python
def attribute(item, ctx: PageCtx) -> Attribution | None:
    if ctx.cand_type == "telegram":
        if is_blocked_telegram(ctx.cand_url_or_handle, ctx.cand_name):
            return None
        provider = ctx.cand_name or ctx.cand_url_or_handle
        return Attribution(provider=provider, is_first_party=True,
                           suggest_type="telegram",
                           suggest_url_or_handle=ctx.cand_url_or_handle,
                           suggest_name=ctx.cand_name or provider)
```

- [ ] **Step 5: Run the tests + full crawler suite**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — whole crawler suite green (all four tasks' new tests pass; no regressions).

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/discovery/blocklist.py crawler/crawler/discovery/attribution.py \
        crawler/tests/test_blocklist.py crawler/tests/test_attribution.py
git commit -m "feat(crawler): gate telegram news/info channels out of provider attribution"
```

---

## Self-Review

**1. Spec coverage:**
- UBD-relevance gate (soft, `target_slugs`) + ДСНС/поліція lexicon → Task 1. ✔
- Location: microdata + contact-region scan + gazetteer (Вишневе) → Task 3. ✔
- Telegram gate: handle blocklist + news/info name heuristic, hooked in `attribute()` → Task 4. ✔
- Discount: drop bare `%` trigger, percent needs context, price-increase guard → Task 2. ✔
- Layering (news with military keyword caught by telegram/discount gates) → Tasks 2+4 backstop Task 1. ✔
- Out of scope (DB, endpoints, UI, LLM, full gazetteer, queue cleanup) → none added. ✔

**2. Placeholder scan:** No TBD/TODO; every code step shows full code. ✔

**3. Type consistency:** `classify(blob, TARGET_LEXICON)`, `find_city(text)`, `_extract_locality(tree)`, `is_blocked_telegram(handle, name)`, `_tg_handle(raw)` — names/signatures identical across tasks and tests. `extract()`/`attribute()` return `None` on gate failure, matching existing callers (runner/harvester already handle `None`). ✔

**Note on gazetteer ambiguity:** `"Вишневе"` also matches the neuter adjective "вишневе" (e.g. "вишневе варення"); scoped address/contact-region priority makes this rare, and it is accepted per precision-over-recall. Flag at final review if it surfaces on live data.

**Note on ДСНС/поліція target categories:** the lexicon extension makes their offers pass the gate; assigning a DB target category to them additionally requires those categories to exist in the DB (admin-seeded) — out of scope here.
