# Backend Apex-Homepage Promo Dedup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse an incoming apex-homepage crawler offer onto an existing same-host, non-shadow, non-expired offer that shares a discount magnitude, so homepage-banner duplicates never enter the moderation queue.

**Architecture:** One new dedup branch ("3d") in `create_offer`, placed after 3c (text-similarity dedup) and before branch 4 (cross-source canonical merge). Apex is detected by a path-less `article_url_canonical`; the match is a plain discount-magnitude set intersection (no text gate), with deep same-host peers preferred as the collapse target.

**Tech Stack:** Python 3, SQLAlchemy, pytest; MySQL (`ubd`) via `docker exec`; Docker Compose.

## Global Constraints

- Ukrainian-only project: no Russian text in code/tests.
- No schema change, no migration, no crawler change, no config. Backend `create_offer` only.
- Reuse existing helpers: `discount_magnitudes` (from `app.crud.dedup`), `_source_host`, `selectinload`, `canonicalize_target_url` — all already imported in `backend/app/crud/offer.py`.
- One-directional: incoming **apex** only (`canon_article` has no `/`). Require a magnitude overlap; exclude shadows (`supersedes IS NULL`) and `expired`.
- Do not alter branches 1/2/3/3b/3c/4 or any legitimate shadow (e.g. queue #334).
- Verified: `canonicalize_target_url` maps `https://smartlab.ua` and `https://www.smartlab.ua/` → `smartlab.ua`; deep pages keep their path.
- Backend tests run in the backend venv/container. DB password `MYSQL_ROOT_PASSWORD` in `.env`; DB `ubd`; container `ubd_probe-db-1`; backend container `ubd_probe-backend-1`.

---

## File Structure

- Modify `backend/app/crud/offer.py` — add branch 3d between line ~267 (end of 3c) and ~269 (branch 4).
- Create `backend/tests/test_offer_apex_dedup.py` — mirror `test_offer_discovered_dedup.py`.
- Rollout only: rebuild backend + reject queue #332/#333.

---

## Task 1: Branch 3d — apex-homepage dedup

**Files:**
- Modify: `backend/app/crud/offer.py:267-269`
- Test: `backend/tests/test_offer_apex_dedup.py`

**Interfaces:**
- Consumes: `create_offer(db, data: OfferCreate, created_by, status, source_id=None, content_hash=None)`; `discount_magnitudes`, `_source_host` (in-module).
- Produces: `create_offer` returns an existing same-host magnitude-overlapping offer (no new row) when `data`'s `article_url_canonical` is a path-less apex host; unchanged otherwise.

- [ ] **Step 1: Write the failing tests** — create `backend/tests/test_offer_apex_dedup.py`

```python
from datetime import datetime

from app.crud import offer as offer_crud
from app.models import Offer
from app.models.enums import CreatedBy, OfferStatus
from app.schemas.offer import OfferCreate


def _offer(article, *, val="30", dtype="percent", provider="P", title="T",
           site="https://smartlab.ua"):
    return OfferCreate(type="discount", title=title, provider=provider,
                       discount_type=dtype, discount_value=val,
                       site_url=site, article_url=article)


def _create(db, data, *, status=OfferStatus.pending_review, ch=None, source_id=None):
    return offer_crud.create_offer(db, data, CreatedBy.crawler, status,
                                   source_id=source_id, content_hash=ch)


def test_apex_offer_collapses_onto_deep_same_host_same_magnitude(db_session):
    deep = _create(db_session, _offer("https://smartlab.ua/discont/hersona/about"),
                   status=OfferStatus.published, ch="h1")
    deep.last_seen_at = datetime(2000, 1, 1)
    db_session.commit()
    apex = _create(db_session, _offer("https://smartlab.ua", val="30"),
                   source_id=48, ch="h2")
    assert apex.id == deep.id                             # collapsed, not a new row
    assert db_session.query(Offer).count() == 1
    assert deep.last_seen_at > datetime(2000, 1, 1)       # bumped


def test_apex_offer_with_no_same_host_peer_is_kept(db_session):
    apex = _create(db_session, _offer("https://smartlab.ua"), ch="h1")
    assert db_session.query(Offer).count() == 1
    assert apex.article_url_canonical == "smartlab.ua"


def test_apex_offer_with_different_magnitude_is_kept(db_session):
    deep = _create(db_session, _offer("https://smartlab.ua/deep", val="30"),
                   status=OfferStatus.published, ch="h1")
    apex = _create(db_session, _offer("https://smartlab.ua", val="10"), ch="h2")
    assert apex.id != deep.id                             # 10% vs 30% -> not collapsed
    assert db_session.query(Offer).count() == 2


def test_apex_prefers_deep_peer_over_apex_peer(db_session):
    # an apex-only rejected peer of the same magnitude exists AND a deep published one;
    # the incoming apex must fold onto the DEEP peer.
    apex_old = _create(db_session, _offer("https://smartlab.ua", val="30"), ch="h0")
    apex_old.status = OfferStatus.rejected
    apex_old.article_url = None                            # force a second apex row shape
    apex_old.article_url_canonical = "smartlab.ua"
    deep = _create(db_session, _offer("https://smartlab.ua/deep", val="30"),
                   status=OfferStatus.published, ch="h1")
    db_session.commit()
    # NOTE: apex_old shares canon "smartlab.ua"; branch 1/3b own exact-canon repeats, so a
    # fresh apex with new content_hash reaches 3d and must prefer the deep peer.
    incoming = _create(db_session, _offer("https://smartlab.ua", val="30"), ch="h2")
    assert incoming.id == deep.id


def test_deep_offer_is_unaffected_by_apex_branch(db_session):
    a = _create(db_session, _offer("https://smartlab.ua/one", val="30"), ch="h1")
    b = _create(db_session, _offer("https://smartlab.ua/two", val="30"), ch="h2")
    assert a.id != b.id                                   # two deep pages stay separate here


def test_shadow_peer_is_not_a_collapse_target(db_session):
    parent = _create(db_session, _offer("https://smartlab.ua/deep", val="30"),
                     status=OfferStatus.published, source_id=48, ch="h1")
    # a shadow of the parent (supersedes set), same host
    shadow = _create(db_session, _offer("https://smartlab.ua/deep", val="40"),
                     source_id=48, ch="h2")
    assert shadow.supersedes_offer_id == parent.id        # sanity: it is a shadow
    apex = _create(db_session, _offer("https://smartlab.ua", val="40"),
                   source_id=48, ch="h3")
    assert apex.id != shadow.id                           # never collapses onto a shadow
```

- [ ] **Step 2: Run to verify it fails**

Run (from `backend/`): `docker compose exec -T backend python -m pytest tests/test_offer_apex_dedup.py -q`
Expected: FAIL — `test_apex_offer_collapses_onto_deep_same_host_same_magnitude` inserts a 2nd row (no 3d branch yet), so `apex.id == deep.id` is False.

> If the repo runs backend tests via a local venv instead of the container, use that runner (e.g. `backend/.venv/Scripts/python.exe -m pytest ...`) — match whatever `backend/tests` already uses for `db_session`.

- [ ] **Step 3: Add branch 3d** — edit `backend/app/crud/offer.py`, inserting between the end of the 3c block (after its `return c`, ~line 267) and the `# 4) Cross-source canonical merge` comment (~line 269)

```python
    # 3d) Apex-homepage dedup: a homepage/source crawl surfaces a promo banner on the
    #     bare apex host (canon_article has no path). Its generic homepage text defeats
    #     3c's text gate, yet it is the same promo as a deep offer page on the same host
    #     sharing a discount magnitude. Collapse the apex offer onto an existing same-host
    #     non-shadow non-expired offer (deep pages preferred), bump last_seen, and never
    #     insert the duplicate. One-directional (incoming apex only); a magnitude overlap
    #     is required, so distinct-magnitude same-host offers stay separate.
    if (crawler and not blocked and canon_article and "/" not in canon_article
            and data.discount_type is not None):
        host = (_source_host(getattr(data, "site_url", None))
                or _source_host(getattr(data, "article_url", None)))
        new_mags = discount_magnitudes(getattr(data, "discounts", None),
                                       data.discount_type, data.discount_value)
        if host and new_mags:
            cands = (db.query(Offer)
                     .options(selectinload(Offer.discounts))
                     .filter(Offer.created_by == CreatedBy.crawler,
                             Offer.status != OfferStatus.expired,
                             Offer.supersedes_offer_id.is_(None))
                     .all())

            def _rank(c):
                ca = c.article_url_canonical or ""
                return (0 if "/" in ca else 1, c.id)   # deep peers first, then lowest id

            for c in sorted(cands, key=_rank):
                if (c.article_url_canonical or "") == canon_article:
                    continue                            # same apex page → branches 1/3b own it
                c_host = _source_host(c.site_url) or _source_host(c.article_url)
                if c_host != host:
                    continue
                c_mags = discount_magnitudes(c.discounts, c.discount_type, c.discount_value)
                if new_mags & c_mags:
                    c.last_seen_at = datetime.utcnow()
                    db.commit()
                    db.refresh(c)
                    return c
```

- [ ] **Step 4: Run to verify it passes**

Run: `docker compose exec -T backend python -m pytest tests/test_offer_apex_dedup.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Run the full backend suite (no regressions)**

Run: `docker compose exec -T backend python -m pytest -q`
Expected: PASS — especially `test_offer_discovered_dedup.py`, `test_offer_banner_dedup.py`, `test_dedup.py` unchanged.

- [ ] **Step 6: Commit**

```bash
git add backend/app/crud/offer.py backend/tests/test_offer_apex_dedup.py
git commit -m "feat(backend): apex-homepage promo dedup (branch 3d)"
```

---

## Task 2: Rollout — deploy + clean the two queue dups

**Files:** none in-repo.

- [ ] **Step 1: Rebuild + restart the backend**

```bash
docker compose build backend && docker compose up -d backend
```

- [ ] **Step 2: Reject the two existing apex duplicates (#332, #333)**

First confirm they are the intended rows, then reject:

```bash
PW=$(grep -h '^MYSQL_ROOT_PASSWORD=' .env | cut -d= -f2-)
docker exec ubd_probe-db-1 mysql --default-character-set=utf8mb4 -uroot -p"$PW" ubd -e "
SELECT id,status,source_id,discount_type,discount_value,article_url_canonical
FROM offers WHERE id IN (332,333);
UPDATE offers SET status='rejected' WHERE id IN (332,333) AND status='pending_review';
SELECT ROW_COUNT() AS rejected;"
```

Expected: the two rows are the compass-group / smartlab apex offers; `rejected` = 2. (Do **not** touch #334 — it is a legitimate shadow of #302.)

- [ ] **Step 3: Verify the queue**

```bash
PW=$(grep -h '^MYSQL_ROOT_PASSWORD=' .env | cut -d= -f2-)
docker exec ubd_probe-db-1 mysql -uroot -p"$PW" ubd -e "
SELECT status, COUNT(*) FROM offers GROUP BY status;"
```

Expected: `pending_review` dropped by 2 (from 6 to 4). #334 still pending (shadow).

---

## Self-Review

**Spec coverage:**
- Branch 3d (apex detection, magnitude overlap, deep-preferred, shadow/expired excluded, return-existing) → Task 1 Step 3. ✓
- Apex collapses onto deep same-magnitude; kept when no peer / different magnitude; deep preferred; deep unaffected; shadow not a target → Task 1 tests. ✓
- No schema/migration/crawler/config change → Global Constraints; branch is additive. ✓
- Rollout (rebuild + reject #332/#333, leave #334) → Task 2. ✓

**Placeholder scan:** none — code and commands concrete.

**Type consistency:** `discount_magnitudes(discounts, dt, dv) -> frozenset[tuple]` used with `&` intersection (frozensets). `_source_host(value) -> str`. `canon_article` is the canonical string. `create_offer` signature matches the test `_create` wrapper. Branch placed after 3c's `return c` and before branch 4, consistent with the spec's line references.
