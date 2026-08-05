# Discovered-Offer Page Dedup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop active-search discovered offers (`source_id=None`) from creating duplicate moderation-queue rows for the same promo page.

**Architecture:** Add one branch to `create_offer` that, for `source_id IS NULL` crawler offers, short-circuits (bump `last_seen_at`, return existing) when the same `article_url_canonical` is already known in any non-expired status. Mirrors branch 1 but keyed on the page URL instead of `content_hash`, so it also catches drifted-content re-crawls that branch 1 misses.

**Tech Stack:** FastAPI, SQLAlchemy, MySQL (tests on the project's test DB), pytest.

## Global Constraints

- Backend-only change. No migration (reuses existing `article_url_canonical` column + `ix_offers_article_url_canonical` index).
- Do NOT modify branches 1/2/3/4 of `create_offer`; only add the new branch.
- New branch is NOT guarded with `and not blocked` (blocked-source re-crawls with drifted content must collapse onto the existing rejected row, not re-INSERT).
- New branch excludes shadows (`supersedes_offer_id IS NULL`) and expired rows (`status != expired`).
- Run tests from `backend/` with `.venv/Scripts/python.exe -m pytest -q`. Backend tests need `docker start mysql-container` (:3306).
- Communication/commit language per repo convention; commit trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## File Structure

- Modify: `backend/app/crud/offer.py` — insert new branch after branches 2/3 (line ~195), before branch 4 (line ~197).
- Create: `backend/tests/test_offer_discovered_dedup.py` — behavior of the new branch.
- Modify (regression fixtures): `backend/tests/test_offer_merge.py`, `backend/tests/test_promotion.py` — unique `article_url` where a test asserts two `source_id=None` offers stay separate but happened to share the default article.

---

### Task 1: New dedup branch + its test file

**Files:**
- Modify: `backend/app/crud/offer.py` (insert branch between line 195 and 197)
- Test: `backend/tests/test_offer_discovered_dedup.py` (create)

**Interfaces:**
- Consumes: `offer_crud.create_offer(db, data: OfferCreate, created_by, status, source_id=None, content_hash=None) -> Offer` (existing signature).
- Produces: no new public symbols; only new runtime behavior for `source_id=None` crawler offers.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_offer_discounts_crud.py`'s sibling `backend/tests/test_offer_discovered_dedup.py`:

```python
from datetime import datetime

from app.crud import offer as offer_crud
from app.crud import blocked_host as bh
from app.crud import source as source_crud
from app.models import Offer
from app.models.enums import CreatedBy, OfferStatus
from app.schemas.offer import OfferCreate
from app.schemas.source import SourceCreate


def _offer(article, *, target=None, provider="P", val="10", title="T",
           site="https://shop.ua"):
    return OfferCreate(type="discount", title=title, provider=provider,
                       discount_type="percent", discount_value=val,
                       site_url=site, article_url=article, target_url=target)


def _create(db, data, *, status=OfferStatus.pending_review, ch=None, source_id=None):
    return offer_crud.create_offer(db, data, CreatedBy.crawler, status,
                                   source_id=source_id, content_hash=ch)


def test_same_page_variants_collapse_to_one_pending(db_session):
    # byte-different URL forms (www / trailing slash / utm) + drifted content_hash
    a = _create(db_session, _offer("https://shop.ua/promo"), ch="h1")
    b = _create(db_session, _offer("https://www.shop.ua/promo/?utm_source=fb", val="20"),
                ch="h2")
    assert b.id == a.id
    assert db_session.query(Offer).count() == 1


def test_rejected_page_does_not_return_to_queue(db_session):
    a = _create(db_session, _offer("https://shop.ua/promo"), ch="h1")
    a.status = OfferStatus.rejected
    db_session.commit()
    b = _create(db_session, _offer("https://shop.ua/promo", val="20"), ch="h2")
    assert b.id == a.id
    assert b.status == OfferStatus.rejected            # stays rejected, no fresh pending
    assert db_session.query(Offer).count() == 1


def test_published_page_bumps_last_seen_without_shadow(db_session):
    a = _create(db_session, _offer("https://shop.ua/promo"), ch="h1")
    a.status = OfferStatus.published
    a.last_seen_at = datetime(2000, 1, 1)
    db_session.commit()
    b = _create(db_session, _offer("https://shop.ua/promo", val="20"), ch="h2")
    assert b.id == a.id
    assert b.supersedes_offer_id is None               # discovered published -> skip, not shadow
    assert b.last_seen_at > datetime(2000, 1, 1)


def test_different_pages_stay_separate(db_session):
    a = _create(db_session, _offer("https://shop.ua/one"), ch="h1")
    b = _create(db_session, _offer("https://shop.ua/two"), ch="h2")
    assert a.id != b.id


def test_source_bound_offer_unaffected(db_session):
    # with a real source, branch 3 (update-in-place) still applies; the new
    # source_id=None branch must not swallow it.
    s = source_crud.create_source(
        db_session, SourceCreate(name="S", type="website",
                                 url_or_handle="https://shop.ua", is_active=True),
        CreatedBy.crawler)
    a = _create(db_session, _offer("https://shop.ua/promo"), ch="h1", source_id=s.id)
    b = _create(db_session, _offer("https://shop.ua/promo", val="20"), ch="h2",
                source_id=s.id)
    assert b.id == a.id                                # branch 3 updates in place
    assert str(b.discount_value) == "20.00"            # branch 3 DID apply content


def test_blocked_source_duplicate_collapses_by_page(db_session):
    bh.auto_block(db_session, "shop.ua")
    a = _create(db_session, _offer("https://shop.ua/promo"), ch="h1")
    assert a.status == OfferStatus.rejected            # blocked -> forced reject
    b = _create(db_session, _offer("https://shop.ua/promo", val="20"), ch="h2")
    assert b.id == a.id                                # drifted content still collapses
    assert db_session.query(Offer).count() == 1
```

- [ ] **Step 2: Run the new tests to verify they fail**

From `backend/`:
```bash
.venv/Scripts/python.exe -m pytest tests/test_offer_discovered_dedup.py -q
```
Expected: FAIL — `test_same_page_variants_collapse_to_one_pending`, `test_rejected_page_does_not_return_to_queue`, `test_published_page_bumps_last_seen_without_shadow`, `test_blocked_source_duplicate_collapses_by_page` fail (two rows created / fresh pending). `test_different_pages_stay_separate` and `test_source_bound_offer_unaffected` should already pass.

- [ ] **Step 3: Insert the new branch**

In `backend/app/crud/offer.py`, immediately after branch 3's block (after the `return pending` at line ~195) and before the `# 4) Cross-source canonical merge` comment (line ~197), insert:

```python
    # 3b) Discovered-offer page dedup (active search, source_id=None). Branches 2/3 above are
    #     gated on `source_id is not None`, so an active-search offer for a page already in the
    #     queue would fall through and re-INSERT. Short-circuit here on article_url_canonical:
    #     bump last_seen and return the existing row without touching its content. Mirrors
    #     branch 1 but keyed on the page URL, so it also catches drifted-content re-crawls that
    #     branch 1 (exact content_hash) misses. NOT guarded with `and not blocked`: a blocked
    #     re-crawl with drifted content must collapse onto the existing rejected row, not
    #     re-INSERT. Excludes shadows (supersedes IS NULL) and expired rows (a revert to an
    #     expired page must fall through to re-moderation).
    if crawler and canon_article and source_id is None:
        existing = (db.query(Offer)
                    .filter(Offer.source_id.is_(None),
                            Offer.article_url_canonical == canon_article,
                            Offer.status != OfferStatus.expired,
                            Offer.supersedes_offer_id.is_(None))
                    .order_by(Offer.id).first())
        if existing is not None:
            existing.last_seen_at = datetime.utcnow()
            db.commit()
            db.refresh(existing)
            return existing
```

- [ ] **Step 4: Run the new tests to verify they pass**

```bash
.venv/Scripts/python.exe -m pytest tests/test_offer_discovered_dedup.py -q
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/crud/offer.py backend/tests/test_offer_discovered_dedup.py
git commit -m "feat(backend): dedup discovered-offer duplicates by promo page

Active-search offers carry source_id=None, so the article_url_canonical
dedup branches (2/3) skip them and duplicates of the same page leak into
moderation (batart×4, kupola×5, prostir×8). Add branch 3b: for
source_id IS NULL crawler offers, short-circuit on article_url_canonical
against any non-expired, non-shadow row (bump last_seen, skip). Catches
drifted-content re-crawls branch 1 misses; not gated on blocked so
blocked-rejected duplicates collapse too.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Repair regression fixtures + full green suite

**Files:**
- Modify: `backend/tests/test_offer_merge.py`
- Modify: `backend/tests/test_promotion.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new. Pure test-fixture correction — three merge tests and one promotion test assert two `source_id=None` offers stay separate but shared the default `article_url`, which the new branch 3b now collapses. Give each its own `article_url` so the test isolates its actual intent (target-merge / origin-promotion), not page identity.

- [ ] **Step 1: Run the full backend suite to see the regressions**

```bash
.venv/Scripts/python.exe -m pytest -q
```
Expected FAILs: `test_offer_merge.py::test_different_target_stays_separate`, `::test_no_target_stays_separate`, `::test_different_canonical_stays_separate` (assert `a.id != b.id`, but share `article="https://a/x"`). Confirm no other unexpected failures; if any appear, they share the same root — apply the same unique-`article_url` fix.

- [ ] **Step 2: Give the three merge tests unique article URLs**

In `backend/tests/test_offer_merge.py`, edit the three target-focused tests so each offer has its own `article_url` (the tests are about *target* identity, not page identity):

```python
def test_different_target_stays_separate(db_session):
    a = _create(db_session, _offer("https://biz.example/one", article="https://biz.example/one"))
    b = _create(db_session, _offer("https://biz.example/two", article="https://biz.example/two"))
    assert a.id != b.id


def test_no_target_stays_separate(db_session):
    a = _create(db_session, _offer(None, article="https://biz.example/a"))
    b = _create(db_session, _offer(None, article="https://biz.example/b"))
    assert a.id != b.id


def test_different_canonical_stays_separate(db_session):
    a = _create(db_session, _offer("https://biz.example/one", article="https://biz.example/one"))
    b = _create(db_session, _offer("https://biz.example/two", article="https://biz.example/two"))
    assert a.id != b.id
```

- [ ] **Step 3: Give the promotion idempotency test distinct pages on one origin**

In `backend/tests/test_promotion.py`, `test_promotion_is_idempotent_across_offers_sharing_origin` currently makes `o1`/`o2` share the default `article_url="https://shop.example/deal"`; branch 3b would collapse `o2` onto `o1` and hollow out the test. Give `o2` its own page on the same `site_url` origin:

```python
def test_promotion_is_idempotent_across_offers_sharing_origin(db_session):
    o1 = _crawler_offer(db_session, content_hash="h1")
    o2 = _crawler_offer(db_session, title="T2", article_url="https://shop.example/deal2",
                        content_hash="h2")
    promotion.maybe_promote_on_publish(db_session, o1)
    promotion.maybe_promote_on_publish(db_session, o2)
    db_session.refresh(o1); db_session.refresh(o2)
    assert o1.source_id == o2.source_id
    assert db_session.query(Source).count() == 1
```

- [ ] **Step 4: Run the full backend suite — all green**

```bash
.venv/Scripts/python.exe -m pytest -q
```
Expected: all pass (previous count 177 + 6 new = 183; adjust if the suite grew).

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_offer_merge.py backend/tests/test_promotion.py
git commit -m "test(backend): isolate page identity from target/origin fixtures

Branch 3b collapses two source_id=None offers sharing an article_url.
Three merge tests and one promotion test shared the default article_url
while asserting separateness on target/origin — give each its own page
URL so they test their actual intent.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Update session ledger, RESUME, and memory

**Files:**
- Modify: `.superpowers/sdd/progress.md`
- Modify: `docs/RESUME.md`
- Create/Modify: memory file for this track + `MEMORY.md` pointer

- [ ] **Step 1: Append to the SDD progress ledger**

Add an entry to `.superpowers/sdd/progress.md` recording the track (discovered-offer page dedup), the branch, and the commits.

- [ ] **Step 2: Update `docs/RESUME.md`**

Add a "#36 discovered-offer page dedup (branch 3b)" section following the existing RESUME format (what/why/commits/tests count).

- [ ] **Step 3: Write memory + MEMORY.md pointer**

Create `C:\Users\goblin\.claude\projects\D--ubd-probe\memory\ubd-backend-discovered-offer-page-dedup.md` (type: project) summarizing: branch 3b dedups `source_id=None` offers by `article_url_canonical` against any non-expired non-shadow row (skip, bump last_seen), closing the queue-noise duplicate leak; links `[[ubd-backend-offer-source-dedup]]`, `[[ubd-backend-auto-reject-blocked-source]]`, `[[ubd-crawler-pagelevel-dedup-done]]`. Add a one-line pointer to `MEMORY.md`.

- [ ] **Step 4: Commit**

```bash
git add .superpowers/sdd/progress.md docs/RESUME.md
git commit -m "docs: RESUME #36 — discovered-offer page dedup (branch 3b)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- New branch for `source_id IS NULL` skip → Task 1 Step 3. ✓
- Position after branch 1, before branch 4 → Task 1 Step 3 (inserted after branch 3, before branch 4; branches 2/3 are mutually exclusive with `source_id IS NULL`). ✓
- Skip semantics for pending/rejected/published → Task 1 tests 1–3. ✓
- Without `not blocked` guard → Task 1 test 6 (blocked duplicate). ✓
- `supersedes IS NULL` + `!= expired` exclusions → encoded in the query; expired not separately tested (mirrors branch 1's documented rationale, low risk). ✓
- Different pages stay separate → Task 1 test 4. ✓
- Source-bound regression intact → Task 1 test 5. ✓
- Backend-only, no migration → Global Constraints; no alembic task. ✓
- Fixture regressions (test_offer_merge, test_promotion) → Task 2. ✓

**Placeholder scan:** No TBD/TODO; every code step shows full code. Task 2 Step 1 asks to confirm no *other* failures — deterministic (a suite run), with a stated fix recipe if any appear. ✓

**Type consistency:** `_offer`/`_create` helper signatures in the new test file are self-consistent; `article=` keyword used in test_offer_merge matches its existing `_offer(target, ..., article=...)` signature; `article_url=` keyword in test_promotion matches `_crawler_offer(**over)` passthrough. ✓
