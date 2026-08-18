# Promo-Offer Dedup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the moderation queue filling with the same promo re-scraped (differently worded) from other pages of a host that already has an offer.

**Architecture:** Replace the exact-label match in `create_offer` branch 3c with **same host + discount-magnitude subset + token-set (Jaccard) text similarity ≥ threshold**, include pending shadows as dedup targets, and compare the full discount set. A DB-free `dedup.py` module holds the pure logic. A one-off script collapses the already-queued duplicates.

**Tech Stack:** Python 3.12, SQLAlchemy, pytest, pydantic-settings.

## Global Constraints

- Backend tests from `backend/`: `./.venv/Scripts/python.exe -m pytest -q` (needs `mysql-container` on :3306).
- TDD: failing test first, minimal impl, green, commit.
- Conservative dedup: doubt → keep separate. Threshold default **0.6**, tunable via `settings.dedup_text_similarity_threshold`.
- Text compared = `description` + all discount `label`s. NOT `title` (business tagline, identical across a host's pages).
- Existing `tests/test_offer_banner_dedup.py` MUST stay green — it is the regression guard.
- No schema change / no migration.

---

### Task 1: Pure dedup module `app/crud/dedup.py`

**Files:**
- Create: `backend/app/crud/dedup.py`
- Test: `backend/tests/test_dedup.py`

**Interfaces:**
- Produces:
  - `normalize_tokens(text: str | None) -> frozenset[str]`
  - `text_similarity(a: frozenset, b: frozenset) -> float`
  - `discount_magnitudes(discounts, dt, dv) -> frozenset[tuple]`
  - `is_duplicate_promo(a_text, a_mags, b_text, b_mags, threshold: float) -> bool`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_dedup.py`:

```python
from decimal import Decimal
from types import SimpleNamespace

from app.crud.dedup import (normalize_tokens, text_similarity,
                            discount_magnitudes, is_duplicate_promo)
from app.models.enums import DiscountType


def test_normalize_tokens_drops_stopwords_and_punctuation():
    toks = normalize_tokens("Знижка 15% для військових!")
    assert {"знижка", "15", "військових"} <= toks
    assert "для" not in toks


def test_normalize_tokens_empty():
    assert normalize_tokens("") == frozenset()
    assert normalize_tokens(None) == frozenset()


def test_text_similarity_identical_and_disjoint():
    a = normalize_tokens("знижка військовим на послуги")
    assert text_similarity(a, a) == 1.0
    b = normalize_tokens("безкоштовна кава студентам")
    assert text_similarity(a, b) == 0.0


def test_text_similarity_paraphrase_above_half():
    a = normalize_tokens("знижка 15% військовим на всі послуги клініки")
    b = normalize_tokens("військовим знижка 15% на послуги нашої клініки")
    assert text_similarity(a, b) > 0.6


def test_discount_magnitudes_multi_and_fallback():
    d1 = SimpleNamespace(discount_type=DiscountType.percent, discount_value=Decimal("30"))
    d2 = SimpleNamespace(discount_type=DiscountType.percent, discount_value=Decimal("50"))
    assert discount_magnitudes([d1, d2], None, None) == frozenset({
        (DiscountType.percent, Decimal("30")), (DiscountType.percent, Decimal("50"))})
    assert discount_magnitudes([], DiscountType.percent, Decimal("15")) == frozenset({
        (DiscountType.percent, Decimal("15"))})


def test_is_duplicate_promo_subset_similar_true():
    p = frozenset({(DiscountType.percent, Decimal("30"))})
    both = frozenset({(DiscountType.percent, Decimal("30")), (DiscountType.percent, Decimal("50"))})
    a = normalize_tokens("знижка 30% військовим на меблі")
    b = normalize_tokens("військовим 30% знижка на меблі магазину")
    assert is_duplicate_promo(a, p, b, both, 0.6) is True


def test_is_duplicate_promo_same_percent_different_text_false():
    p = frozenset({(DiscountType.percent, Decimal("10"))})
    a = normalize_tokens("знижка 10% військовим на меблі")
    c = normalize_tokens("знижка 10% студентам на каву")
    assert is_duplicate_promo(a, p, c, p, 0.6) is False


def test_is_duplicate_promo_superset_false():
    p = frozenset({(DiscountType.percent, Decimal("30"))})
    both = frozenset({(DiscountType.percent, Decimal("30")), (DiscountType.percent, Decimal("50"))})
    a = normalize_tokens("знижки військовим 30% та ветеранам 50%")
    b = normalize_tokens("військовим знижка 30% на все")
    # a offers extra 50% not in b -> not a duplicate of b
    assert is_duplicate_promo(a, both, b, p, 0.6) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_dedup.py -q`
Expected: FAIL — `ModuleNotFoundError: app.crud.dedup`.

- [ ] **Step 3: Write the module**

Create `backend/app/crud/dedup.py`:

```python
"""Pure, DB-free helpers for detecting duplicate promo offers across pages of one host.

Two crawler offers describe the SAME promo when one's discount magnitudes are a subset of
the other's AND their promo text is similar enough — even when worded differently on
different pages (apex, /pro-nas, /category). Text similarity is token-set Jaccard; the
threshold is deliberately conservative (doubt -> keep separate).
"""
import re

# Малий курований укр. стоп-лист: службові слова без промо-змісту.
_STOPWORDS = frozenset({
    "для", "на", "та", "і", "й", "з", "зі", "у", "в", "що", "як", "до",
    "від", "по", "за", "є", "а", "або", "при", "не", "the", "a",
})

_TOKEN_RE = re.compile(r"[^\w]+", re.UNICODE)


def normalize_tokens(text):
    """Lowercase, strip punctuation, drop stopwords -> a set of content tokens."""
    if not text:
        return frozenset()
    return frozenset(w for w in _TOKEN_RE.split(text.lower())
                     if w and w not in _STOPWORDS)


def text_similarity(a, b):
    """Jaccard similarity of two token sets. Empty-vs-anything -> 0.0 (not a match)."""
    if not a or not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def discount_magnitudes(discounts, dt, dv):
    """Set of (discount_type, discount_value) across all of an offer's discounts.
    Falls back to the single top-level (dt, dv) when the discount list is empty."""
    mags = set()
    for d in discounts or []:
        t = getattr(d, "discount_type", None)
        if t is not None:
            mags.add((t, getattr(d, "discount_value", None)))
    if not mags and dt is not None:
        mags.add((dt, dv))
    return frozenset(mags)


def is_duplicate_promo(a_text, a_mags, b_text, b_mags, threshold):
    """True when b already covers a's discounts (a_mags subset of b_mags) AND the two
    promo texts are similar enough. Subset because the candidate must cover everything
    the new offer proposes; text is the decisive guard against collapsing two genuinely
    different offers of the same percentage."""
    if not a_mags or not a_mags <= b_mags:
        return False
    return text_similarity(a_text, b_text) >= threshold
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_dedup.py -q`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/crud/dedup.py backend/tests/test_dedup.py
git commit -m "feat(backend): pure promo-dedup helpers (normalize/jaccard/magnitudes)"
```

---

### Task 2: Rewire `create_offer` branch 3c to use similarity dedup

**Files:**
- Modify: `backend/app/core/config.py` (add setting)
- Modify: `backend/app/crud/offer.py` (imports, `_promo_text` helper, branch 3c at lines 246-264)
- Test: `backend/tests/test_offer_promo_dedup.py`

**Interfaces:**
- Consumes: `normalize_tokens`, `discount_magnitudes`, `is_duplicate_promo` from Task 1; `settings.dedup_text_similarity_threshold`.
- Produces: `_promo_text(obj) -> str` in `offer.py`; new branch-3c behavior (returns an existing offer when the incoming one is a duplicate promo; otherwise falls through to INSERT).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_offer_promo_dedup.py`:

```python
from app.crud import offer as offer_crud
from app.models.enums import CreatedBy, OfferStatus
from app.schemas.offer import OfferCreate


def _offer(article, *, host, desc, val="15", label=None, discounts=None, title="Бізнес"):
    if discounts is None:
        discounts = [{"discount_type": "percent", "discount_value": val, "label": label}]
    return OfferCreate(
        type="discount", title=title, provider="P", description=desc,
        discount_type=discounts[0]["discount_type"],
        discount_value=discounts[0].get("discount_value"),
        discounts=discounts,
        site_url=f"https://{host}", article_url=f"https://{host}{article}",
        target_url=f"https://{host}{article}")


def _cr(db, data, status=OfferStatus.pending_review, source_id=None):
    return offer_crud.create_offer(db, data, CreatedBy.crawler, status, source_id=source_id)


def test_reworded_same_promo_on_other_page_collapses(db_session):
    a = _cr(db_session, _offer("/", host="edclinic.com.ua",
            desc="Знижка 15% військовим на всі медичні послуги клініки", label="15% військовим"),
            status=OfferStatus.published)
    b = _cr(db_session, _offer("/pro-nas", host="edclinic.com.ua",
            desc="Військовим знижка 15% на послуги нашої медичної клініки", label="для захисників"))
    assert b.id == a.id


def test_same_percent_different_promo_stays_separate(db_session):
    a = _cr(db_session, _offer("/kava", host="cafe.com.ua", val="10",
            desc="Знижка 10% на каву студентам", label="10% кава"))
    b = _cr(db_session, _offer("/strizhka", host="cafe.com.ua", val="10",
            desc="Знижка 10% на стрижку військовим", label="10% стрижка"))
    assert a.id != b.id


def test_new_offer_collapses_onto_pending_shadow(db_session):
    pub = _cr(db_session, _offer("/aktsiyi", host="dentalstudio.ck.ua", val="10",
              desc="Знижка 10% пенсіонерам клініки", label="10%"),
              status=OfferStatus.published, source_id=23)
    shadow = _cr(db_session, _offer("/aktsiyi", host="dentalstudio.ck.ua", val="15",
                 desc="Знижка 15% для військових Dental Studio", label="знижка 15% для військових"),
                 source_id=23)
    assert shadow.supersedes_offer_id == pub.id
    dup = _cr(db_session, _offer("/pro-nas", host="dentalstudio.ck.ua", val="15",
              desc="Dental Studio знижка 15% для військових", label="знижка 15% для військових"),
              source_id=23)
    assert dup.id == shadow.id


def test_multi_discount_subset_collapses(db_session):
    pub = _cr(db_session, _offer("/aktsii", host="tovpollar.org",
              desc="Знижки військовим 30% та ветеранам 50% на продукцію",
              discounts=[{"discount_type": "percent", "discount_value": "30", "label": "30% військовим"},
                         {"discount_type": "percent", "discount_value": "50", "label": "50% ветеранам"}]),
              status=OfferStatus.published, source_id=20)
    b = _cr(db_session, _offer("/pro-nas", host="tovpollar.org",
            desc="Знижки військовим 30% на продукцію ветеранам",
            discounts=[{"discount_type": "percent", "discount_value": "30", "label": "30% військовим"}]),
            source_id=20)
    assert b.id == pub.id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_offer_promo_dedup.py -q`
Expected: FAIL — `test_reworded_...`, `test_new_offer_collapses_onto_pending_shadow`, `test_multi_discount_subset_collapses` fail (current 3c needs exact label / excludes shadows / primary-only). `test_same_percent_different_promo_stays_separate` may already pass.

- [ ] **Step 3: Add the config setting**

In `backend/app/core/config.py`, add inside `class Settings` (after `crawler_api_key`):

```python
    dedup_text_similarity_threshold: float = 0.6
```

- [ ] **Step 4: Add imports + `_promo_text` in `offer.py`**

At the top of `backend/app/crud/offer.py`, after the existing `from app.models.enums import ...` line, add:

```python
from app.core.config import settings
from app.crud.dedup import normalize_tokens, discount_magnitudes, is_duplicate_promo
```

Immediately after the `_primary_disc_sig` function (ends ~line 85), add:

```python
def _promo_text(obj) -> str:
    """Text identifying a promo: its discount paragraph plus all discount labels.
    Excludes title (business tagline, identical across a host's pages)."""
    parts = [getattr(obj, "description", None) or ""]
    for d in (getattr(obj, "discounts", None) or []):
        lbl = getattr(d, "label", None)
        if lbl:
            parts.append(lbl)
    return " ".join(parts)
```

- [ ] **Step 5: Replace branch 3c**

In `backend/app/crud/offer.py`, replace the whole branch-3c block (currently lines 246-264, the `if crawler and not blocked and data.discount_type is not None:` block using `_primary_disc_sig`) with:

```python
    # 3c) Same-promo dedup (host + discount-magnitude subset + text similarity). One promo
    #     appears on many pages worded differently (apex, /pro-nas, /category, /promotions);
    #     exact-label matching missed the reworded copies. Collapse when an existing live
    #     crawler offer from the SAME host already covers this offer's magnitudes and its
    #     promo text is similar enough. Shadows are INCLUDED as targets, so a new page's
    #     offer collapses onto an in-flight shadow of the same promo. Conservative: below the
    #     threshold the offers stay distinct (two real same-% offers survive).
    if crawler and not blocked and data.discount_type is not None:
        host = _source_host(getattr(data, "site_url", None)) or _source_host(getattr(data, "article_url", None))
        new_text = normalize_tokens(_promo_text(data))
        new_mags = discount_magnitudes(getattr(data, "discounts", None),
                                       data.discount_type, data.discount_value)
        if host and new_mags:
            threshold = settings.dedup_text_similarity_threshold
            cands = (db.query(Offer)
                     .filter(Offer.created_by == CreatedBy.crawler,
                             Offer.status != OfferStatus.expired)
                     .order_by(Offer.id).all())
            for c in cands:
                c_host = _source_host(c.site_url) or _source_host(c.article_url)
                if c_host != host:
                    continue
                c_mags = discount_magnitudes(c.discounts, c.discount_type, c.discount_value)
                if is_duplicate_promo(new_text, new_mags, c_text := normalize_tokens(_promo_text(c)),
                                      c_mags, threshold):
                    c.last_seen_at = datetime.utcnow()
                    db.commit()
                    db.refresh(c)
                    return c
```

- [ ] **Step 6: Run the new tests + the banner regression guard**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_offer_promo_dedup.py tests/test_offer_banner_dedup.py -q`
Expected: PASS (all). If `test_same_value_different_label_stays_separate` (lunch/dinner 10%) fails, the threshold is too low — confirm 0.6 and that `_promo_text` uses labels only when description is empty.

- [ ] **Step 7: Run the full backend suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS (no regressions in discovered-dedup, autoreject, freshness, internal).

- [ ] **Step 8: Commit**

```bash
git add backend/app/core/config.py backend/app/crud/offer.py backend/tests/test_offer_promo_dedup.py
git commit -m "feat(backend): promo dedup by host+magnitude+text similarity (branch 3c)"
```

---

### Task 3: One-off queue cleanup script `app/dedup_queue.py`

**Files:**
- Create: `backend/app/dedup_queue.py`
- Test: `backend/tests/test_dedup_queue_script.py`

**Interfaces:**
- Consumes: `normalize_tokens`, `discount_magnitudes`, `is_duplicate_promo` (Task 1); `_source_host`, `_promo_text` (Task 2); `settings.dedup_text_similarity_threshold`.
- Produces: `find_duplicates(db, threshold) -> list[tuple[int, int]]` returning `(dup_id, keep_id)` pairs; `main()` CLI (dry-run default, `--apply` rejects).

Follows the flat-script convention of `app/seed.py` / `app/demo_seed.py` (run as `python -m app.dedup_queue`), a small path deviation from the spec's `app/scripts/` for consistency with the existing scripts.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_dedup_queue_script.py`:

```python
from decimal import Decimal

from app.dedup_queue import find_duplicates
from app.models import Offer, OfferDiscount
from app.models.enums import CreatedBy, OfferStatus, DiscountType, OfferType


def _raw(db, article, host, desc, val="15", label="x"):
    o = Offer(type=OfferType.discount, title="T", description=desc, provider="P",
              discount_type=DiscountType.percent, discount_value=Decimal(val),
              site_url=f"https://{host}", article_url=f"https://{host}{article}",
              status=OfferStatus.pending_review, created_by=CreatedBy.crawler)
    o.discounts = [OfferDiscount(label=label, discount_type=DiscountType.percent,
                                 discount_value=Decimal(val), sort_order=0)]
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


def test_find_duplicates_pairs_same_promo(db_session):
    a = _raw(db_session, "/aktsiyi", "x.com.ua", "Знижка 15% військовим на послуги")
    b = _raw(db_session, "/pro-nas", "x.com.ua", "Військовим знижка 15% на послуги")
    c = _raw(db_session, "/o", "y.com.ua", "Безкоштовна доставка усім клієнтам")  # different host
    pairs = find_duplicates(db_session, 0.6)
    assert (b.id, a.id) in pairs
    assert all(p[0] != c.id for p in pairs)


def test_find_duplicates_idempotent_after_reject(db_session):
    a = _raw(db_session, "/1", "z.com.ua", "Знижка 20% ветеранам на все")
    b = _raw(db_session, "/2", "z.com.ua", "Ветеранам знижка 20% на все")
    assert (b.id, a.id) in find_duplicates(db_session, 0.6)
    b.status = OfferStatus.rejected
    db_session.commit()
    assert find_duplicates(db_session, 0.6) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_dedup_queue_script.py -q`
Expected: FAIL — `ModuleNotFoundError: app.dedup_queue`.

- [ ] **Step 3: Write the script**

Create `backend/app/dedup_queue.py`:

```python
"""One-off: collapse duplicate promo offers already sitting in the moderation queue.

Groups pending crawler offers by host and rejects same-promo duplicates (keeping the
oldest row per group), using the same host+magnitude+text rule as create_offer branch 3c.
Dry-run by default; pass --apply to write changes. Idempotent.

Run:  python -m app.dedup_queue          # dry-run
      python -m app.dedup_queue --apply  # reject duplicates
"""
import argparse

from app.core.config import settings
from app.core.db import SessionLocal
from app.crud.dedup import normalize_tokens, discount_magnitudes, is_duplicate_promo
from app.crud.offer import _source_host, _promo_text
from app.models import Offer
from app.models.enums import CreatedBy, OfferStatus


def find_duplicates(db, threshold):
    """Return [(dup_id, keep_id)] for pending crawler offers that duplicate an older kept
    offer on the same host. The oldest row of each promo group is kept."""
    pend = (db.query(Offer)
            .filter(Offer.created_by == CreatedBy.crawler,
                    Offer.status == OfferStatus.pending_review)
            .order_by(Offer.id).all())
    kept = []
    pairs = []
    for o in pend:
        host = _source_host(o.site_url) or _source_host(o.article_url)
        mags = discount_magnitudes(o.discounts, o.discount_type, o.discount_value)
        text = normalize_tokens(_promo_text(o))
        match = next((k for k in kept if k["host"] == host
                      and is_duplicate_promo(text, mags, k["text"], k["mags"], threshold)), None)
        if match is not None:
            pairs.append((o.id, match["id"]))
        else:
            kept.append({"id": o.id, "host": host, "mags": mags, "text": text})
    return pairs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    args = ap.parse_args()
    db = SessionLocal()
    try:
        pairs = find_duplicates(db, settings.dedup_text_similarity_threshold)
        for dup_id, keep_id in pairs:
            tag = "[REJECTED]" if args.apply else "[dry-run]"
            print(f"offer {dup_id} -> duplicate of {keep_id}  {tag}")
        if args.apply:
            for dup_id, _ in pairs:
                db.get(Offer, dup_id).status = OfferStatus.rejected
            db.commit()
        verb = "rejected" if args.apply else "found (dry-run)"
        print(f"{len(pairs)} duplicate(s) {verb}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_dedup_queue_script.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/dedup_queue.py backend/tests/test_dedup_queue_script.py
git commit -m "feat(backend): one-off script to collapse queued promo duplicates"
```

---

### Task 4: Deploy + clean the live queue

**Files:** none (rebuild + run script + verify).

- [ ] **Step 1: Rebuild + restart backend with the new code**

```bash
docker compose build backend && docker compose up -d --force-recreate backend
```
Expected: `Container ubd_probe-backend-1  Started`, then `Up ... (healthy)`.

- [ ] **Step 2: Dry-run the cleanup on the live DB**

```bash
docker compose exec backend python -m app.dedup_queue
```
Expected: a list of `offer N -> duplicate of M  [dry-run]` lines and a total count. Review that the pairs are the genuine duplicates (edclinic/mate/shishkinn/tovpollar family), not distinct offers.

- [ ] **Step 3: Apply the cleanup**

```bash
docker compose exec backend python -m app.dedup_queue --apply
```
Expected: same pairs now `[REJECTED]`, plus `N duplicate(s) rejected.`

- [ ] **Step 4: Verify the queue shrank and no host duplicates remain**

```bash
docker exec ubd_probe-db-1 mysql -uroot -pmy-secret-pw -N ubd -e "SELECT status, COUNT(*) FROM offers GROUP BY status;"
```
Expected: `pending_review` count dropped by the number rejected; `rejected` rose by the same.

---

## Self-Review

**Spec coverage:**
- dedup.py pure functions (normalize/similarity/magnitudes/is_duplicate) → Task 1. ✓
- Rewired branch 3c (host + magnitude subset + text, shadows included) → Task 2. ✓
- Config threshold → Task 2 Step 3. ✓
- Text = description + labels, not title → Task 2 `_promo_text`. ✓
- One-off cleanup, dry-run default, keep-oldest-per-group → Task 3. ✓
- Regression guard (banner tests) → Task 2 Step 6. ✓
- Live deploy + clean queue → Task 4. ✓
- No schema change → confirmed (no migration task). ✓

**Placeholder scan:** none — every step has concrete code/commands.

**Type consistency:** `normalize_tokens`/`text_similarity`/`discount_magnitudes`/`is_duplicate_promo` signatures identical across Tasks 1-3; `_promo_text`/`_source_host` used consistently; `find_duplicates(db, threshold) -> list[(int,int)]` matches its test.

---

## Known follow-ups (post-merge, not blocking)

- **Candidate-scan scale ceiling (final-review Important #1).** Branch 3c loads every non-expired crawler offer per `create_offer` call, then filters host/magnitude/text in Python (magnitude-SUBSET matching can't be pushed to SQL as an equality filter). Negligible at current volume (hundreds of offers), but O(N) on the ingestion hot path. Fast-follow when offer volume grows: add a NECESSARY-condition SQL pre-filter — a candidate must contain the new offer's primary `(discount_type, discount_value)` among its `offer_discounts` (EXISTS subquery) — to shrink the scan without changing subset semantics. Top-level `discount_value` alone is unsafe for multi-discount offers (it mirrors only the primary), hence the subquery.
