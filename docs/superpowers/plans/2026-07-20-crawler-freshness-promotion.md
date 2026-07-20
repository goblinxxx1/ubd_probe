# Crawler Freshness + Promotion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publishing a crawler offer promotes its origin page to an active passive-crawl source; the passive crawler re-confirms the offer each pass, and offers not re-confirmed for N days are marked `expired`.

**Architecture:** Backend gains an `Offer.last_seen_at` column, a promotion hook on publish (upsert `Source` from the offer origin + link + stamp `last_seen_at`), a `last_seen_at` bump whenever `create_offer` dedups an existing offer, and an internal `expire-stale` endpoint. The crawler calls `expire-stale` once per pass with a config TTL.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic (MySQL) on the backend; Python crawler with httpx `ApiClient`. Tests: pytest (`backend/tests` needs the `mysql-container` test DB; `crawler/tests` need no network).

## Global Constraints

- **Expiry conditions (all four, exact):** `status == published` AND `created_by == crawler` AND `source_id IS NOT NULL` AND `last_seen_at < now - older_than_days`. Default TTL **30 days**.
- **Promotion fires ONLY on transition to `published`**, and only when: `offer.created_by == crawler` AND `offer.source_id IS NULL` AND `normalize_source_ref(offer.site_url)` is a valid `http(s)` ref. V1 promotes **website** origins only.
- **Promoted `Source`:** `type=website`, `url_or_handle = normalize_source_ref(site_url)`, `name = offer.provider`, `is_active = True`, `created_by = crawler`. Idempotent by `(type, url_or_handle)` — reuse (and reactivate) an existing source, never duplicate.
- **content_hash stability:** setting `Source.name = offer.provider` is what makes the passive re-crawl reproduce the same `content_hash = sha256(title | provider | body)` so the re-crawl dedup-matches the published offer.
- **Unique-constraint safety:** `Offer` has `UniqueConstraint(source_id, content_hash)`. Never link an offer to a source when a different row already holds `(source.id, offer.content_hash)`.
- **`valid_until` is ignored** as an expiry signal — the only signal is re-crawl.
- `last_seen_at` is set in Python via `datetime.utcnow()` everywhere (create, dedup bump, promotion); the expiry cutoff is `datetime.utcnow() - timedelta(days=older_than_days)`.

---

### Task 1: `Offer.last_seen_at` column + migration + set on create

**Files:**
- Modify: `backend/app/models/offer.py`
- Create: `backend/alembic/versions/7f3c1a2b9d10_offer_last_seen_at.py`
- Modify: `backend/app/crud/offer.py`
- Modify: `backend/app/schemas/offer.py` (add field to `OfferOut`)
- Test: `backend/tests/test_offer_freshness.py`

**Interfaces:**
- Produces: `Offer.last_seen_at: datetime | None`; `create_offer(...)` stamps it to `datetime.utcnow()` on a newly created offer.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_offer_freshness.py`:

```python
from datetime import datetime

from app.crud import offer as offer_crud
from app.models.enums import CreatedBy, OfferStatus
from app.schemas.offer import OfferCreate


def _offer(**over):
    base = dict(type="discount", title="T", provider="P", discount_type="percent",
                discount_value="10", site_url="https://a/x", article_url="https://a/x",
                target_url="https://biz/deal")
    base.update(over)
    return OfferCreate(**base)


def test_create_sets_last_seen_at(db_session):
    o = offer_crud.create_offer(db_session, _offer(target_url=None), CreatedBy.crawler,
                                OfferStatus.pending_review, content_hash="h1")
    assert isinstance(o.last_seen_at, datetime)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_offer_freshness.py -v`
Expected: FAIL — `AttributeError: 'Offer' object has no attribute 'last_seen_at'`.

- [ ] **Step 3: Add the column to the model**

In `backend/app/models/offer.py`, add after the `content_hash` column (line ~38):

```python
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

(`datetime` and `DateTime` are already imported in this file.)

- [ ] **Step 4: Stamp it on create**

In `backend/app/crud/offer.py`, add the import at the top:

