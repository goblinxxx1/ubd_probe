# Backend canonical offer dedup — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dedup/merge offers on a backend-computed `target_url_canonical` key (utm/click-id/www/scheme-insensitive) instead of the raw `target_url`.

**Architecture:** A pure `canonicalize_target_url` in `app/core/urlnorm.py` is the single source of truth. `Offer` gains a `target_url_canonical` column (indexed), computed on every create for all offers; the crawler merge path matches on it. Raw `target_url` stays for the click-through. Existing rows are backfilled without retro-merge.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Alembic, MySQL, pytest.

## Global Constraints

- Scope is `backend/` only — no crawler/admin/public changes.
- Baseline is **92** backend tests green. Run from `backend/`: `./.venv/Scripts/python.exe -m pytest -q`. Backend tests need `mysql-container` on :3306 (`docker start mysql-container`); the `db_session` fixture builds schema via `Base.metadata.create_all` (models, not migrations).
- `target_url_canonical` is INTERNAL: not in `OfferCreate`/`OfferBase`/`OfferOut`; public click-through keeps using raw `target_url`.
- Fixed decisions (do not revisit): raw `target_url` stays; backfill has NO retro-merge; NO unique constraint on canonical.
- Merge policy preserved exactly: canonical computed+stored for ALL offers (incl. admin); admin-created offers do NOT trigger dedup; crawler-created offers match ANY existing offer (incl. admin) by canonical and append an `OfferLink`. Only the match key changes raw→canonical.
- Canonical transform (exact): reject non-http(s)→`None`; lowercase host via `p.hostname` (drops port+userinfo); `removeprefix("www.")`; scheme omitted (http↔https collapse); drop fragment; `path.rstrip("/")`; drop `utm_*` and curated click-ids; sort remaining query params. Output form: `f"{host}{path}"` + `("?"+query if query else "")`.
- Current Alembic head is `67382fc48c01` — the new migration's `down_revision` is `'67382fc48c01'`.

---

### Task 1: `canonicalize_target_url`

**Files:**
- Modify: `backend/app/core/urlnorm.py`
- Test: `backend/tests/test_urlnorm.py` (new)

**Interfaces:**
- Produces: `canonicalize_target_url(url: str) -> str | None` in `app.core.urlnorm`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_urlnorm.py
from app.core.urlnorm import canonicalize_target_url


def test_strips_www_and_collapses_scheme():
    assert canonicalize_target_url("https://www.okko.ua/promo") == "okko.ua/promo"
    assert canonicalize_target_url("http://okko.ua/promo") == "okko.ua/promo"


def test_strips_utm_and_click_ids():
    assert canonicalize_target_url(
        "https://www.okko.ua/promo/?utm_source=fb&fbclid=xxx&gclid=y") == "okko.ua/promo"


def test_keeps_meaningful_query_sorted():
    assert canonicalize_target_url("https://shop.ua/p?b=2&a=1&utm_x=9") == "shop.ua/p?a=1&b=2"


def test_trailing_slash_and_root_collapse():
    assert canonicalize_target_url("https://okko.ua/") == "okko.ua"
    assert canonicalize_target_url("https://okko.ua") == "okko.ua"


def test_strips_port_and_userinfo():
    assert canonicalize_target_url("https://user:pw@www.okko.ua:443/p") == "okko.ua/p"


def test_non_http_and_junk_and_empty_return_none():
    assert canonicalize_target_url("ftp://okko.ua/x") is None
    assert canonicalize_target_url("mailto:a@b.com") is None
    assert canonicalize_target_url("not a url") is None
    assert canonicalize_target_url("") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_urlnorm.py -q`
Expected: FAIL — `ImportError: cannot import name 'canonicalize_target_url'`

- [ ] **Step 3: Write minimal implementation**

Append to `backend/app/core/urlnorm.py` (imports `parse_qsl, urlencode, urlsplit` already present):

```python
# Tracking/click-id params stripped in addition to any utm_* prefix.
_TRACKING_PARAMS = frozenset({
    "gclid", "gclsrc", "dclid", "gbraid", "wbraid", "fbclid", "yclid", "msclkid",
    "twclid", "ttclid", "igshid", "mc_eid", "mc_cid", "_openstat", "vero_id",
    "oly_enc_id", "oly_anon_id", "icid", "scid", "srsltid", "spm",
})


