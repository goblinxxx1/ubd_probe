# Extractor free-precision + provider=name — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the false-`free` noise (a free-trigger only counts when an audience term shares its block) and show the company/site name in the "who offers" (`provider`) field.

**Architecture:** Crawler-only, two edits to `crawler/crawler/extract/heuristic.py`. Each RawItem's `text` is one page block (`<article>/<li>/<p>`), so "audience in the same block" ≈ "same paragraph". Provider display switches to `item.site_name` while `content_hash`/classification stay on the host (no churn).

**Tech Stack:** Python, pytest. Run from `crawler/`: `./.venv/Scripts/python.exe -m pytest -q` (no DB).

## Global Constraints

- Crawler-only. TDD. Run from `crawler/`: `./.venv/Scripts/python.exe -m pytest -q`.
- `_has_audience_in_text(text)` = `bool(classify(text, TARGET_LEXICON))` — audience in the BLOCK PROSE, not provider/site_name. `classify`, `TARGET_LEXICON`, `pl` are already imported (heuristic.py:43,45).
- Free branch becomes `if pl.FREE.search(low) and _has_audience_in_text(text):`; on failure it must fall through to the existing `elif` percent/fixed chain (do NOT early-return).
- The whole-offer audience gate (heuristic.py:116-118, over `blob`) stays unchanged. The offer's `target_category_ids` still come from `blob`.
- Provider display: `display_provider = (item.site_name or "").strip() or provider`; set `OfferCandidate(provider=display_provider, ...)`. **`content_hash(promo_title, provider, text)` and the `blob` classification MUST keep using the `provider` param (the host)** — no churn.
- Do not touch percent/fixed detection, `require_discount`, or any other field.

---

### Task 1: Free-proximity gate (audience must share the block)

**Files:**
- Modify: `crawler/crawler/extract/heuristic.py`
- Test: `crawler/tests/test_heuristic.py`

**Interfaces:**
- Produces: module helper `_has_audience_in_text(text: str) -> bool`. The free branch of `extract` gains the `and _has_audience_in_text(text)` guard.

- [ ] **Step 1: Write the failing tests**

Append to `crawler/tests/test_heuristic.py` (it has `CATS = CategoryIndex(...)`, `_item(text)` → RawItem with only text, and `ex`/`get_extractor("heuristic")`):
```python
def test_free_rejected_when_audience_only_in_provider_not_text():
    from crawler.extract import get_extractor
    from crawler.models import RawItem
    ex = get_extractor("heuristic")
    # free word in the block text, but the audience token is only in provider/site_name,
    # not in the block prose -> free must NOT count -> no discount -> None (require_discount).
    it = RawItem(source_id=1, platform="website", key="k",
                 text="Безкоштовна доставка по всій Україні. Умови доставки та оплати.",
                 site_name="Магазин для ветеранів")
    # free word in text, NO audience/percent/fixed in text; audience only in site_name/provider
    assert ex.extract(it, "Магазин для ветеранів", CATS) is None


def test_free_kept_when_audience_in_same_block_text():
    from crawler.extract import get_extractor
    ex = get_extractor("heuristic")
    cand = ex.extract(_item("Безкоштовні протези ветеранам у нашій клініці"), "Клініка", CATS)
    assert cand is not None and cand.discount_type == "free"


def test_free_fails_but_percent_with_context_still_extracts():
    from crawler.extract import get_extractor
    ex = get_extractor("heuristic")
    # generic free (no audience token in the block text) + a real percent discount; audience
    # comes from the provider (offer-level gate over blob) -> free fails, falls through to percent.
    from crawler.models import RawItem
    it = RawItem(source_id=1, platform="website", key="k",
                 text="Безкоштовна доставка. Знижка 20% на все у нашому магазині.")
    cand = ex.extract(it, "Магазин для військових", CATS)
    assert cand is not None and cand.discount_type == "percent" and cand.discount_value == "20"
```

- [ ] **Step 2: Run to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_heuristic.py -k "free_rejected_when_audience_only or free_fails_but_percent"`
Expected: FAIL — currently free counts regardless of in-text audience (`test_free_rejected...` returns a candidate; `test_free_fails_but_percent...` returns discount_type="free" not "percent").

- [ ] **Step 3: Implement the gate**

In `crawler/crawler/extract/heuristic.py`, add a module-level helper (near the other `_`-helpers, above the class):
```python
def _has_audience_in_text(text: str) -> bool:
    """True iff a TARGET (audience) term appears in the block prose itself —
    not merely in provider/site_name metadata. Gates the loose FREE trigger."""
    return bool(classify(text or "", TARGET_LEXICON))
