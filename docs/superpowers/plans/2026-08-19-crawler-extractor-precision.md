# Crawler Extractor Precision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kill three concrete extractor false positives — shareholder-homograph fixed prices, structural logo-alt providers, and about-page free offers — each with an isolated, validated fix.

**Architecture:** Three independent changes: a negative lookahead on `DISCOUNT_CTX` (promo_lexicon), a token-level structural skip in `_extract_logo_alt` (website fetcher), and an about-page URL guard on the FREE branch (heuristic extractor).

**Tech Stack:** Python 3, pytest, selectolax; MySQL via `docker exec`; Docker Compose.

## Global Constraints

- Ukrainian-only project: no Russian text in code/tests.
- Each fix is isolated and independently testable. No config, schema, backend, or wiring change.
- Run crawler tests from `crawler/`: `./.venv/Scripts/python.exe -m pytest ...`.
- Validated by execution (this session): `акці(?!онер)` excludes "акціонерні товариства"/"права акціонера", keeps "акція"/"акційна"/"акції"/"знижка".
- `_LOGO_IMG_SELECTORS` matches `<img class="logo">`; `OfferCandidate.discount_type ∈ {"percent","fixed","free",None}`; `RawItem(source_id, platform, key, text, url=...)`.
- DB password `MYSQL_ROOT_PASSWORD` in `.env`; DB `ubd`; container `ubd_probe-db-1`.

---

## File Structure

- Modify `crawler/crawler/discovery/promo_lexicon.py` — `DISCOUNT_CTX` regex.
- Modify `crawler/crawler/fetchers/website.py` — `_extract_logo_alt` + `_STRUCTURAL_ALT_TOKENS`.
- Modify `crawler/crawler/extract/heuristic.py` — `_is_info_page` helper + FREE-branch guard.
- Tests: `test_promo_lexicon.py`, `test_website_logo.py`, `test_heuristic.py`.

---

## Task 1: Discount-context homograph guard (fix A)

**Files:**
- Modify: `crawler/crawler/discovery/promo_lexicon.py:34-35`
- Test: `crawler/tests/test_promo_lexicon.py`

**Interfaces:**
- Produces: `promo_lexicon.DISCOUNT_CTX` no longer matches the "акціонер" family; still matches "акція"/"акційн"/"знижк".

- [ ] **Step 1: Write the failing test** — append to `crawler/tests/test_promo_lexicon.py`

```python
from crawler.discovery import promo_lexicon as _pl


def test_discount_ctx_excludes_shareholder_homograph():
    assert _pl.DISCOUNT_CTX.search("консультація юриста по акціонерні товариства") is None
    assert _pl.DISCOUNT_CTX.search("права акціонера") is None
    # real promo words still match
    assert _pl.DISCOUNT_CTX.search("акція для військових") is not None
    assert _pl.DISCOUNT_CTX.search("акційна ціна на все") is not None
    assert _pl.DISCOUNT_CTX.search("наші акції та знижки") is not None
    assert _pl.DISCOUNT_CTX.search("знижка 20%") is not None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_promo_lexicon.py -q`
Expected: FAIL — `DISCOUNT_CTX.search("...акціонерні товариства")` currently matches (bare `акці`), so the `is None` assert fails.

- [ ] **Step 3: Add the negative lookahead** — edit `crawler/crawler/discovery/promo_lexicon.py`

```python
DISCOUNT_CTX = re.compile(
    r"знижк|акці(?!онер)|розпродаж|спецпропоз|промокод|економ|вигід|-\s*\d",
    re.IGNORECASE)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_promo_lexicon.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/promo_lexicon.py crawler/tests/test_promo_lexicon.py
git commit -m "fix(crawler): DISCOUNT_CTX excludes акціонер homograph (fixed-price precision)"
```

---

## Task 2: Structural logo-alt skip (fix B)