def canonicalize_target_url(url: str) -> str | None:
    """Scheme-less, www-less offer dedup key: lowercased host (no port/userinfo, www. dropped),
    path without trailing slash, tracking params (utm_*/click-ids) stripped, rest sorted.
    http↔https collapsed (scheme omitted). Returns None for non-http(s)/junk."""
    if not url:
        return None
    p = urlsplit(url.strip())
    if p.scheme not in ("http", "https") or not p.netloc:
        return None
    host = (p.hostname or "").removeprefix("www.")
    if not host:
        return None
    kept = sorted((k, v) for k, v in parse_qsl(p.query)
                  if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_PARAMS)
    query = urlencode(kept)
    path = p.path.rstrip("/")
    return f"{host}{path}" + (f"?{query}" if query else "")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_urlnorm.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/urlnorm.py backend/tests/test_urlnorm.py
git commit -m "feat(backend): canonicalize_target_url for offer dedup key"
```

---

### Task 2: `target_url_canonical` column + migration + backfill

**Files:**
- Modify: `backend/app/models/offer.py`
- Create: `backend/alembic/versions/9a1c7b3e2f10_offer_target_url_canonical.py`
- Test: `backend/tests/test_migration_canonical.py` (new)

**Interfaces:**
- Consumes: `canonicalize_target_url` (Task 1).
- Produces: `Offer.target_url_canonical` (nullable str), index `ix_offers_target_url_canonical`; migration module exposing `_backfill(conn)`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_migration_canonical.py
import importlib.util
import pathlib

from sqlalchemy import text

from app.models import Offer
from app.models.enums import CreatedBy, OfferStatus, OfferType


def _load_backfill():
    path = (pathlib.Path(__file__).resolve().parents[1]
            / "alembic" / "versions" / "9a1c7b3e2f10_offer_target_url_canonical.py")
    spec = importlib.util.spec_from_file_location("mig_canonical", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._backfill


def test_backfill_populates_canonical_for_existing_rows(db_session):
    # Legacy rows: target_url set, canonical left NULL (Task 3 auto-set not involved here).
    o1 = Offer(type=OfferType.discount, title="T", description="", provider="P",
               target_url="https://www.biz.example/deal/?utm_source=x&fbclid=z",
               status=OfferStatus.published, created_by=CreatedBy.crawler)
    o2 = Offer(type=OfferType.discount, title="T2", description="", provider="P",
               target_url=None, status=OfferStatus.published, created_by=CreatedBy.crawler)
    db_session.add_all([o1, o2])
    db_session.commit()
    assert o1.target_url_canonical is None          # not set on plain construction

    _load_backfill()(db_session.connection())
    db_session.expire_all()
    assert db_session.get(Offer, o1.id).target_url_canonical == "biz.example/deal"
    assert db_session.get(Offer, o2.id).target_url_canonical is None   # no target_url → stays NULL
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_migration_canonical.py -q`
Expected: FAIL — `AttributeError: type object 'Offer' has no attribute 'target_url_canonical'` (model column missing) / migration file not found.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/models/offer.py`, add the column right after the `target_url` line:
```python
    target_url_canonical: Mapped[str | None] = mapped_column(String(1024), nullable=True)
```
and add to `__table_args__` (after the existing `Index(...)`):
```python
        Index("ix_offers_target_url_canonical", "target_url_canonical", mysql_length=255),