```
Change the free branch (currently `if pl.FREE.search(low):`) to:
```python
        if pl.FREE.search(low) and _has_audience_in_text(text):
            discount_type = "free"
```
Leave the `elif` percent/fixed branches and everything else unchanged (a failed free now naturally falls into the `elif` chain).

- [ ] **Step 4: Run to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_heuristic.py`
Expected: PASS (existing `test_free_offer_for_military` — "Безкоштовно для військових!" — still passes: free+audience share the text).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/extract/heuristic.py crawler/tests/test_heuristic.py
git commit -m "feat(crawler): free counts only when audience shares the block (precision)"
```

---

### Task 2: `provider` display = company/site name

**Files:**
- Modify: `crawler/crawler/extract/heuristic.py`
- Test: `crawler/tests/test_heuristic.py`

**Interfaces:**
- Consumes: `item.site_name` (already populated by the website fetcher).
- Produces: `OfferCandidate.provider = item.site_name or <host param>`; `content_hash`/`blob` unchanged (host).

- [ ] **Step 1: Write the failing tests**

Append to `crawler/tests/test_heuristic.py`:
```python
def test_provider_uses_site_name_when_present():
    from crawler.extract import get_extractor
    from crawler.models import RawItem
    ex = get_extractor("heuristic")
    it = RawItem(source_id=1, platform="website", key="k",
                 text="Знижка 20% для ветеранів", site_name="Гастро-бар Угловой")
    cand = ex.extract(it, "uglovoy.com.ua", CATS)   # host passed as provider param
    assert cand is not None and cand.provider == "Гастро-бар Угловой"


def test_provider_falls_back_to_host_without_site_name():
    from crawler.extract import get_extractor
    ex = get_extractor("heuristic")
    cand = ex.extract(_item("Знижка 20% для ветеранів"), "uglovoy.com.ua", CATS)  # no site_name
    assert cand is not None and cand.provider == "uglovoy.com.ua"


def test_content_hash_unchanged_when_only_display_provider_differs():
    from crawler.extract import get_extractor
    from crawler.models import RawItem
    ex = get_extractor("heuristic")
    text = "Знижка 20% для ветеранів"
    with_name = ex.extract(RawItem(source_id=1, platform="website", key="k",
                                   text=text, site_name="Гастро-бар Угловой"), "uglovoy.com.ua", CATS)
    no_name = ex.extract(_item(text), "uglovoy.com.ua", CATS)
    assert with_name.content_hash == no_name.content_hash   # hash on host, not display name
```

- [ ] **Step 2: Run to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_heuristic.py -k "provider_uses_site_name or content_hash_unchanged"`
Expected: FAIL — currently `provider` is the host param, so `test_provider_uses_site_name` fails (provider == "uglovoy.com.ua", not the name).

- [ ] **Step 3: Implement**

In `extract`, just before the `return OfferCandidate(...)`, add:
```python
        display_provider = (item.site_name or "").strip() or provider
```
In the `OfferCandidate(...)` construction, change `provider=provider,` to `provider=display_provider,`.
Leave `content_hash=content_hash(promo_title, provider, text)` and the `blob = f"{provider} ..."` line unchanged (they keep using the host `provider` param → no churn).

- [ ] **Step 4: Run to verify they pass + full suite**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_heuristic.py` then `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS. Note: `test_offer_category_from_site_name_context` (heuristic.py test with `site_name="Барбершоп Резервіст"`, provider="Shop") now yields `provider="Барбершоп Резервіст"` — confirm that test does NOT assert `provider == "Shop"` (it asserts offer category); if it does assert provider, update that assertion to the site_name value.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/extract/heuristic.py crawler/tests/test_heuristic.py
git commit -m "feat(crawler): offer provider display = company/site name (site_name)"
```

---

### Task 3: Full suite + brief live check

**Files:** none (verification).

- [ ] **Step 1: Full crawler suite**

Run (from `crawler/`): `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS, 0 failures.

- [ ] **Step 2: Canonical rebuild crawler (deploy)**

```bash
docker compose --profile crawler build crawler && docker compose --profile crawler up -d crawler
```
Expected: build ok, crawler runs without tracebacks.

- [ ] **Step 3: Report** the test count and that new offers will carry a site-name provider + drop generic-free noise.

---

## Self-Review notes
- **Spec coverage:** Component 1 (free gate) → Task 1; Component 2 (provider=name) → Task 2; churn-guard verified by `test_content_hash_unchanged...`.
- **No placeholders:** every step shows exact code.
- **Type consistency:** `_has_audience_in_text(text)`, `display_provider`, `content_hash(..., provider, ...)` consistent; provider param stays the host for hash/blob throughout.