```python
from datetime import datetime, timedelta
```

In `create_offer`, in the `Offer(...)` constructor call, add `last_seen_at=datetime.utcnow(),` (put it next to `status=status`):

```python
        target_url=data.target_url, source_id=source_id,
        status=status, created_by=created_by, content_hash=content_hash,
        last_seen_at=datetime.utcnow(),
        target_categories=targets, offer_categories=offers,
        links=[_mk_link()],
```

- [ ] **Step 5: Add the field to `OfferOut`**

In `backend/app/schemas/offer.py`, in `OfferOut`, add after `updated_at: datetime`:

```python
    last_seen_at: datetime | None = None
```

- [ ] **Step 6: Create the Alembic migration**

Create `backend/alembic/versions/7f3c1a2b9d10_offer_last_seen_at.py`:

```python
"""offer last_seen_at

Revision ID: 7f3c1a2b9d10
Revises: f2585ce64af2
Create Date: 2026-07-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '7f3c1a2b9d10'
down_revision: Union[str, Sequence[str], None] = 'f2585ce64af2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('offers', sa.Column('last_seen_at', sa.DateTime(), nullable=True))
    op.execute("UPDATE offers SET last_seen_at = created_at WHERE last_seen_at IS NULL")


def downgrade() -> None:
    op.drop_column('offers', 'last_seen_at')
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_offer_freshness.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/offer.py backend/app/crud/offer.py backend/app/schemas/offer.py \
        backend/alembic/versions/7f3c1a2b9d10_offer_last_seen_at.py backend/tests/test_offer_freshness.py
git commit -m "feat(backend): add Offer.last_seen_at (column, migration, set on create)"
```

---

### Task 2: Bump `last_seen_at` when `create_offer` dedups

**Files:**
- Modify: `backend/app/crud/offer.py`
- Test: `backend/tests/test_offer_freshness.py`

**Interfaces:**
- Consumes: `Offer.last_seen_at` (Task 1).
- Produces: `create_offer` sets `existing.last_seen_at = datetime.utcnow()` whenever it returns a deduped existing offer (content_hash branch and target_url branch).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_offer_freshness.py`:

```python
def test_resubmit_same_content_hash_bumps_last_seen(db_session):
    a = offer_crud.create_offer(db_session, _offer(target_url=None), CreatedBy.crawler,
                                OfferStatus.pending_review, content_hash="h1")
    a.last_seen_at = datetime(2000, 1, 1)
    db_session.commit()
    b = offer_crud.create_offer(db_session, _offer(target_url=None), CreatedBy.crawler,
                                OfferStatus.pending_review, content_hash="h1")
    assert b.id == a.id
    assert b.last_seen_at > datetime(2000, 1, 1)


def test_resubmit_same_target_url_bumps_last_seen(db_session):
    a = offer_crud.create_offer(db_session, _offer(target_url="https://biz/deal"),
                                CreatedBy.crawler, OfferStatus.pending_review)
    a.last_seen_at = datetime(2000, 1, 1)
    db_session.commit()
    b = offer_crud.create_offer(db_session, _offer(target_url="https://biz/deal", provider="Q"),
                                CreatedBy.crawler, OfferStatus.pending_review)
    assert b.id == a.id
    assert b.last_seen_at > datetime(2000, 1, 1)
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_offer_freshness.py -v`
Expected: FAIL — the deduped offer's `last_seen_at` is not bumped (still `2000-01-01`).

- [ ] **Step 3: Bump in the content_hash branch**

In `backend/app/crud/offer.py`, change the content_hash dedup branch:

```python
        existing = q.first()
        if existing is not None:
            existing.last_seen_at = datetime.utcnow()
            db.commit()
            db.refresh(existing)
            return existing
```

- [ ] **Step 4: Bump in the target_url branch**

Change the target_url dedup branch so both the merge and no-op paths bump and commit once:

```python
    if created_by == CreatedBy.crawler and data.target_url:
        existing = db.query(Offer).filter(Offer.target_url == data.target_url).first()
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