```

Create `backend/alembic/versions/9a1c7b3e2f10_offer_target_url_canonical.py`:
```python
"""offer target_url_canonical

Revision ID: 9a1c7b3e2f10
Revises: 67382fc48c01
Create Date: 2026-07-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '9a1c7b3e2f10'
down_revision: Union[str, Sequence[str], None] = '67382fc48c01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _backfill(conn) -> None:
    from app.core.urlnorm import canonicalize_target_url
    rows = conn.execute(
        sa.text("SELECT id, target_url FROM offers WHERE target_url IS NOT NULL")
    ).fetchall()
    for rid, turl in rows:
        canon = canonicalize_target_url(turl)
        if canon:
            conn.execute(
                sa.text("UPDATE offers SET target_url_canonical = :c WHERE id = :i"),
                {"c": canon, "i": rid},
            )


def upgrade() -> None:
    op.add_column('offers', sa.Column('target_url_canonical', sa.String(length=1024), nullable=True))
    op.create_index('ix_offers_target_url_canonical', 'offers',
                    ['target_url_canonical'], mysql_length=255)
    _backfill(op.get_bind())


def downgrade() -> None:
    op.drop_index('ix_offers_target_url_canonical', table_name='offers')
    op.drop_column('offers', 'target_url_canonical')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_migration_canonical.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Verify migration runs against the DB**

Run: `./.venv/Scripts/python.exe -m alembic upgrade head && ./.venv/Scripts/python.exe -m alembic downgrade -1 && ./.venv/Scripts/python.exe -m alembic upgrade head`
Expected: no errors (upgrade adds column+index+backfill; downgrade drops them; re-upgrade clean). If the container DB isn't already at the prior head `67382fc48c01`, this walks it up first — that is fine. If alembic env/DB is unavailable, note it in the report; the authoritative backfill check is Step 4 and the column is exercised by Task 3's suite.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/offer.py backend/alembic/versions/9a1c7b3e2f10_offer_target_url_canonical.py backend/tests/test_migration_canonical.py
git commit -m "feat(backend): target_url_canonical column, index, and backfill migration"
```

---

### Task 3: canonical dedup in `create_offer` / `update_offer`

**Files:**
- Modify: `backend/app/crud/offer.py`
- Test: `backend/tests/test_offer_merge.py` (append)

**Interfaces:**
- Consumes: `canonicalize_target_url` (Task 1), `Offer.target_url_canonical` (Task 2).
- Produces: `create_offer` sets `target_url_canonical` on every new offer and dedups the crawler path on it; `update_offer` recomputes it when `target_url` changes.

- [ ] **Step 1: Write the failing tests**

```python
# append to backend/tests/test_offer_merge.py
from app.schemas.offer import OfferUpdate


def _create_admin(db, data):
    return offer_crud.create_offer(db, data, CreatedBy.admin, OfferStatus.published)


def test_merges_across_utm_www_and_scheme(db_session):
    a = _create(db_session, _offer("https://www.biz.example/deal?utm_source=a",
                                    provider="Agg1", site="https://agg1", article="https://agg1/p"))
    b = _create(db_session, _offer("http://biz.example/deal?fbclid=zz",
                                    provider="Agg2", site="https://agg2", article="https://agg2/p"))
    assert a.id == b.id
    assert len(a.links) == 2
    assert a.target_url_canonical == "biz.example/deal"


def test_different_canonical_stays_separate(db_session):
    a = _create(db_session, _offer("https://biz.example/one"))
    b = _create(db_session, _offer("https://biz.example/two"))
    assert a.id != b.id


def test_admin_does_not_dedup_but_stores_canonical(db_session):
    a = _create_admin(db_session, _offer("https://biz.example/deal"))
    b = _create_admin(db_session, _offer("https://biz.example/deal"))
    assert a.id != b.id                              # admin never dedups
    assert a.target_url_canonical == "biz.example/deal"
    assert b.target_url_canonical == "biz.example/deal"


def test_crawler_merges_into_existing_admin_offer(db_session):
    admin = _create_admin(db_session, _offer("https://biz.example/deal", provider="Admin",
                                             site="https://admin", article="https://admin/p"))
    crawler = _create(db_session, _offer("https://www.biz.example/deal?utm_source=x",
                                         provider="Crawl", site="https://c", article="https://c/p"))
    assert crawler.id == admin.id                    # preserved cross-created_by behavior
    assert {l.provider for l in admin.links} == {"Admin", "Crawl"}


def test_update_recomputes_canonical_only_on_target_change(db_session):
    o = _create(db_session, _offer("https://biz.example/old"))
    offer_crud.update_offer(db_session, o.id, OfferUpdate(title="new title"))
    assert o.target_url_canonical == "biz.example/old"      # unchanged
    offer_crud.update_offer(db_session, o.id, OfferUpdate(target_url="https://www.biz.example/new/"))
    assert o.target_url_canonical == "biz.example/new"      # recomputed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_offer_merge.py -q -k "utm_www or admin_does_not or merges_into_existing_admin or recomputes"`
Expected: FAIL — offers not merged / `target_url_canonical` is None (dedup still keys on raw `target_url`, canonical never set).

- [ ] **Step 3: Write minimal implementation**

In `backend/app/crud/offer.py`:

1. Add the import at the top:
```python
from app.core.urlnorm import canonicalize_target_url
```

2. In `create_offer`, compute the key once (right after the `_mk_link` def):
```python
    canon = canonicalize_target_url(data.target_url) if data.target_url else None
```

3. Replace the raw `target_url` dedup block (currently `if created_by == CreatedBy.crawler and data.target_url:` … matching `Offer.target_url == data.target_url`) with:
```python
    if created_by == CreatedBy.crawler and canon:
        existing = (db.query(Offer).filter(Offer.target_url_canonical == canon)
                    .order_by(Offer.id).first())
        if existing is not None:
            already = any(l.provider == data.provider and l.site_url == data.site_url
                          and l.article_url == data.article_url for l in existing.links)
            if not already:
                existing.links.append(_mk_link())
            existing.last_seen_at = datetime.utcnow()
            db.commit()
            db.refresh(existing)
            return existing
```

4. In the `Offer(...)` constructor, add the field (alongside `target_url=data.target_url`):
```python
        target_url=data.target_url, target_url_canonical=canon,
```

5. In `update_offer`, after the `for field, value in payload.items(): setattr(...)` loop (before the valid_from/until check):
```python
    if "target_url" in payload:
        obj.target_url_canonical = canonicalize_target_url(obj.target_url)
```

- [ ] **Step 4: Run tests to verify they pass, then the full suite**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_offer_merge.py -q`
Expected: PASS (all — the 4 pre-existing merge tests still green: raw-equal targets share a canonical, so they still merge).

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — 92 baseline + new tests, all green.

- [ ] **Step 5: Commit**

```bash
git add backend/app/crud/offer.py backend/tests/test_offer_merge.py
git commit -m "feat(backend): dedup offers on target_url_canonical, recompute on update"
```

---

## Final verification (after all tasks)

- [ ] Full backend suite green from `backend/`: `./.venv/Scripts/python.exe -m pytest -q`
- [ ] `alembic upgrade head` / `downgrade -1` / `upgrade head` clean.
- [ ] Request opus whole-branch review (superpowers:requesting-code-review) before merge.
- [ ] Merge to `main` (--no-ff), delete branch, push, update `docs/RESUME.md` + memory.

## Self-review notes (traceability to spec)

- Canonicalizer (spec §1) → Task 1. Column+migration+backfill (spec §2) → Task 2.
  create_offer dedup + update_offer recompute (spec §3, §4) → Task 3.
- Scope guards (spec: schemas/public/content_hash unchanged, no unique, no retro-merge) → no code; Task 3 leaves schemas untouched, Task 2 adds no unique constraint, backfill has no merge.
- Merge policy preservation → `test_crawler_merges_into_existing_admin_offer` + `test_admin_does_not_dedup_but_stores_canonical`.
