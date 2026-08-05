# FIXED-branch Discount-Context Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the FIXED discount branch from misreading a bare price/donation amount as a fixed discount, by gating it on `DISCOUNT_CTX` (mirroring PERCENT).

**Architecture:** Add one boolean condition (`and pl.DISCOUNT_CTX.search(low)`) to the `elif` for the FIXED branch in `HeuristicExtractor.extract`. No other logic changes. TDD.

**Tech Stack:** Python, pytest. Crawler package (`crawler/`).

## Global Constraints

- Crawler-only. Single edit in `crawler/crawler/extract/heuristic.py` (the FIXED `elif`, line ~103).
- Do NOT touch the free branch, percent branch, `require_discount` handling, the global audience gate (line ~123), `_FIXED`/`_PERCENT` regexes, or `content_hash` derivation.
- Gate mirrors PERCENT exactly: `and pl.DISCOUNT_CTX.search(low)` (page-level, not block-level).
- Run tests from `crawler/` with `.venv/Scripts/python.exe -m pytest -q`.
- Commit trailer: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## File Structure

- Modify: `crawler/crawler/extract/heuristic.py:103` — add `and pl.DISCOUNT_CTX.search(low)` to the FIXED `elif`.
- Test: `crawler/tests/test_heuristic.py` — add gate tests (helpers already present: `CATS`, `_item`, `get_extractor`, `HeuristicExtractor`, `_target_cats`).

---

### Task 1: Gate the FIXED branch on DISCOUNT_CTX

**Files:**
- Modify: `crawler/crawler/extract/heuristic.py:103`
- Test: `crawler/tests/test_heuristic.py` (append tests)

**Interfaces:**
- Consumes: `HeuristicExtractor(require_discount: bool = False).extract(item: RawItem, provider: str, categories: CategoryIndex) -> OfferCandidate | None`; module globals `pl.DISCOUNT_CTX`, `_FIXED` (existing).
- Produces: no new symbols — only tighter FIXED classification.

- [ ] **Step 1: Write the failing tests**

Append to `crawler/tests/test_heuristic.py` (helpers `CATS`, `_item`, `get_extractor`, `HeuristicExtractor` are already imported/defined in this file):

```python
def test_fixed_with_context_still_emitted():
    ex = HeuristicExtractor(require_discount=True)
    res = ex.extract(_item("Знижка 500 грн для ветеранів на послуги"), "Shop", CATS)
    assert res is not None
    assert res.discount_type == "fixed" and res.discount_value == "500"


def test_fixed_minus_sign_style_emitted():
    ex = HeuristicExtractor(require_discount=True)
    res = ex.extract(_item("Розпродаж -500 грн для військових"), "Shop", CATS)
    assert res is not None
    assert res.discount_type == "fixed" and res.discount_value == "500"


def test_fixed_price_without_context_dropped_when_required():
    # trigger "тільки сьогодні" (not DISCOUNT_CTX) + price 2000 грн + audience -> a PRICE, not a discount
    ex = HeuristicExtractor(require_discount=True)
    res = ex.extract(_item("Тільки сьогодні! Куртка 2000 грн для ветеранів"), "Shop", CATS)
    assert res is None


def test_fixed_price_without_context_permissive_emits_no_discount():
    # permissive default: offer still emitted, but the bare price is no longer a fixed discount
    ex = HeuristicExtractor()  # require_discount=False
    res = ex.extract(_item("Тільки сьогодні! Куртка 2000 грн для ветеранів"), "Shop", CATS)
    assert res is not None
    assert res.discount_type is None
```

- [ ] **Step 2: Run the new tests to verify they fail**

From `crawler/`:
```bash
.venv/Scripts/python.exe -m pytest tests/test_heuristic.py -q -k "fixed_price_without_context or fixed_minus_sign or fixed_with_context"
```
Expected: `test_fixed_price_without_context_dropped_when_required` FAILS (currently emits fixed=2000, not None) and `test_fixed_price_without_context_permissive_emits_no_discount` FAILS (currently discount_type=="fixed"). The two "still emitted" tests should already PASS.

- [ ] **Step 3: Add the DISCOUNT_CTX gate to the FIXED branch**

In `crawler/crawler/extract/heuristic.py`, edit the FIXED `elif` (line ~103):