- [ ] **Step 5: Run the full freshness + merge tests**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_offer_freshness.py tests/test_offer_merge.py -v`
Expected: PASS (new bumps pass; existing merge behaviour unchanged).

- [ ] **Step 6: Commit**

```bash
git add backend/app/crud/offer.py backend/tests/test_offer_freshness.py
git commit -m "feat(backend): bump last_seen_at when create_offer dedups an existing offer"
```

---

### Task 3: `expire_stale` CRUD + internal endpoint

**Files:**
- Modify: `backend/app/crud/offer.py`
- Modify: `backend/app/routers/internal.py`
- Test: `backend/tests/test_offer_freshness.py`, `backend/tests/test_internal.py`

**Interfaces:**
- Consumes: `Offer.last_seen_at` (Task 1).
- Produces: `offer_crud.expire_stale(db, older_than_days: int) -> int`; `POST /api/internal/offers/expire-stale` body `{older_than_days: int = 30}` → `{"expired": int}`.

- [ ] **Step 1: Write the failing CRUD test**

Append to `backend/tests/test_offer_freshness.py`:

```python
from datetime import timedelta

from app.crud import source as source_crud
from app.schemas.source import SourceCreate


def _source(db):
    return source_crud.create_source(
        db, SourceCreate(name="S", type="website", url_or_handle="https://a/x", is_active=True),
        CreatedBy.crawler)


def _published(db, source_id, last_seen, ch, created_by=CreatedBy.crawler):
    o = offer_crud.create_offer(db, _offer(target_url=None), created_by,
                                OfferStatus.published, source_id=source_id, content_hash=ch)
    o.last_seen_at = last_seen
    db.commit()
    db.refresh(o)
    return o


def test_expire_stale_marks_only_stale_promoted_published(db_session):
    s = _source(db_session)
    old = datetime.utcnow() - timedelta(days=40)
    fresh = datetime.utcnow()
    stale = _published(db_session, s.id, old, "h_stale")
    still_fresh = _published(db_session, s.id, fresh, "h_fresh")
    unpromoted = _published(db_session, None, old, "h_unpromoted")   # source_id None
    n = offer_crud.expire_stale(db_session, 30)
    db_session.refresh(stale); db_session.refresh(still_fresh); db_session.refresh(unpromoted)
    assert n == 1
    assert stale.status == OfferStatus.expired
    assert still_fresh.status == OfferStatus.published
    assert unpromoted.status == OfferStatus.published   # not promoted -> never expires
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_offer_freshness.py::test_expire_stale_marks_only_stale_promoted_published -v`
Expected: FAIL — `AttributeError: module 'app.crud.offer' has no attribute 'expire_stale'`.

- [ ] **Step 3: Implement `expire_stale`**

Add to `backend/app/crud/offer.py`:

```python
def expire_stale(db: Session, older_than_days: int) -> int:
    cutoff = datetime.utcnow() - timedelta(days=older_than_days)
    rows = db.query(Offer).filter(
        Offer.status == OfferStatus.published,
        Offer.created_by == CreatedBy.crawler,
        Offer.source_id.isnot(None),
        Offer.last_seen_at < cutoff,
    ).all()
    for o in rows:
        o.status = OfferStatus.expired
    db.commit()
    return len(rows)
```

- [ ] **Step 4: Add the internal endpoint**

In `backend/app/routers/internal.py`, add the import at the top:

```python
from pydantic import BaseModel
```

Add the request/response models and route (place after the `create_offer` route):

```python
class ExpireStaleRequest(BaseModel):
    older_than_days: int = 30


class ExpireStaleResult(BaseModel):
    expired: int


@router.post("/offers/expire-stale", response_model=ExpireStaleResult)
def expire_stale(data: ExpireStaleRequest, db: Session = Depends(get_db)):
    return ExpireStaleResult(expired=offer_crud.expire_stale(db, data.older_than_days))
