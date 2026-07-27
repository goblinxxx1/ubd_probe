# Пасивна ре-модерація заапрувлених джерел — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заапрувлене джерело не пропонується повторно; при пасивному обході зміна знижки/контенту наявного published-офера заводиться в модерацію як лінкований shadow-офер (без дублів, старе published живе до підтвердження), а незмінний офер лише тихо бампає `last_seen_at`.

**Architecture:** Уся логіка — backend-side. `create_offer` дістає гілку детекції зміни: same-source+same-canon зміна published-офера → створює/оновлює один `pending_review` shadow з `supersedes_offer_id`. `set_status` при публікації shadow гасить parent. Серверний guard у `create_suggestion` відсікає suggestions для вже-активних Sources. Admin показує маркер «замінює #X». Краулер не чіпаємо.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, pytest (backend, MySQL на :3306); Vue 3 + Element Plus, Vitest (admin).

## Global Constraints

- **Crauler baseline незмінний: 420 тестів мають лишитися зеленими** (у цьому треку краулер не редагується — лише перевірити, що нічого не поламали суміжно).
- **Backend baseline: 106** тестів; додаємо нові. Тести потребують `mysql-container` на :3306 → `docker start mysql-container`.
- **Admin baseline: 97** тестів + `npm run build` має проходити (Vitest не ловить scoped-Less-помилки — build обовʼязковий).
- Backend-тести йдуть через `Base.metadata.create_all` з моделей (не через міграції) — модельна колонка стає видимою тестам одразу; Alembic-міграція потрібна для реальної БД.
- Alembic head зараз: `9a1c7b3e2f10`. Нова міграція має `down_revision = '9a1c7b3e2f10'`.
- UI-копірайт — українською.
- Запуск backend-тестів (з активованим venv проєкту): `cd backend && python -m pytest <path> -v`.
- Запуск admin-тестів: `cd admin && npm test`; білд: `cd admin && npm run build`.

---

### Task 1: Модель + міграція `supersedes_offer_id`

**Files:**
- Modify: `backend/app/models/offer.py`
- Create: `backend/alembic/versions/b2d4f6a80c11_offer_supersedes.py`
- Test: `backend/tests/test_offer_supersedes_model.py`

**Interfaces:**
- Produces: `Offer.supersedes_offer_id: int | None` (self-FK → `offers.id`, ON DELETE SET NULL) та relationship `Offer.supersedes: Offer | None` (remote_side=id). Later tasks читають/пишуть це поле.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_offer_supersedes_model.py`:

```python
from app.crud import offer as offer_crud
from app.models import Offer
from app.models.enums import CreatedBy, OfferStatus
from app.schemas.offer import OfferCreate


def _offer(**over):
    base = dict(type="discount", title="T", provider="P", discount_type="percent",
                discount_value="10", site_url="https://a/x", article_url="https://a/x",
                target_url="https://biz/deal")
    base.update(over)
    return OfferCreate(**base)


def test_supersedes_link_roundtrips(db_session):
    parent = offer_crud.create_offer(db_session, _offer(target_url=None), CreatedBy.crawler,
                                     OfferStatus.published, content_hash="p")
    child = Offer(type="discount", title="C", description="", provider="P",
                  status=OfferStatus.pending_review, created_by=CreatedBy.crawler,
                  supersedes_offer_id=parent.id)
    db_session.add(child)
    db_session.commit()
    db_session.refresh(child)
    assert child.supersedes_offer_id == parent.id
    assert child.supersedes.id == parent.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_offer_supersedes_model.py -v`
Expected: FAIL — `AttributeError`/`TypeError` (no `supersedes_offer_id`).

- [ ] **Step 3: Add the column + relationship to the model**

In `backend/app/models/offer.py`, after the `reviewed_by` column (line ~43) add:

```python
    supersedes_offer_id: Mapped[int | None] = mapped_column(
        ForeignKey("offers.id", ondelete="SET NULL"), nullable=True
    )