**Files:**
- Modify: `crawler/crawler/fetchers/website.py:140-149`
- Test: `crawler/tests/test_website_logo.py`

**Interfaces:**
- Consumes: `_extract_logo_alt(tree)` (selectolax tree).
- Produces: `_extract_logo_alt` returns None for alts containing a structural token (logo/footer/header/template/starter/…); returns the alt for real brand names.

- [ ] **Step 1: Write the failing test** — append to `crawler/tests/test_website_logo.py`

```python
from crawler.fetchers.website import _extract_logo_alt


def test_logo_alt_skips_structural_and_template_labels():
    assert _extract_logo_alt(_p('<img class="logo" alt="Footer-logo">')) is None
    assert _extract_logo_alt(_p('<img class="logo" alt="wezom-starter-template">')) is None
    assert _extract_logo_alt(_p('<img class="logo" alt="logo">')) is None          # bare generic
    # real brand names survive (whole-token match, not substring)
    assert _extract_logo_alt(_p('<img class="logo" alt="Смартлаб">')) == "Смартлаб"
    assert _extract_logo_alt(_p('<img class="logo" alt="Home Comfort">')) == "Home Comfort"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_website_logo.py -q`
Expected: FAIL — "Footer-logo" / "wezom-starter-template" are not in the exact `_GENERIC_ALTS`, so `_extract_logo_alt` returns them instead of None.

- [ ] **Step 3: Add the structural-token skip** — edit `crawler/crawler/fetchers/website.py`, replacing the `_GENERIC_ALTS` block and `_extract_logo_alt`

```python
# Generic alts that are not a business name — never use them as the provider.
_GENERIC_ALTS = {"logo", "лого", "image", "img", "banner", "банер", "home", "головна"}
# Structural page-scaffold tokens: an alt containing any of these as a WHOLE token is a
# template/layout label ("footer-logo", "wezom-starter-template"), not a business name.
_STRUCTURAL_ALT_TOKENS = {"logo", "лого", "footer", "header", "template", "starter",
                          "placeholder", "default", "icon", "menu", "nav"}
_ALT_TOKEN_RE = re.compile(r"[^0-9a-zA-Zа-яА-ЯіїєґІЇЄҐ]+")


def _extract_logo_alt(tree) -> str | None:
    for css in _LOGO_IMG_SELECTORS:
        for node in tree.css(css):
            alt = (node.attributes.get("alt") or "").strip()
            if not alt:
                continue
            low = alt.lower()
            if low in _GENERIC_ALTS:
                continue
            if {t for t in _ALT_TOKEN_RE.split(low) if t} & _STRUCTURAL_ALT_TOKENS:
                continue                                   # structural/template label
            return _cap_tagline(alt)
    return None
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_website_logo.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/fetchers/website.py crawler/tests/test_website_logo.py
git commit -m "fix(crawler): skip structural/template logo-alt labels as provider"
```

---

## Task 3: About/info-page FREE suppression (fix C)

**Files:**
- Modify: `crawler/crawler/extract/heuristic.py` (add `_is_info_page`; guard the FREE branch ~line 109)
- Test: `crawler/tests/test_heuristic.py`

**Interfaces:**
- Consumes: `item.url` on the `RawItem`; the FREE branch in `HeuristicExtractor.extract`.
- Produces: FREE is not assigned when `item.url` is an about/info page; percent/fixed unaffected.

- [ ] **Step 1: Write the failing tests** — append to `crawler/tests/test_heuristic.py`

```python
def _item_url(text, url):
    return RawItem(source_id=1, platform="website", key="k", text=text, url=url)


def test_free_suppressed_on_about_page():
    ex = get_extractor("heuristic", require_discount=True)
    text = "Ми надаємо безкоштовну допомогу ветеранам та військовим"
    assert ex.extract(_item_url(text, "https://x.org/about-us"), "Shop", CATS) is None


def test_free_kept_on_offer_page():
    ex = get_extractor("heuristic", require_discount=True)
    text = "Ми надаємо безкоштовну допомогу ветеранам та військовим"
    cand = ex.extract(_item_url(text, "https://x.org/promo"), "Shop", CATS)
    assert cand is not None and cand.discount_type == "free"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_heuristic.py -q`