```

- [ ] **Step 5: Write the endpoint test**

Append to `backend/tests/test_internal.py`:

```python
def test_expire_stale_endpoint(client, db_session):
    from datetime import datetime, timedelta
    from app.crud import offer as offer_crud
    from app.crud import source as source_crud
    from app.models.enums import CreatedBy, OfferStatus
    from app.schemas.offer import OfferCreate
    from app.schemas.source import SourceCreate

    s = source_crud.create_source(
        db_session, SourceCreate(name="S", type="website", url_or_handle="https://a/x",
                                 is_active=True), CreatedBy.crawler)
    o = offer_crud.create_offer(
        db_session, OfferCreate(type="discount", title="T", provider="P"),
        CreatedBy.crawler, OfferStatus.published, source_id=s.id, content_hash="h")
    o.last_seen_at = datetime.utcnow() - timedelta(days=40)
    db_session.commit()

    r = client.post("/api/internal/offers/expire-stale", json={"older_than_days": 30},
                    headers={"X-API-Key": settings.crawler_api_key})
    assert r.status_code == 200
    assert r.json() == {"expired": 1}
    db_session.refresh(o)
    assert o.status == OfferStatus.expired
```

- [ ] **Step 6: Run the tests**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_offer_freshness.py tests/test_internal.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/crud/offer.py backend/app/routers/internal.py \
        backend/tests/test_offer_freshness.py backend/tests/test_internal.py
git commit -m "feat(backend): expire-stale internal endpoint marks unconfirmed promoted offers expired"
```

---

### Task 4: URL normalizer + `Source` upsert helper

**Files:**
- Create: `backend/app/core/urlnorm.py`
- Modify: `backend/app/crud/source.py`
- Test: `backend/tests/test_sources.py`

**Interfaces:**
- Produces: `normalize_source_ref(url: str) -> str | None`; `source_crud.get_or_create_source_by_ref(db, type_, url_or_handle, name, created_by) -> Source`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_sources.py`:

```python
def test_normalize_source_ref():
    from app.core.urlnorm import normalize_source_ref
    assert normalize_source_ref("HTTPS://Shop.Example.com/deal/?utm_source=x#frag") \
        == "https://shop.example.com/deal"
    assert normalize_source_ref("https://ex.com/") == "https://ex.com"
    assert normalize_source_ref("not a url") is None
    assert normalize_source_ref("") is None


def test_get_or_create_source_by_ref_creates_then_reuses(db_session):
    from app.crud import source as source_crud
    from app.models.enums import CreatedBy, SourceType
    a = source_crud.get_or_create_source_by_ref(
        db_session, SourceType.website, "https://shop.example/deal", "Shop", CreatedBy.crawler)
    b = source_crud.get_or_create_source_by_ref(
        db_session, SourceType.website, "https://shop.example/deal", "Shop", CreatedBy.crawler)
    assert a.id == b.id
    assert a.name == "Shop" and a.type == SourceType.website and a.is_active is True


def test_get_or_create_source_by_ref_reactivates(db_session):
    from app.crud import source as source_crud
    from app.models.enums import CreatedBy, SourceType
    a = source_crud.get_or_create_source_by_ref(
        db_session, SourceType.website, "https://shop.example/x", "Shop", CreatedBy.crawler)
    a.is_active = False
    db_session.commit()
    b = source_crud.get_or_create_source_by_ref(
        db_session, SourceType.website, "https://shop.example/x", "Shop", CreatedBy.crawler)
    assert b.id == a.id and b.is_active is True
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_sources.py -k "normalize or get_or_create" -v`
Expected: FAIL — `ModuleNotFoundError: app.core.urlnorm` / no `get_or_create_source_by_ref`.

- [ ] **Step 3: Create the normalizer**

Create `backend/app/core/urlnorm.py`:

```python
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def normalize_source_ref(url: str) -> str | None:
    """Canonical http(s) ref for source dedup: lowercased host, no trailing slash,
    no fragment, utm_* query params stripped. Returns None for non-http(s)/junk."""
    if not url:
        return None
    p = urlsplit(url.strip())
    if p.scheme not in ("http", "https") or not p.netloc:
        return None
    query = urlencode([(k, v) for k, v in parse_qsl(p.query)
                       if not k.lower().startswith("utm_")])
    path = p.path.rstrip("/")
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), path, query, ""))
```

- [ ] **Step 4: Add the upsert helper**

In `backend/app/crud/source.py`, add the import and function:

```python
from app.models.enums import CreatedBy, SourceType
```

```python
def get_or_create_source_by_ref(db: Session, type_: SourceType, url_or_handle: str,
                                name: str, created_by: CreatedBy) -> Source:
    existing = db.query(Source).filter(Source.type == type_,
                                       Source.url_or_handle == url_or_handle).first()
    if existing is not None:
        if not existing.is_active:
            existing.is_active = True
            db.commit()
            db.refresh(existing)
        return existing
    obj = Source(name=name, type=type_, url_or_handle=url_or_handle,
                 is_active=True, created_by=created_by)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj
```

(The existing `from app.models.enums import CreatedBy` import — merge the `SourceType` addition into it rather than duplicating.)

- [ ] **Step 5: Run the tests**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_sources.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/urlnorm.py backend/app/crud/source.py backend/tests/test_sources.py
git commit -m "feat(backend): source ref normalizer + get_or_create_source_by_ref upsert"
```

---

### Task 5: Promotion on publish

**Files:**
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/promotion.py`
- Modify: `backend/app/routers/admin.py`
- Test: `backend/tests/test_promotion.py`

**Interfaces:**
- Consumes: `normalize_source_ref` + `get_or_create_source_by_ref` (Task 4); `Offer.last_seen_at` (Task 1).
- Produces: `promotion.maybe_promote_on_publish(db, offer: Offer) -> None`, called from `publish_offer`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_promotion.py`:

```python
from app.crud import offer as offer_crud
from app.models import Offer, Source
from app.models.enums import CreatedBy, OfferStatus, SourceType
from app.schemas.offer import OfferCreate
from app.services import promotion


def _crawler_offer(db, **over):
    base = dict(type="discount", title="T", provider="Shop",
                site_url="https://shop.example/deal", article_url="https://shop.example/deal")
    base.update(over)
    o = offer_crud.create_offer(db, OfferCreate(**base), CreatedBy.crawler,
                                OfferStatus.published, content_hash=over.get("content_hash", "h1"))
    return o


def test_publish_promotes_website_origin(db_session):
    o = _crawler_offer(db_session)
    promotion.maybe_promote_on_publish(db_session, o)
    db_session.refresh(o)
    src = db_session.get(Source, o.source_id)
    assert src is not None
    assert src.type == SourceType.website
    assert src.url_or_handle == "https://shop.example/deal"
    assert src.name == "Shop"           # name == provider -> stable content_hash on re-crawl
    assert src.is_active is True
    assert o.last_seen_at is not None


def test_promotion_is_idempotent_across_offers_sharing_origin(db_session):
    o1 = _crawler_offer(db_session, content_hash="h1")
    o2 = _crawler_offer(db_session, title="T2", content_hash="h2")
    promotion.maybe_promote_on_publish(db_session, o1)
    promotion.maybe_promote_on_publish(db_session, o2)
    db_session.refresh(o1); db_session.refresh(o2)
    assert o1.source_id == o2.source_id
    assert db_session.query(Source).count() == 1


def test_no_promotion_for_admin_offer(db_session):
    o = offer_crud.create_offer(
        db_session, OfferCreate(type="discount", title="T", provider="P",
                                site_url="https://shop.example/deal"),
        CreatedBy.admin, OfferStatus.published, content_hash="h1")
    promotion.maybe_promote_on_publish(db_session, o)
    db_session.refresh(o)
    assert o.source_id is None
    assert db_session.query(Source).count() == 0


def test_no_promotion_without_site_url(db_session):
    o = _crawler_offer(db_session, site_url=None)
    promotion.maybe_promote_on_publish(db_session, o)
    db_session.refresh(o)
    assert o.source_id is None
    assert db_session.query(Source).count() == 0


def test_no_promotion_when_already_sourced(db_session):
    from app.crud import source as source_crud
    from app.schemas.source import SourceCreate
    s = source_crud.create_source(
        db_session, SourceCreate(name="Existing", type="website",
                                 url_or_handle="https://other/x", is_active=True),
        CreatedBy.admin)
    o = offer_crud.create_offer(
        db_session, OfferCreate(type="discount", title="T", provider="Shop",
                                site_url="https://shop.example/deal"),
        CreatedBy.crawler, OfferStatus.published, source_id=s.id, content_hash="h1")
    promotion.maybe_promote_on_publish(db_session, o)
    db_session.refresh(o)
    assert o.source_id == s.id           # unchanged
    assert db_session.query(Source).count() == 1


def test_promotion_respects_unique_constraint(db_session):
    # A source already exists for the origin, with an offer holding (source_id, "h1").
    from app.crud import source as source_crud
    from app.schemas.source import SourceCreate
    s = source_crud.get_or_create_source_by_ref(
        db_session, SourceType.website, "https://shop.example/deal", "Shop", CreatedBy.crawler)
    offer_crud.create_offer(
        db_session, OfferCreate(type="discount", title="Prior", provider="Shop",
                                site_url="https://shop.example/deal"),
        CreatedBy.crawler, OfferStatus.pending_review, source_id=s.id, content_hash="h1")
    # New offer, same origin, same content_hash, not yet sourced.
    o = _crawler_offer(db_session, content_hash="h1")
    promotion.maybe_promote_on_publish(db_session, o)   # must not raise / must not violate uq
    db_session.refresh(o)
    assert o.source_id is None           # left unlinked; existing row already represents it
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_promotion.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.promotion`.