```

And after the `links` relationship (line ~57) add:

```python
    supersedes: Mapped["Offer | None"] = relationship(
        "Offer", remote_side="Offer.id", foreign_keys="Offer.supersedes_offer_id",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_offer_supersedes_model.py -v`
Expected: PASS.

- [ ] **Step 5: Write the Alembic migration**

Create `backend/alembic/versions/b2d4f6a80c11_offer_supersedes.py`:

```python
"""offer supersedes_offer_id

Revision ID: b2d4f6a80c11
Revises: 9a1c7b3e2f10
Create Date: 2026-07-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b2d4f6a80c11'
down_revision: Union[str, Sequence[str], None] = '9a1c7b3e2f10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('offers', sa.Column('supersedes_offer_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_offers_supersedes', 'offers', 'offers',
                          ['supersedes_offer_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint('fk_offers_supersedes', 'offers', type_='foreignkey')
    op.drop_column('offers', 'supersedes_offer_id')
```

- [ ] **Step 6: Run the whole backend suite (regression baseline)**

Run: `cd backend && python -m pytest -q`
Expected: 106 passed + 1 new (test_supersedes_link_roundtrips) → all green.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/offer.py backend/alembic/versions/b2d4f6a80c11_offer_supersedes.py backend/tests/test_offer_supersedes_model.py
git commit -m "feat(backend): add offers.supersedes_offer_id self-FK + migration"
```

---

### Task 2: Детекція зміни в `create_offer` (shadow-логіка)

**Files:**
- Modify: `backend/app/crud/offer.py` (`create_offer`, + helper `_apply_content`)
- Test: `backend/tests/test_offer_shadow.py`

**Interfaces:**
- Consumes: `Offer.supersedes_offer_id` (Task 1); `canonicalize_target_url`; `OfferStatus`.
- Produces: `create_offer` behaviour — same-source+same-canon зміна published-офера повертає pending_review shadow з `supersedes_offer_id=parent.id`; ідемпотентний; parent лишається published і бампає last_seen.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_offer_shadow.py`:

```python
from datetime import datetime

from app.crud import offer as offer_crud
from app.crud import source as source_crud
from app.models.enums import CreatedBy, OfferStatus
from app.schemas.offer import OfferCreate
from app.schemas.source import SourceCreate


def _offer(**over):
    base = dict(type="discount", title="T", provider="P", discount_type="percent",
                discount_value="10", site_url="https://a/x", article_url="https://a/x",
                target_url="https://biz/deal")
    base.update(over)
    return OfferCreate(**base)


def _source(db):
    return source_crud.create_source(
        db, SourceCreate(name="S", type="website", url_or_handle="https://a/x", is_active=True),
        CreatedBy.crawler)


def _published(db, sid, ch, value="10"):
    o = offer_crud.create_offer(db, _offer(discount_value=value), CreatedBy.crawler,
                                OfferStatus.published, source_id=sid, content_hash=ch)
    return o


def test_changed_discount_creates_linked_shadow(db_session):
    s = _source(db_session)
    p = _published(db_session, s.id, "h1", value="10")
    shadow = offer_crud.create_offer(db_session, _offer(discount_value="20"), CreatedBy.crawler,
                                     OfferStatus.pending_review, source_id=s.id, content_hash="h2")
    assert shadow.id != p.id
    assert shadow.status == OfferStatus.pending_review
    assert shadow.supersedes_offer_id == p.id
    assert str(shadow.discount_value) == "20.00"
    db_session.refresh(p)
    assert p.status == OfferStatus.published            # parent stays live


def test_change_bumps_parent_last_seen(db_session):
    s = _source(db_session)
    p = _published(db_session, s.id, "h1")
    p.last_seen_at = datetime(2000, 1, 1)
    db_session.commit()
    offer_crud.create_offer(db_session, _offer(discount_value="20"), CreatedBy.crawler,
                            OfferStatus.pending_review, source_id=s.id, content_hash="h2")
    db_session.refresh(p)
    assert p.last_seen_at > datetime(2000, 1, 1)


def test_repeated_change_updates_single_shadow(db_session):
    s = _source(db_session)
    p = _published(db_session, s.id, "h1")
    a = offer_crud.create_offer(db_session, _offer(discount_value="20"), CreatedBy.crawler,
                                OfferStatus.pending_review, source_id=s.id, content_hash="h2")
    b = offer_crud.create_offer(db_session, _offer(discount_value="30"), CreatedBy.crawler,
                                OfferStatus.pending_review, source_id=s.id, content_hash="h3")
    assert b.id == a.id                                 # same shadow, updated in place
    assert str(b.discount_value) == "30.00"
    assert b.content_hash == "h3"


def test_unchanged_published_rewalk_bumps_no_shadow(db_session):
    s = _source(db_session)
    p = _published(db_session, s.id, "h1")
    again = offer_crud.create_offer(db_session, _offer(discount_value="10"), CreatedBy.crawler,
                                    OfferStatus.pending_review, source_id=s.id, content_hash="h1")
    assert again.id == p.id                             # content_hash match -> bump, no shadow


def test_pending_first_submission_updates_in_place(db_session):
    s = _source(db_session)
    q = offer_crud.create_offer(db_session, _offer(discount_value="10"), CreatedBy.crawler,
                                OfferStatus.pending_review, source_id=s.id, content_hash="h1")
    r = offer_crud.create_offer(db_session, _offer(discount_value="20"), CreatedBy.crawler,
                                OfferStatus.pending_review, source_id=s.id, content_hash="h2")
    assert r.id == q.id                                 # no shadow while still pending
    assert r.supersedes_offer_id is None
    assert str(r.discount_value) == "20.00"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_offer_shadow.py -v`
Expected: FAIL — changed submissions currently get swallowed by canon-merge (`shadow.id == p.id`, no `supersedes_offer_id`).

- [ ] **Step 3: Implement the change-detection branches**

In `backend/app/crud/offer.py`, add a helper above `create_offer`:

```python
def _apply_content(obj, data, canon, content_hash, targets, offers, mk_link):
    obj.type = data.type
    obj.title = data.title
    obj.description = data.description
    obj.provider = data.provider
    obj.location = data.location
    obj.valid_from = data.valid_from
    obj.valid_until = data.valid_until
    obj.discount_type = data.discount_type
    obj.discount_value = data.discount_value
    obj.site_url = data.site_url
    obj.article_url = data.article_url
    obj.image_url = data.image_url
    obj.target_url = data.target_url
    obj.target_url_canonical = canon
    obj.content_hash = content_hash
    obj.target_categories = targets
    obj.offer_categories = offers
    obj.links = [mk_link()]
    obj.last_seen_at = datetime.utcnow()
```

Then replace the crawler-dedup block (current lines 27-51, from `canon = ...` down to the end of the canon-merge `if`) with:

```python
    canon = canonicalize_target_url(data.target_url) if data.target_url else None
    crawler = created_by == CreatedBy.crawler

    # 1) Unchanged (or idempotent repeat of an existing shadow): same source + content_hash.
    if content_hash is not None and crawler:
        q = db.query(Offer).filter(Offer.content_hash == content_hash)
        q = (q.filter(Offer.source_id == source_id) if source_id is not None
             else q.filter(Offer.source_id.is_(None)))
        existing = q.first()
        if existing is not None:
            existing.last_seen_at = datetime.utcnow()
            if existing.supersedes_offer_id is not None:
                parent = db.get(Offer, existing.supersedes_offer_id)
                if parent is not None:
                    parent.last_seen_at = datetime.utcnow()
            db.commit()
            db.refresh(existing)
            return existing

    # Same-source change detection needs a canonical key and a source.
    if crawler and canon and source_id is not None:
        # 2) Change of a live (published) offer from this same source+target -> shadow.
        parent = (db.query(Offer)
                  .filter(Offer.source_id == source_id,
                          Offer.target_url_canonical == canon,
                          Offer.status == OfferStatus.published)
                  .order_by(Offer.id).first())
        if parent is not None:
            targets, offers = _load_categories(db, data.target_category_ids, data.offer_category_ids)
            shadow = (db.query(Offer)
                      .filter(Offer.supersedes_offer_id == parent.id,
                              Offer.status == OfferStatus.pending_review)
                      .order_by(Offer.id).first())
            if shadow is None:
                shadow = Offer(status=OfferStatus.pending_review, created_by=CreatedBy.crawler,
                               source_id=source_id, supersedes_offer_id=parent.id)
                db.add(shadow)
            _apply_content(shadow, data, canon, content_hash, targets, offers, _mk_link)
            parent.last_seen_at = datetime.utcnow()
            db.commit()
            db.refresh(shadow)
            return shadow

        # 3) First submission still pending (not yet approved) -> update in place, no shadow.
        pending = (db.query(Offer)
                   .filter(Offer.source_id == source_id,
                           Offer.target_url_canonical == canon,
                           Offer.status == OfferStatus.pending_review,
                           Offer.supersedes_offer_id.is_(None))
                   .order_by(Offer.id).first())
        if pending is not None:
            targets, offers = _load_categories(db, data.target_category_ids, data.offer_category_ids)
            _apply_content(pending, data, canon, content_hash, targets, offers, _mk_link)
            db.commit()
            db.refresh(pending)
            return pending

    # 4) Cross-source canonical merge (aggregator / cross-platform) — existing behavior.
    if crawler and canon:
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

Note: the final "new row" block (current lines 53-68) stays unchanged — a fresh `Offer(...)` with `supersedes_offer_id` defaulting to NULL.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_offer_shadow.py -v`
Expected: PASS (all 5).

- [ ] **Step 5: Run offer-merge + freshness regression**

Run: `cd backend && python -m pytest tests/test_offer_merge.py tests/test_offer_freshness.py -v`
Expected: PASS (cross-source merge + freshness behavior preserved).

- [ ] **Step 6: Commit**

```bash
git add backend/app/crud/offer.py backend/tests/test_offer_shadow.py
git commit -m "feat(backend): shadow-offer on same-source discount/content change"
```

---

### Task 3: Approve-supersede у `set_status`

**Files:**
- Modify: `backend/app/crud/offer.py` (`set_status`)
- Test: `backend/tests/test_offer_supersede_publish.py`

**Interfaces:**
- Consumes: `Offer.supersedes_offer_id` (Task 1), shadow creation (Task 2).
- Produces: publish shadow → shadow published, parent expired; reject shadow → parent untouched.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_offer_supersede_publish.py`:

```python
from app.crud import offer as offer_crud
from app.crud import source as source_crud
from app.models import AdminUser
from app.models.enums import AdminRole, CreatedBy, OfferStatus
from app.schemas.offer import OfferCreate
from app.schemas.source import SourceCreate


def _offer(**over):
    base = dict(type="discount", title="T", provider="P", discount_type="percent",
                discount_value="10", site_url="https://a/x", article_url="https://a/x",
                target_url="https://biz/deal")
    base.update(over)
    return OfferCreate(**base)


def _admin(db):
    a = AdminUser(email="m@example.com", password_hash="x", role=AdminRole.moderator)
    db.add(a); db.commit(); db.refresh(a)
    return a


def _setup_shadow(db):
    s = source_crud.create_source(
        db, SourceCreate(name="S", type="website", url_or_handle="https://a/x", is_active=True),
        CreatedBy.crawler)
    p = offer_crud.create_offer(db, _offer(discount_value="10"), CreatedBy.crawler,
                                OfferStatus.published, source_id=s.id, content_hash="h1")
    shadow = offer_crud.create_offer(db, _offer(discount_value="20"), CreatedBy.crawler,
                                     OfferStatus.pending_review, source_id=s.id, content_hash="h2")
    return p, shadow


def test_publish_shadow_expires_parent(db_session):
    p, shadow = _setup_shadow(db_session)
    admin = _admin(db_session)
    offer_crud.set_status(db_session, shadow.id, OfferStatus.published, admin.id)
    db_session.refresh(p); db_session.refresh(shadow)
    assert shadow.status == OfferStatus.published
    assert p.status == OfferStatus.expired


def test_reject_shadow_leaves_parent_published(db_session):
    p, shadow = _setup_shadow(db_session)
    admin = _admin(db_session)
    offer_crud.set_status(db_session, shadow.id, OfferStatus.rejected, admin.id)
    db_session.refresh(p); db_session.refresh(shadow)
    assert shadow.status == OfferStatus.rejected
    assert p.status == OfferStatus.published
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_offer_supersede_publish.py -v`
Expected: FAIL — `test_publish_shadow_expires_parent` fails (parent still published).

- [ ] **Step 3: Implement supersede-on-publish in `set_status`**

In `backend/app/crud/offer.py`, replace the body of `set_status` (current lines 127-135) with:

```python
def set_status(db: Session, offer_id: int, status: OfferStatus, reviewed_by: int) -> Offer:
    obj = get_offer(db, offer_id)
    obj.status = status
    obj.reviewed_by = reviewed_by
    if status == OfferStatus.published:
        obj.last_seen_at = datetime.utcnow()
        if obj.supersedes_offer_id is not None:
            parent = db.get(Offer, obj.supersedes_offer_id)
            if parent is not None and parent.status == OfferStatus.published:
                parent.status = OfferStatus.expired
    db.commit()
    db.refresh(obj)
    return obj
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_offer_supersede_publish.py tests/test_offer_freshness.py -v`
Expected: PASS (new supersede tests + existing set_status freshness tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/crud/offer.py backend/tests/test_offer_supersede_publish.py
git commit -m "feat(backend): publishing a shadow expires its superseded parent"
```

---

### Task 4: `OfferOut` віддає supersede-контекст

**Files:**
- Modify: `backend/app/schemas/offer.py`
- Test: `backend/tests/test_offer_out_supersedes.py`

**Interfaces:**
- Consumes: `Offer.supersedes` relationship (Task 1), shadow (Task 2).
- Produces: `OfferOut.supersedes_offer_id: int | None`, `OfferOut.supersedes: SupersedesOut | None` (id, title, discount_type, discount_value). Admin UI (Task 6) reads these.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_offer_out_supersedes.py`:

```python
from app.crud import offer as offer_crud
from app.crud import source as source_crud
from app.models.enums import CreatedBy, OfferStatus
from app.schemas.offer import OfferCreate, OfferOut
from app.schemas.source import SourceCreate


def _offer(**over):
    base = dict(type="discount", title="T", provider="P", discount_type="percent",
                discount_value="10", site_url="https://a/x", article_url="https://a/x",
                target_url="https://biz/deal")
    base.update(over)
    return OfferCreate(**base)


def test_offer_out_exposes_supersede_context(db_session):
    s = source_crud.create_source(
        db_session, SourceCreate(name="S", type="website", url_or_handle="https://a/x", is_active=True),
        CreatedBy.crawler)
    p = offer_crud.create_offer(db_session, _offer(title="Parent", discount_value="10"),
                                CreatedBy.crawler, OfferStatus.published,
                                source_id=s.id, content_hash="h1")
    shadow = offer_crud.create_offer(db_session, _offer(discount_value="20"), CreatedBy.crawler,
                                     OfferStatus.pending_review, source_id=s.id, content_hash="h2")
    out = OfferOut.model_validate(shadow)
    assert out.supersedes_offer_id == p.id
    assert out.supersedes.id == p.id
    assert out.supersedes.title == "Parent"
    assert str(out.supersedes.discount_value) == "10.00"


def test_offer_out_supersedes_none_for_plain_offer(db_session):
    o = offer_crud.create_offer(db_session, _offer(target_url=None), CreatedBy.crawler,
                                OfferStatus.pending_review, content_hash="h9")
    out = OfferOut.model_validate(o)
    assert out.supersedes_offer_id is None
    assert out.supersedes is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_offer_out_supersedes.py -v`
Expected: FAIL — `AttributeError`/validation (`supersedes_offer_id` not on OfferOut).

- [ ] **Step 3: Add the nested schema + fields**

In `backend/app/schemas/offer.py`, add before `class OfferOut` (after `OfferLinkOut`):

```python
class SupersedesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    discount_type: DiscountType | None
    discount_value: Decimal | None
```

And inside `OfferOut`, after `source_id: int | None` (line ~104) add:

```python
    supersedes_offer_id: int | None = None
    supersedes: SupersedesOut | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_offer_out_supersedes.py -v`
Expected: PASS (both).

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/offer.py backend/tests/test_offer_out_supersedes.py
git commit -m "feat(backend): expose supersede context on OfferOut"
```

---

### Task 5: Серверний suggestion-guard проти активних Sources

**Files:**
- Modify: `backend/app/core/urlnorm.py` (add `normalize_ref`)
- Modify: `backend/app/crud/suggested_source.py` (`create_suggestion`)
- Test: `backend/tests/test_suggestion_guard.py`

**Interfaces:**
- Consumes: `Source` model, `SuggestedSourceCreate`.
- Produces: `normalize_ref(type: str, url_or_handle: str) -> str` (mirrors crawler `passive.normalize_ref`); `create_suggestion` skips creating a pending row when `(type, normalized url)` matches an active Source (returns None).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_suggestion_guard.py`:

```python
from app.crud import source as source_crud
from app.crud import suggested_source as suggestion_crud
from app.models import SuggestedSource
from app.models.enums import CreatedBy
from app.schemas.source import SourceCreate
from app.schemas.suggested_source import SuggestedSourceCreate


def _active_source(db, type_, ref):
    return source_crud.create_source(
        db, SourceCreate(name="S", type=type_, url_or_handle=ref, is_active=True),
        CreatedBy.crawler)


def test_suggestion_for_active_source_is_skipped(db_session):
    _active_source(db_session, "website", "https://biz.example/")
    out = suggestion_crud.create_suggestion(
        db_session, SuggestedSourceCreate(name="X", type="website",
                                          url_or_handle="http://www.biz.example"))
    assert out is None
    assert db_session.query(SuggestedSource).count() == 0


def test_suggestion_for_active_telegram_is_skipped(db_session):
    _active_source(db_session, "telegram", "https://t.me/mychan")
    out = suggestion_crud.create_suggestion(
        db_session, SuggestedSourceCreate(name="X", type="telegram", url_or_handle="@mychan"))
    assert out is None


def test_new_source_still_suggested(db_session):
    _active_source(db_session, "website", "https://biz.example/")
    out = suggestion_crud.create_suggestion(
        db_session, SuggestedSourceCreate(name="X", type="website",
                                          url_or_handle="https://other.example"))
    assert out is not None
    assert db_session.query(SuggestedSource).count() == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_suggestion_guard.py -v`
Expected: FAIL — currently a pending row is created (guard absent); `out` is a SuggestedSource, count 1.

- [ ] **Step 3: Add `normalize_ref` to urlnorm**

In `backend/app/core/urlnorm.py`, add at the top (after the imports) and a `re` import:

```python
import re
```

and append:

```python
def normalize_ref(type: str, url_or_handle: str) -> str:
    """Type-aware source-ref key based on the crawler's passive.normalize_ref, made a
    touch more robust for the server guard: lowercased; scheme stripped; a leading www.
    dropped (for all refs, not only social hosts); platform prefix (t.me/, instagram.com/,
    facebook.com/) stripped; leading @ and trailing / removed."""
    s = (url_or_handle or "").strip().lower()
    s = re.sub(r"^https?://", "", s)
    s = re.sub(r"^www\.", "", s)
    s = re.sub(r"^(t\.me/|instagram\.com/|facebook\.com/)", "", s)
    return s.lstrip("@").rstrip("/")
```

- [ ] **Step 4: Add the guard to `create_suggestion`**

In `backend/app/crud/suggested_source.py`, update the return type and add the active-source check. Change the signature to `-> SuggestedSource | None` and insert the guard before the existing-suggestion dedup:

```python
from app.core.urlnorm import normalize_ref


def create_suggestion(db: Session, data: SuggestedSourceCreate) -> SuggestedSource | None:
    ref = normalize_ref(data.type, data.url_or_handle)
    active = db.query(Source).filter(Source.type == data.type, Source.is_active.is_(True)).all()
    if any(normalize_ref(s.type.value if hasattr(s.type, "value") else s.type,
                         s.url_or_handle) == ref for s in active):
        return None
    existing = (db.query(SuggestedSource)
                .filter(SuggestedSource.type == data.type,
                        SuggestedSource.url_or_handle == data.url_or_handle)
                .first())
    if existing is not None:
        return existing
    obj = SuggestedSource(
        name=data.name, type=data.type, url_or_handle=data.url_or_handle,
        discovered_from_source_id=data.discovered_from_source_id,
        discovery_note=data.discovery_note, status=SuggestionStatus.pending,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj
```

- [ ] **Step 5: Handle the None return at the router**

The internal route `submit_suggested_source` (backend/app/routers/internal.py:63-65) has `response_model=SuggestedSourceOut`; returning `None` would fail serialization. Update it to 204 on skip. Replace those lines with:

```python
from fastapi import Response, status as http_status


@router.post("/suggested-sources", response_model=SuggestedSourceOut | None)
def submit_suggested_source(data: SuggestedSourceCreate, response: Response,
                            db: Session = Depends(get_db)):
    out = suggestion_crud.create_suggestion(db, data)
    if out is None:
        response.status_code = http_status.HTTP_204_NO_CONTENT
    return out
```

(Add the `Response, status as http_status` import to the existing `from fastapi import ...` line at the top of internal.py.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_suggestion_guard.py tests/test_internal.py -v`
Expected: PASS (guard tests + existing internal-router tests still green).

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/urlnorm.py backend/app/crud/suggested_source.py backend/app/routers/internal.py backend/tests/test_suggestion_guard.py
git commit -m "feat(backend): server-side suggestion guard against active sources"
```

---

### Task 6: Admin — маркер «замінює #X» у черзі модерації

**Files:**
- Modify: `admin/src/utils/format.js` (add `discountLabel`, `supersedeSummary`)
- Modify: `admin/src/views/OffersListView.vue` (render marker in title cell)
- Test: `admin/tests/utils/format.test.js` (create if absent)

**Interfaces:**
- Consumes: `OfferOut.supersedes` (Task 4) — `row.supersedes = { id, title, discount_type, discount_value }`.
- Produces: `discountLabel(type, value) -> string`; `supersedeSummary(offer) -> string` (empty when no supersede).

- [ ] **Step 1: Write the failing test**

Create `admin/tests/utils/format.test.js` (if it exists, append the two `describe` blocks):

```javascript
import { describe, it, expect } from "vitest";
import { discountLabel, supersedeSummary } from "@/utils/format";

describe("discountLabel", () => {
  it("formats percent without trailing zeros", () => {
    expect(discountLabel("percent", "20.00")).toBe("−20%");
  });
  it("formats fixed", () => {
    expect(discountLabel("fixed", "100.00")).toBe("−100 грн");
  });
  it("formats free", () => {
    expect(discountLabel("free", null)).toBe("безкоштовно");
  });
});

describe("supersedeSummary", () => {
  it("summarizes a supersede diff", () => {
    const offer = {
      discount_type: "percent", discount_value: "20.00",
      supersedes: { id: 12, discount_type: "percent", discount_value: "10.00" },
    };
    expect(supersedeSummary(offer)).toBe("замінює #12 (−10% → −20%)");
  });
  it("returns empty for a plain offer", () => {
    expect(supersedeSummary({ supersedes: null })).toBe("");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && npx vitest run tests/utils/format.test.js`
Expected: FAIL — `discountLabel`/`supersedeSummary` not exported.

- [ ] **Step 3: Implement the helpers**

In `admin/src/utils/format.js`, append:

```javascript
export function discountLabel(type, value) {
  if (type === "free") return "безкоштовно";
  const n = value == null ? null : Number(value);
  if (n == null || Number.isNaN(n)) return "";
  if (type === "percent") return `−${n}%`;
  if (type === "fixed") return `−${n} грн`;
  return "";
}

export function supersedeSummary(offer) {
  const p = offer && offer.supersedes;
  if (!p) return "";
  const was = discountLabel(p.discount_type, p.discount_value);
  const now = discountLabel(offer.discount_type, offer.discount_value);
  return `замінює #${p.id} (${was} → ${now})`;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd admin && npx vitest run tests/utils/format.test.js`
Expected: PASS (5 assertions).

- [ ] **Step 5: Wire the marker into the offers list**

In `admin/src/views/OffersListView.vue`:

1. Add `supersedeSummary` to the format import (line 8):

```javascript
import { enumLabel, formatDate, statusTagType, isHttpUrl, supersedeSummary } from "@/utils/format";
```

2. Change the title column (line 22) to a slot:

```javascript
  { label: "Заголовок", slot: "title" },
```

3. Add the title slot template inside `<ResponsiveTable>` (before the `col-type` template, line ~115):

```html
      <template #col-title="{ row }">
        <div>{{ row.title }}</div>
        <el-tag v-if="supersedeSummary(row)" size="small" type="warning" style="margin-top: 4px">
          {{ supersedeSummary(row) }}
        </el-tag>
      </template>
```

- [ ] **Step 6: Run the admin suite + build**

Run: `cd admin && npm test`
Expected: 97 baseline + new format tests → all green.

Run: `cd admin && npm run build`
Expected: build succeeds (no scoped-Less / template errors).

- [ ] **Step 7: Commit**

```bash
git add admin/src/utils/format.js admin/src/views/OffersListView.vue admin/tests/utils/format.test.js
git commit -m "feat(admin): supersede marker in moderation queue"
```

---

## Self-Review

**Spec coverage:**
- Компонент A (детекція зміни / shadow) → Task 2 ✅
- Компонент B (approve/reject supersede) → Task 3 ✅
- Компонент C (схема supersedes_offer_id + OfferOut контекст) → Task 1 (колонка/міграція) + Task 4 (OfferOut) ✅
- Компонент D (серверний suggestion-guard) → Task 5 ✅
- Компонент E (admin marker) → Task 6 ✅
- Крайові: slow-moderator parent-bump → Task 2 (`test_change_bumps_parent_last_seen`); двічі-змінена знижка → Task 2 (`test_repeated_change_updates_single_shadow`); pending-parent in-place → Task 2 (`test_pending_first_submission_updates_in_place`); незмінний → Task 2 (`test_unchanged_published_rewalk_bumps_no_shadow`); cross-source merge не регресить → Task 2 Step 5. ✅
- «Reject shadow → зміна знову» (новий shadow наступного проходу): shadow-lookup фільтрує `status == pending_review`, тож rejected-shadow не матчиться → гілка 2 створить новий shadow. Поведінка відповідає спеці; спец-тест не обовʼязковий (наслідок фільтра). ✅

**Placeholder scan:** нема TODO/TBD; усі кроки містять реальний код і команди. ✅

**Type consistency:** `supersedes_offer_id`, `supersedes`, `normalize_ref(type, url_or_handle)`, `discountLabel(type, value)`, `supersedeSummary(offer)`, `SupersedesOut` — імена узгоджені між тасками. ✅