Expected: FAIL — `test_free_suppressed_on_about_page` currently returns a `free` offer (no about guard yet), so the `is None` assert fails.

- [ ] **Step 3: Add the info-page guard** — edit `crawler/crawler/extract/heuristic.py`

Add near the top (after imports / module constants):

```python
_INFO_PAGE_TOKENS = ("about", "pro-nas", "pro-proekt", "pro-kompani", "o-nas",
                     "o-kompani", "про-нас", "про-проєкт")


def _is_info_page(url) -> bool:
    return bool(url) and any(tok in url.lower() for tok in _INFO_PAGE_TOKENS)
```

Then guard the FREE branch (the `elif pl.FREE.search(...) and _has_audience_in_text(text):` line):

```python
        elif (pl.FREE.search(pl.FREE_SERVICE.sub(" ", low)) and _has_audience_in_text(text)
              and not _is_info_page(item.url)):
            # FREE only when it's not merely a complementary free service (masked above)
            # and not an about/info page (mission text trips the weak free-word signal).
            discount_type = "free"
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_heuristic.py -q`
Expected: PASS (both new tests + existing heuristic tests).

- [ ] **Step 5: Run the full crawler suite (no regressions)**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/extract/heuristic.py crawler/tests/test_heuristic.py
git commit -m "fix(crawler): suppress FREE offers on about/info pages"
```

---

## Task 4: Rollout — deploy + clean queue

**Files:** none in-repo.

- [ ] **Step 1: Rebuild + restart the crawler**

```bash
docker compose build crawler && docker compose up -d crawler
```

- [ ] **Step 2: Reject the three current false positives (#342, #343, #344)**

Confirm, then reject:

```bash
PW=$(grep -h '^MYSQL_ROOT_PASSWORD=' .env | cut -d= -f2-)
docker exec ubd_probe-db-1 mysql --default-character-set=utf8mb4 -uroot -p"$PW" ubd -e "
SELECT id,discount_type,provider,article_url_canonical FROM offers WHERE id IN (342,343,344);
UPDATE offers SET status='rejected' WHERE id IN (342,343,344) AND status='pending_review';
SELECT ROW_COUNT() AS rejected;"
```

Expected: the three rows are gospital about-us / b2bconsult price / sheriffua about; `rejected` = 3.

- [ ] **Step 3: Verify queue**

```bash
PW=$(grep -h '^MYSQL_ROOT_PASSWORD=' .env | cut -d= -f2-)
docker exec ubd_probe-db-1 mysql -uroot -p"$PW" ubd -e "SELECT status,COUNT(*) FROM offers GROUP BY status;"
```

Expected: `pending_review` dropped by 3. Remaining pending are #334 (shadow), #335 (leocard), #345/#346 (dom.ria) — out of this track's scope.

---

## Self-Review

**Spec coverage:**
- A DISCOUNT_CTX `акці(?!онер)` → Task 1. ✓
- B structural logo-alt skip → Task 2. ✓
- C about-page FREE suppression → Task 3. ✓
- No config/schema/backend/wiring → Global Constraints; all three isolated. ✓
- Rollout (rebuild + reject #342/#343/#344) → Task 4. ✓

**Placeholder scan:** none — code and commands concrete.

**Type consistency:** `DISCOUNT_CTX` is a compiled regex (`.search`). `_extract_logo_alt(tree) -> str | None`. `_is_info_page(url) -> bool`; `item.url` is `str | None`. `OfferCandidate.discount_type` values match the tests. Test helpers (`_p`, `_item`, `_item_url`, `get_extractor`, `CATS`) match each file's existing fixtures.