- [ ] **Step 3: Create the services package**

Create `backend/app/services/__init__.py` (empty file):

```python
```

- [ ] **Step 4: Implement the promotion service**

Create `backend/app/services/promotion.py`:

```python
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.urlnorm import normalize_source_ref
from app.crud import source as source_crud
from app.models import Offer
from app.models.enums import CreatedBy, SourceType


def maybe_promote_on_publish(db: Session, offer: Offer) -> None:
    """On publish, promote a crawler offer's website origin to an active passive-crawl
    source and link the offer to it, so the passive crawler re-confirms it (freshness).
    No-op unless the offer is a crawler offer, not already sourced, with a valid http(s)
    site_url. Idempotent by (type, url_or_handle)."""
    if offer.created_by != CreatedBy.crawler or offer.source_id is not None:
        return
    ref = normalize_source_ref(offer.site_url or "")
    if ref is None:
        return
    source = source_crud.get_or_create_source_by_ref(
        db, SourceType.website, ref, offer.provider, CreatedBy.crawler)
    if offer.content_hash is not None:
        clash = db.query(Offer).filter(Offer.source_id == source.id,
                                       Offer.content_hash == offer.content_hash,
                                       Offer.id != offer.id).first()
        if clash is not None:
            # Existing row already represents this offer under the source; do not
            # violate UniqueConstraint(source_id, content_hash). Leave it unlinked.
            offer.last_seen_at = datetime.utcnow()
            db.commit()
            return
    offer.source_id = source.id
    offer.last_seen_at = datetime.utcnow()
    db.commit()
    db.refresh(offer)
```

- [ ] **Step 5: Wire it into publish**

In `backend/app/routers/admin.py`, add the import:

```python
from app.services import promotion
```

Change `publish_offer` (line ~94) to promote after setting status:

```python
@router.post("/offers/{offer_id}/publish", response_model=OfferOut)
def publish_offer(offer_id: int, db: Session = Depends(get_db),
                  admin=Depends(get_current_admin)):
    offer = offer_crud.set_status(db, offer_id, OfferStatus.published, admin.id)
    promotion.maybe_promote_on_publish(db, offer)
    return offer
```

(Keep the existing parameter list / dependencies exactly as they were; only the body changes to capture `offer` and call promotion.)

- [ ] **Step 6: Write the publish→promotion integration test**

Append to `backend/tests/test_promotion.py`:

```python
def test_publish_endpoint_promotes(client, db_session):
    from app.core.security import create_access_token
    from app.models import AdminUser
    from app.models.enums import AdminRole
    admin = AdminUser(email="mod@example.com", password_hash="x", role=AdminRole.moderator)
    db_session.add(admin); db_session.commit()
    token = create_access_token(subject=admin.email, role="moderator")

    pending = offer_crud.create_offer(
        db_session, OfferCreate(type="discount", title="Crawled", provider="Shop",
                                site_url="https://shop.example/deal"),
        CreatedBy.crawler, OfferStatus.pending_review, content_hash="h1")

    r = client.post(f"/api/admin/offers/{pending.id}/publish",
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.json()["status"] == "published"
    db_session.refresh(pending)
    assert pending.source_id is not None
    assert db_session.get(Source, pending.source_id).name == "Shop"
```

- [ ] **Step 7: Run the promotion + admin tests**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_promotion.py tests/test_offers_admin.py -v`
Expected: PASS (promotion works; existing admin publish tests still green).

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/__init__.py backend/app/services/promotion.py \
        backend/app/routers/admin.py backend/tests/test_promotion.py
git commit -m "feat(backend): promote crawler offer origin to active source on publish"
```

---

### Task 6: Crawler — `FRESHNESS_TTL_DAYS` + `expire_stale` call each pass

**Files:**
- Modify: `crawler/crawler/config.py`
- Modify: `crawler/crawler/api_client.py`
- Modify: `crawler/crawler/runner.py`
- Modify: `crawler/crawler/wiring.py`
- Modify: `crawler/.env.example`
- Test: `crawler/tests/test_config.py`, `crawler/tests/test_runner.py`

**Interfaces:**
- Consumes: `POST /api/internal/offers/expire-stale` (Task 3).
- Produces: `Config.freshness_ttl_days: int`; `ApiClient.expire_stale(older_than_days) -> dict`; `Runner` calls it once per pass and folds `expired` into the summary.

- [ ] **Step 1: Write the failing config test**