```python
        elif (m := _FIXED.search(text)) and pl.DISCOUNT_CTX.search(low):
            discount_type, discount_value = "fixed", re.sub(r"\s", "", m.group(1))
```

(Only the `elif` line changes — add `and pl.DISCOUNT_CTX.search(low)`. The body line is unchanged.)

- [ ] **Step 4: Run the new tests to verify they pass**

```bash
.venv/Scripts/python.exe -m pytest tests/test_heuristic.py -q -k "fixed_price_without_context or fixed_minus_sign or fixed_with_context"
```
Expected: 4 passed.

- [ ] **Step 5: Run the full crawler suite (regression)**

```bash
.venv/Scripts/python.exe -m pytest -q
```
Expected: all pass (previous 549 + 4 new = 553). Confirm no regression — especially `test_extractor_hryven_full_form_gives_fixed`, `test_round_hryvnia_price_not_misread_as_free` (both have "Знижка …" → DISCOUNT_CTX present → still emit), and `test_percent_discount_parsed` / `test_free_offer_parsed`. If anything else fails, inspect: a legit fixed test lacking a DISCOUNT_CTX word would need its text corrected (it was relying on the ungated branch).

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/extract/heuristic.py crawler/tests/test_heuristic.py
git commit -m "feat(crawler): gate FIXED discount branch on DISCOUNT_CTX

The FIXED branch matched any грн amount with no gate, so a bare price or
donation (2000 грн) was misread as a fixed discount. Mirror PERCENT: only
treat an amount as a fixed discount when discount context is present
(знижка / -500 / економія / розпродаж). Completes free/percent/fixed
gating symmetry. content_hash derives from title/provider/text (not the
discount), so existing offers do not re-hash.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Ledger, RESUME, memory, merge + deploy

**Files:**
- Modify: `.superpowers/sdd/progress.md` (gitignored — local ledger)
- Modify: `docs/RESUME.md`
- Create/Modify: memory `ubd-crawler-fixed-context-gate.md` + `MEMORY.md` pointer

- [ ] **Step 1: Append track entry to `.superpowers/sdd/progress.md`** (branch, root, the one-line change, tests count).

- [ ] **Step 2: Add RESUME `#37` section** in the existing format (what/why/gate/tests/commits).

- [ ] **Step 3: Write memory** `C:\Users\goblin\.claude\projects\D--ubd-probe\memory\ubd-crawler-fixed-context-gate.md` (type: project): FIXED branch now gated on DISCOUNT_CTX mirroring PERCENT; price ≠ discount; permissive not byte-eq (mirrors #35); links `[[ubd-crawler-free-precision-provider-name]]`, `[[ubd-crawler-extractor-precision]]`. Add `MEMORY.md` pointer line.

- [ ] **Step 4: Commit docs** (`docs/RESUME.md` only; progress.md is gitignored):

```bash
git add docs/RESUME.md
git commit -m "docs: RESUME #37 — FIXED-branch discount-context gate

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 5: Finish branch** — ff-merge `track-fixed-context` → `main`, delete branch, canonical rebuild of the crawler container (`docker compose build crawler` + `up -d crawler`), verify clean start / no tracebacks, confirm gate live in image. Push per user decision.

---

## Self-Review

**Spec coverage:**
- DISCOUNT_CTX gate on FIXED (mirror PERCENT) → Task 1 Step 3. ✓
- fixed+context still emitted → tests 1 & 2. ✓
- fixed price without context dropped (prod) → test 3. ✓
- permissive emits without spurious discount (not byte-eq) → test 4. ✓
- percent/free unchanged → Task 1 Step 5 regression (existing tests). ✓
- churn-guard (content_hash unchanged) → not separately tested; guaranteed because the edit doesn't touch content_hash derivation (line 145), stated in commit + spec. ✓
- Trade-offs (bonus/cashback, page-level) → design decisions, no code needed. ✓

**Placeholder scan:** No TBD/TODO; every code step shows full code. Task 1 Step 5 gives a concrete recipe if an unexpected failure appears. ✓

**Type consistency:** `HeuristicExtractor(require_discount=...)`, `.extract(item, provider, CATS)`, `_item(text)`, `CATS` all match the existing test file's definitions; `res.discount_type` / `res.discount_value` match `OfferCandidate` fields used elsewhere in the file. ✓