Append to `crawler/tests/test_config.py` (follow the file's existing pattern for building a config; the assertion is what matters):

```python
def test_freshness_ttl_days_default_and_override(monkeypatch):
    from crawler.config import load_config
    monkeypatch.delenv("FRESHNESS_TTL_DAYS", raising=False)
    assert load_config().freshness_ttl_days == 30
    monkeypatch.setenv("FRESHNESS_TTL_DAYS", "7")
    assert load_config().freshness_ttl_days == 7
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_config.py -k freshness -v`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'freshness_ttl_days'`.

- [ ] **Step 3: Add the config knob**

In `crawler/crawler/config.py`:
- In `_RawSettings`, add: `freshness_ttl_days: int = 30`
- In `Config` (dataclass), add: `freshness_ttl_days: int = 30`
- In `load_config()`'s `Config(...)` call, add: `freshness_ttl_days=s.freshness_ttl_days,`

- [ ] **Step 4: Add the API client method**

In `crawler/crawler/api_client.py`, add to the internal section:

```python
    def expire_stale(self, older_than_days: int) -> dict:
        r = self._client.post("/api/internal/offers/expire-stale",
                              json={"older_than_days": older_than_days})
        r.raise_for_status()
        return r.json()
```

- [ ] **Step 5: Write the failing runner test**

In `crawler/tests/test_runner.py`, add an `expire_stale` method to `FakeApi` (record calls, return a count):

```python
    def expire_stale(self, older_than_days):
        self.expired_calls.append(older_than_days)
        return {"expired": 2}
```

and initialise `self.expired_calls = []` in `FakeApi.__init__`. Then add the test:

```python
def test_runner_calls_expire_stale_and_reports_count():
    src = {"id": 1, "type": "website", "name": "Shop", "url_or_handle": "http://x"}
    item = RawItem(source_id=1, platform="website", key="k", text="Акція 10%", links=[])
    api = FakeApi([src])
    runner = Runner(api, {"website": FakeFetcher([item])}, get_extractor("heuristic"), _rl(),
                    freshness_ttl_days=14)
    summary = runner.run()
    assert api.expired_calls == [14]
    assert summary["expired"] == 2
```

- [ ] **Step 6: Run to verify it fails**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_runner.py::test_runner_calls_expire_stale_and_reports_count -v`
Expected: FAIL — `Runner.__init__` has no `freshness_ttl_days` / summary has no `expired`.

- [ ] **Step 7: Wire the runner**

In `crawler/crawler/runner.py`:
- Add `freshness_ttl_days=30` to `Runner.__init__` params and store `self._freshness_ttl_days = freshness_ttl_days`.
- Initialise the summary with `"expired": 0`:

```python
        summary = {"sources": 0, "offers": 0, "suggestions": 0, "expired": 0, "errors": 0}
```

- After the discovery/harvest block and before `log.info("crawl summary: %s", summary)`, add:

```python
        try:
            result = self._api.expire_stale(self._freshness_ttl_days)
            summary["expired"] = result.get("expired", 0)
        except Exception as exc:  # noqa: BLE001 — sweep must not crash the pass
            summary["errors"] += 1
            log.warning("expire-stale failed: %s", exc)
```

- [ ] **Step 8: Pass the config through wiring**

In `crawler/crawler/wiring.py`, extend the `Runner(...)` construction (line ~54) to pass the knob:

```python
    return Runner(api, fetchers, extractor, rate_limiter,
                  discovery=discovery, keywords=config.search_keywords, harvester=harvester,
                  freshness_ttl_days=config.freshness_ttl_days)
```

- [ ] **Step 9: Document the env var**

In `crawler/.env.example`, add near the other search/crawl settings:

```
# Freshness: published crawler offers not re-confirmed by a passive re-crawl within this
# many days are marked expired (drops off the public site). Signal is re-crawl only.
FRESHNESS_TTL_DAYS=30
```

- [ ] **Step 10: Run the crawler suite**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — whole crawler suite green (existing runner tests unaffected; `expired` added to summary).

- [ ] **Step 11: Commit**

```bash
git add crawler/crawler/config.py crawler/crawler/api_client.py crawler/crawler/runner.py \
        crawler/crawler/wiring.py crawler/.env.example \
        crawler/tests/test_config.py crawler/tests/test_runner.py
git commit -m "feat(crawler): call expire-stale each pass with FRESHNESS_TTL_DAYS, report expired count"
```

---

## Self-Review

**1. Spec coverage:**
- Promotion on publish → Task 5 (+ Task 4 upsert/normalizer). ✔
- `Offer.last_seen_at` + migration + set on create → Task 1. ✔
- content_hash stability (source.name=provider) → Task 5 (`get_or_create_source_by_ref(..., offer.provider, ...)`), asserted in `test_publish_promotes_website_origin`. ✔
- Freshness bump on dedup (both branches) → Task 2. ✔
- Expiry sweep endpoint + four conditions → Task 3. ✔
- Crawler calls sweep each pass + config TTL + summary → Task 6. ✔
- Unique-constraint safety → Task 5 (`test_promotion_respects_unique_constraint`). ✔
- Out of scope (Track 3, telegram, non-promoted expiry, valid_until) → none added. ✔

**2. Placeholder scan:** No TBD/TODO; every code step shows full code. ✔

**3. Type consistency:** `last_seen_at: datetime | None`, `expire_stale(db, older_than_days: int) -> int`, `get_or_create_source_by_ref(db, type_, url_or_handle, name, created_by)`, `maybe_promote_on_publish(db, offer)`, `ApiClient.expire_stale(older_than_days)`, `Runner(..., freshness_ttl_days=...)`, summary key `"expired"` — names/signatures identical across Tasks 1-6 and their tests. Endpoint `POST /api/internal/offers/expire-stale` body `{older_than_days}` matches client. ✔

**Note on migrations:** backend tests build the schema via `Base.metadata.create_all` (conftest), so they exercise the model column, not the Alembic migration. Verify the migration itself against the real DB with `alembic upgrade head` (Docker / live check) as part of final review.
