# Page-level offer identity + multi-discount cards — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make one source promo-page collapse into a single offer that carries a list of labelled discounts, and route cross-pass page changes to shadow re-moderation via an `article_url` page-identity.

**Architecture:** The crawler aggregates a page's per-block candidates into one candidate with a `discounts` list (union of categories/locations, best discount as primary). The backend stores discounts in a new `offer_discounts` child table, adds `offers.article_url_canonical`, and switches same-source change detection (create_offer branches 2/3) from `target_url_canonical` to `article_url_canonical`. Public and admin render/edit the discount list.

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy / Alembic (backend), pytest; Python crawler, pytest; Vue 3 (public + admin), Vitest.

## Global Constraints

- Language of all user-facing copy: Ukrainian.
- Backend dedup source of truth stays in `create_offer` (crawler `_normalize_url` is classification only).
- Top-level `offers.discount_type`/`discount_value` are KEPT as the primary/headline discount; `offer_discounts` is additive. Do not break `OfferBadge`, public sort/filter, `SupersedesOut`, existing admin, or API.
- `offer_discounts` is ALWAYS populated for a discount offer: if a payload gives no `discounts` list, synthesize one 1-item entry from the top-level discount. Event/no-discount offers have an empty list.
- Alembic new migration `down_revision = 'a1b2c3d4e5f6'` (current head, offer_locations).
- Reuse existing `canonicalize_target_url` (`app/core/urlnorm.py`) for `article_url_canonical` — it is URL-agnostic.
- Run backend tests from `backend/` with the project venv; crawler tests from `crawler/`; public/admin with `npm run test` and `npm run build`.

---

### Task 1: `OfferDiscount` model

**Files:**
- Create: `backend/app/models/offer_discount.py`
- Modify: `backend/app/models/offer.py` (relationship + TYPE_CHECKING import)
- Modify: `backend/app/models/__init__.py` (register)
- Test: `backend/tests/test_offer_discount_model.py`

**Interfaces:**
- Produces: `OfferDiscount(offer_id: int, label: str|None, discount_type: DiscountType|None, discount_value: Decimal|None, sort_order: int)`; `Offer.discounts: list[OfferDiscount]` ordered by `sort_order`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_offer_discount_model.py
from decimal import Decimal

from app.models import Offer, OfferDiscount
from app.models.enums import CreatedBy, DiscountType, OfferStatus, OfferType


def test_offer_discounts_relationship_ordered(db_session):
    o = Offer(type=OfferType.discount, title="T", description="", provider="P",
              status=OfferStatus.pending_review, created_by=CreatedBy.crawler)
    o.discounts = [
        OfferDiscount(label="ЗСУ", discount_type=DiscountType.percent,
                      discount_value=Decimal("15"), sort_order=1),
        OfferDiscount(label="МВС", discount_type=DiscountType.percent,
                      discount_value=Decimal("10"), sort_order=0),
    ]
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    assert [d.label for d in o.discounts] == ["МВС", "ЗСУ"]
    assert o.discounts[0].discount_value == Decimal("10")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_offer_discount_model.py -v`
Expected: FAIL — `ImportError: cannot import name 'OfferDiscount'`.

- [ ] **Step 3: Create the model**

```python
# backend/app/models/offer_discount.py
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.enums import DiscountType

if TYPE_CHECKING:
    from app.models.offer import Offer


class OfferDiscount(Base):
    __tablename__ = "offer_discounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    offer_id: Mapped[int] = mapped_column(
        ForeignKey("offers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    discount_type: Mapped[DiscountType | None] = mapped_column(Enum(DiscountType), nullable=True)
    discount_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    offer: Mapped["Offer"] = relationship(back_populates="discounts")
```

- [ ] **Step 4: Wire the relationship on Offer**

In `backend/app/models/offer.py`, add to the `TYPE_CHECKING` block (near the `OfferLink`/`OfferLocation` imports):

```python
    from app.models.offer_discount import OfferDiscount
```

And add this relationship inside the `Offer` class, right after the `locations` relationship (before `location_names`):

```python
    discounts: Mapped[list["OfferDiscount"]] = relationship(
        back_populates="offer", cascade="all, delete-orphan",
        order_by="OfferDiscount.sort_order", lazy="selectin",
    )
```

- [ ] **Step 5: Register in models package**

In `backend/app/models/__init__.py`, add the import after the `offer_link` import:

```python
from app.models.offer_discount import OfferDiscount
```

and add `"OfferDiscount"` to `__all__` (next to `"OfferLink"`).

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_offer_discount_model.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/offer_discount.py backend/app/models/offer.py backend/app/models/__init__.py backend/tests/test_offer_discount_model.py
git commit -m "feat(backend): OfferDiscount child model + Offer.discounts relationship"
```

---

### Task 2: Discount schemas + `article_url_canonical` on Offer model

**Files:**
- Modify: `backend/app/models/offer.py` (column + index)
- Modify: `backend/app/schemas/offer.py` (DiscountIn/DiscountOut + wire into OfferBase/OfferUpdate/OfferOut)
- Test: `backend/tests/test_offer_discount_schema.py`

**Interfaces:**
- Produces: `DiscountIn{label: str|None, discount_type: DiscountType|None, discount_value: Decimal|None}`, `DiscountOut` (same fields, from_attributes). `OfferBase.discounts: list[DiscountIn] = []`, `OfferUpdate.discounts: list[DiscountIn] | None = None`, `OfferOut.discounts: list[DiscountOut] = []`. `Offer.article_url_canonical: str|None`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_offer_discount_schema.py
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.offer import DiscountIn, OfferCreate
from app.models.enums import DiscountType, OfferType


def test_offer_create_accepts_discounts_list():
    oc = OfferCreate(type=OfferType.discount, title="T", provider="P",
                     discount_type=DiscountType.percent, discount_value=Decimal("15"),
                     discounts=[{"label": "ЗСУ", "discount_type": "percent", "discount_value": 15},
                                {"label": None, "discount_type": "free", "discount_value": None}])
    assert oc.discounts[0].label == "ЗСУ"
    assert oc.discounts[1].discount_type == DiscountType.free


def test_discount_in_rejects_value_without_percent_fixed():
    with pytest.raises(ValidationError):
        DiscountIn(label="x", discount_type=DiscountType.free, discount_value=Decimal("5"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_offer_discount_schema.py -v`
Expected: FAIL — `ImportError: cannot import name 'DiscountIn'`.

- [ ] **Step 3: Add the schemas**

In `backend/app/schemas/offer.py`, add near the top (after the imports, before `OfferBase`):

```python
class DiscountIn(BaseModel):
    label: str | None = None
    discount_type: DiscountType | None = None
    discount_value: Decimal | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.discount_type in (DiscountType.percent, DiscountType.fixed):
            if self.discount_value is None:
                raise ValueError("discount_value required for percent/fixed discounts")
        elif self.discount_value is not None:
            raise ValueError("discount_value must be empty unless discount_type is percent/fixed")
        return self


class DiscountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    label: str | None = None
    discount_type: DiscountType | None = None
    discount_value: Decimal | None = None
```

In `OfferBase`, add after `offer_category_ids`:

```python
    discounts: list[DiscountIn] = []
```

In `OfferUpdate`, add after `offer_category_ids`:

```python
    discounts: list[DiscountIn] | None = None
```

In `OfferOut`, add after `offer_categories`:

```python
    discounts: list[DiscountOut] = []
```

- [ ] **Step 4: Add the model column + index**

In `backend/app/models/offer.py`, add the column after `target_url_canonical`:

```python
    article_url_canonical: Mapped[str | None] = mapped_column(String(1024), nullable=True)
```

and add to `__table_args__` (after the `ix_offers_target_url_canonical` Index):

```python
        Index("ix_offers_article_url_canonical", "article_url_canonical", mysql_length=255),
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_offer_discount_schema.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/offer.py backend/app/schemas/offer.py backend/tests/test_offer_discount_schema.py
git commit -m "feat(backend): discount schemas + Offer.article_url_canonical column"
```

---

### Task 3: Alembic migration (offer_discounts table + article_url_canonical + backfill)

**Files:**
- Create: `backend/alembic/versions/e5f6a7b8c9d0_offer_discounts_and_article_canonical.py`

**Interfaces:**
- Consumes: `OfferDiscount` model, `Offer.article_url_canonical` (Tasks 1–2).
- Produces: table `offer_discounts`, column `offers.article_url_canonical` + index; both backfilled.

**Note on testing:** the backend test DB (`conftest.py`) is built with
`Base.metadata.create_all`, NOT via alembic — so a pytest "does the table
exist" check would only assert the model metadata (already covered by Tasks
1–2 tests) and would say nothing about the migration. The correct
verification for a migration is an **alembic round-trip against the real dev
DB** (Step 2). No new pytest file for this task.

- [ ] **Step 1: Write the migration**

```python
# backend/alembic/versions/e5f6a7b8c9d0_offer_discounts_and_article_canonical.py
"""offer_discounts table + offers.article_url_canonical

Revision ID: e5f6a7b8c9d0
Revises: a1b2c3d4e5f6
Create Date: 2026-07-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DISCOUNT_ENUM = sa.Enum("percent", "fixed", "free", name="discounttype")


def _backfill(conn) -> None:
    from app.core.urlnorm import canonicalize_target_url
    rows = conn.execute(
        sa.text("SELECT id, article_url, discount_type, discount_value "
                "FROM offers")
    ).fetchall()
    for rid, aurl, dtype, dval in rows:
        if aurl:
            canon = canonicalize_target_url(aurl)
            if canon:
                conn.execute(
                    sa.text("UPDATE offers SET article_url_canonical = :c WHERE id = :i"),
                    {"c": canon, "i": rid},
                )
        if dtype is not None:
            conn.execute(
                sa.text("INSERT INTO offer_discounts "
                        "(offer_id, label, discount_type, discount_value, sort_order) "
                        "VALUES (:o, NULL, :t, :v, 0)"),
                {"o": rid, "t": dtype, "v": dval},
            )


def upgrade() -> None:
    op.add_column("offers", sa.Column("article_url_canonical", sa.String(length=1024), nullable=True))
    op.create_index("ix_offers_article_url_canonical", "offers",
                    ["article_url_canonical"], mysql_length=255)
    op.create_table(
        "offer_discounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("offer_id", sa.Integer(), sa.ForeignKey("offers.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("discount_type", _DISCOUNT_ENUM, nullable=True),
        sa.Column("discount_value", sa.Numeric(10, 2), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_offer_discounts_offer_id", "offer_discounts", ["offer_id"])
    _backfill(op.get_bind())


def downgrade() -> None:
    op.drop_index("ix_offer_discounts_offer_id", table_name="offer_discounts")
    op.drop_table("offer_discounts")
    op.drop_index("ix_offers_article_url_canonical", table_name="offers")
    op.drop_column("offers", "article_url_canonical")
```

- [ ] **Step 2: Verify migration applies cleanly on the dev DB (round-trip)**

Run (from `backend/`, with the venv): `./.venv/Scripts/python.exe -m alembic upgrade head && ./.venv/Scripts/python.exe -m alembic downgrade -1 && ./.venv/Scripts/python.exe -m alembic upgrade head && ./.venv/Scripts/python.exe -m alembic current`
Expected: no errors; `alembic current` reports `e5f6a7b8c9d0 (head)`. The down-then-up proves both `upgrade()` and `downgrade()` are correct. This round-trip IS the task's test.

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/e5f6a7b8c9d0_offer_discounts_and_article_canonical.py
git commit -m "feat(backend): migration for offer_discounts + article_url_canonical + backfill"
```

---

### Task 4: `create_offer` — discount sync + article_url page identity

**Files:**
- Modify: `backend/app/crud/offer.py`
- Test: `backend/tests/test_offer_discounts_crud.py`

**Interfaces:**
- Consumes: `OfferDiscount`, `DiscountIn`, `Offer.article_url_canonical`, `canonicalize_target_url`.
- Produces: `create_offer` populates `offer_discounts` and `article_url_canonical`; branches 2/3 match on `(source_id, article_url_canonical)`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_offer_discounts_crud.py
from decimal import Decimal

from app.crud import offer as offer_crud
from app.models import Offer
from app.models.enums import CreatedBy, DiscountType, OfferStatus, OfferType
from app.schemas.offer import OfferCreate


def _mk(**kw):
    base = dict(type=OfferType.discount, title="T", provider="P",
                discount_type=DiscountType.percent, discount_value=Decimal("15"))
    base.update(kw)
    return OfferCreate(**base)


def test_create_offer_stores_discounts_list(db_session):
    data = _mk(article_url="https://ex.com/promo",
               discounts=[{"label": "МВС", "discount_type": "percent", "discount_value": 10},
                          {"label": "ЗСУ", "discount_type": "percent", "discount_value": 15}])
    o = offer_crud.create_offer(db_session, data, CreatedBy.crawler,
                                OfferStatus.pending_review, source_id=1, content_hash="h1")
    assert [(d.label, d.discount_value) for d in o.discounts] == \
        [("МВС", Decimal("10")), ("ЗСУ", Decimal("15"))]
    assert o.article_url_canonical == "ex.com/promo"


def test_create_offer_synthesizes_single_discount_when_no_list(db_session):
    o = offer_crud.create_offer(db_session, _mk(), CreatedBy.crawler,
                                OfferStatus.pending_review, source_id=1, content_hash="h2")
    assert len(o.discounts) == 1
    assert o.discounts[0].discount_type == DiscountType.percent
    assert o.discounts[0].discount_value == Decimal("15")


def test_page_change_shadows_via_article_url_even_with_null_target(db_session):
    # published parent, target_url NULL -> identity is article_url
    parent = offer_crud.create_offer(
        db_session, _mk(article_url="https://ex.com/promo"), CreatedBy.crawler,
        OfferStatus.pending_review, source_id=7, content_hash="p1")
    parent.status = OfferStatus.published
    db_session.commit()
    # a changed page (new content_hash, same article_url) -> shadow, not a fresh pending
    changed = offer_crud.create_offer(
        db_session, _mk(article_url="https://ex.com/promo", discount_value=Decimal("20")),
        CreatedBy.crawler, OfferStatus.pending_review, source_id=7, content_hash="p2")
    assert changed.supersedes_offer_id == parent.id
    assert changed.status == OfferStatus.pending_review
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && python -m pytest tests/test_offer_discounts_crud.py -v`
Expected: FAIL — discounts empty / `article_url_canonical` None / no shadow (fresh pending created).

- [ ] **Step 3: Implement the discount sync helper**

In `backend/app/crud/offer.py`, add the import at top:

```python
from app.models import Offer, OfferCategory, OfferDiscount, OfferLocation, TargetCategory
```

Add this helper after `_norm_locations`:

```python
def _discount_rows(data):
    """Discount rows for an offer: the payload list, else a single synthesized entry
    from the top-level discount, else empty (event / no-discount)."""
    from app.models import OfferDiscount
    if getattr(data, "discounts", None):
        return [OfferDiscount(label=d.label, discount_type=d.discount_type,
                              discount_value=d.discount_value, sort_order=i)
                for i, d in enumerate(data.discounts)]
    if data.discount_type is not None:
        return [OfferDiscount(label=None, discount_type=data.discount_type,
                              discount_value=data.discount_value, sort_order=0)]
    return []
```

- [ ] **Step 4: Wire discounts + article canonical into `_apply_content` and `create_offer`**

In `_apply_content`, add a parameter and set the fields. Change the signature and body:

```python
def _apply_content(obj, data, canon, canon_article, content_hash, targets, offers, mk_link):
    obj.type = data.type
    obj.title = data.title
    obj.description = data.description
    obj.provider = data.provider
    obj.location_names = _norm_locations(data.locations)
    obj.valid_from = data.valid_from
    obj.valid_until = data.valid_until
    obj.discount_type = data.discount_type
    obj.discount_value = data.discount_value
    obj.site_url = data.site_url
    obj.article_url = data.article_url
    obj.image_url = data.image_url
    obj.target_url = data.target_url
    obj.target_url_canonical = canon
    obj.article_url_canonical = canon_article
    obj.content_hash = content_hash
    obj.target_categories = targets
    obj.offer_categories = offers
    obj.discounts = _discount_rows(data)
    obj.links = [mk_link()]
    obj.last_seen_at = datetime.utcnow()
```

In `create_offer`, compute the article canonical near `canon`:

```python
    canon = canonicalize_target_url(data.target_url) if data.target_url else None
    canon_article = canonicalize_target_url(data.article_url) if data.article_url else None
    crawler = created_by == CreatedBy.crawler
```

Change the branch-2/3 guard and match key from `canon` (target) to `canon_article`. Replace the line:

```python
    if crawler and canon and source_id is not None:
```

with:

```python
    if crawler and canon_article and source_id is not None:
```

In branch 2, change the parent query filter from `Offer.target_url_canonical == canon` to:

```python
                  .filter(Offer.source_id == source_id,
                          Offer.article_url_canonical == canon_article,
                          Offer.status == OfferStatus.published)
```

and update both `_apply_content(...)` calls in branches 2 and 3 to pass `canon_article`:

```python
            _apply_content(shadow, data, canon, canon_article, content_hash, targets, offers, _mk_link)
```
```python
            _apply_content(pending, data, canon, canon_article, content_hash, targets, offers, _mk_link)
```

In branch 3, change the pending query filter from `Offer.target_url_canonical == canon` to `Offer.article_url_canonical == canon_article`.

In the final fallthrough `Offer(...)` constructor, add `article_url_canonical=canon_article,` next to `target_url_canonical=canon,` and add discounts after it is built (the ORM needs the object first). Replace the fallthrough block:

```python
    targets, offers = _load_categories(db, data.target_category_ids, data.offer_category_ids)
    obj = Offer(
        type=data.type, title=data.title, description=data.description, provider=data.provider,
        valid_from=data.valid_from, valid_until=data.valid_until,
        discount_type=data.discount_type, discount_value=data.discount_value,
        site_url=data.site_url, article_url=data.article_url, image_url=data.image_url,
        target_url=data.target_url, target_url_canonical=canon,
        article_url_canonical=canon_article, source_id=source_id,
        status=status, created_by=created_by, content_hash=content_hash,
        last_seen_at=datetime.utcnow(),
        target_categories=targets, offer_categories=offers,
        discounts=_discount_rows(data),
        links=[_mk_link()],
    )
    obj.location_names = _norm_locations(data.locations)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj
```

- [ ] **Step 5: Run to verify they pass**

Run: `cd backend && python -m pytest tests/test_offer_discounts_crud.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full existing offer suite (no regressions)**

Run: `cd backend && python -m pytest tests/test_offer_merge.py tests/test_offer_shadow.py tests/test_offer_supersede_publish.py tests/test_offer_freshness.py -v`
Expected: PASS. If a shadow test relied on `target_url_canonical` for same-source identity, update it to set `article_url` on the offers (the page identity is now `article_url`), keeping the assertion intent.

- [ ] **Step 7: Commit**

```bash
git add backend/app/crud/offer.py backend/tests/test_offer_discounts_crud.py
git commit -m "feat(backend): create_offer stores discounts + article_url page identity"
```

---

### Task 5: `update_offer` — discount sync + article canonical recompute

**Files:**
- Modify: `backend/app/crud/offer.py`
- Test: `backend/tests/test_offer_update_discounts.py`

**Interfaces:**
- Consumes: `_discount_rows`, `OfferUpdate.discounts`.
- Produces: `update_offer` replaces `offer_discounts` when `discounts` in payload; recomputes `article_url_canonical` when `article_url` in payload.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_offer_update_discounts.py
from decimal import Decimal

from app.crud import offer as offer_crud
from app.models.enums import CreatedBy, DiscountType, OfferStatus, OfferType
from app.schemas.offer import OfferCreate, OfferUpdate


def _seed(db):
    data = OfferCreate(type=OfferType.discount, title="T", provider="P",
                       discount_type=DiscountType.percent, discount_value=Decimal("10"),
                       article_url="https://ex.com/a")
    return offer_crud.create_offer(db, data, CreatedBy.admin, OfferStatus.published)


def test_update_replaces_discounts_and_recomputes_article_canonical(db_session):
    o = _seed(db_session)
    upd = OfferUpdate(article_url="https://www.ex.com/b",
                      discounts=[{"label": "Курсанти", "discount_type": "percent", "discount_value": 15},
                                 {"label": "ЗСУ", "discount_type": "free", "discount_value": None}])
    out = offer_crud.update_offer(db_session, o.id, upd)
    assert [d.label for d in out.discounts] == ["Курсанти", "ЗСУ"]
    assert out.article_url_canonical == "ex.com/b"  # www stripped
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && python -m pytest tests/test_offer_update_discounts.py -v`
Expected: FAIL — discounts unchanged / `article_url_canonical` not recomputed.

- [ ] **Step 3: Implement**

In `update_offer` (`backend/app/crud/offer.py`), pop `discounts` alongside the other list fields:

```python
    target_ids = payload.pop("target_category_ids", None)
    offer_ids = payload.pop("offer_category_ids", None)
    locations = payload.pop("locations", None)
    discounts = payload.pop("discounts", None)
```

After the existing `if "target_url" in payload:` block, add:

```python
    if "article_url" in payload:
        obj.article_url_canonical = (canonicalize_target_url(obj.article_url)
                                     if obj.article_url else None)
    if discounts is not None:
        obj.discounts = _discount_rows(data)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && python -m pytest tests/test_offer_update_discounts.py -v`
Expected: PASS.

- [ ] **Step 5: Run the update suite (no regressions)**

Run: `cd backend && python -m pytest tests/test_offer_update_links.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/crud/offer.py backend/tests/test_offer_update_discounts.py
git commit -m "feat(backend): update_offer syncs discounts + recomputes article_url_canonical"
```

---

### Task 6: Crawler — per-block discount label on `OfferCandidate`

**Files:**
- Modify: `crawler/crawler/models.py` (add `discounts` field)
- Modify: `crawler/crawler/extract/heuristic.py` (build single-entry discounts with label)
- Test: `crawler/tests/test_heuristic_discount_label.py`

**Interfaces:**
- Produces: `OfferCandidate.discounts: list[dict]` where each dict is `{"label": str|None, "discount_type": str|None, "discount_value": str|None}`. `extract()` sets a single-entry list (the block's discount) with `label = _title_from(text)` fallback to the matched target-category name.

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_heuristic_discount_label.py
from crawler.extract.base import CategoryIndex
from crawler.extract.heuristic import HeuristicExtractor
from crawler.models import RawItem


def _cats():
    return CategoryIndex(target=[{"id": 1, "slug": "vijskovi", "name": "Військові"}], offer=[])


def test_extract_sets_single_discount_with_snippet_label():
    ex = HeuristicExtractor()
    item = RawItem(source_id=1, platform="website", key="k",
                   text="Військовим знижка 15% на все меню.", url="https://ex.com/p")
    cand = ex.extract(item, "Кафе", _cats())
    assert cand is not None
    assert len(cand.discounts) == 1
    d = cand.discounts[0]
    assert d["discount_type"] == "percent"
    assert d["discount_value"] == "15"
    assert d["label"] and "15%" in d["label"]
```

Note: adjust the `target` slug/name in `_cats()` to a slug the lexicon actually maps "військовим" to; check `crawler/crawler/discovery/lexicon.py` TARGET_LEXICON if the test's category is not matched.

- [ ] **Step 2: Run to verify it fails**

Run: `cd crawler && python -m pytest tests/test_heuristic_discount_label.py -v`
Expected: FAIL — `OfferCandidate` has no `discounts` field.

- [ ] **Step 3: Add the field**

In `crawler/crawler/models.py`, add to `OfferCandidate` after `offer_category_matches`:

```python
    discounts: list[dict] = field(default_factory=list)
```

- [ ] **Step 4: Build the discount entry in `extract`**

In `crawler/crawler/extract/heuristic.py`, add a label helper above the class:

```python
def _discount_label(text: str, target_ids, categories) -> str | None:
    snippet = _title_from(text)
    if snippet and len(snippet) <= 80:
        return snippet
    names = [c["name"] for c in categories.target if c["id"] in set(target_ids)]
    return names[0] if names else None
```

In `extract`, just before the `return OfferCandidate(...)`, build the list:

```python
        discounts = ([{"label": _discount_label(text, target_ids, categories),
                       "discount_type": discount_type,
                       "discount_value": discount_value}]
                     if discount_type is not None else [])
```

and add to the `OfferCandidate(...)` constructor (after `offer_category_matches=offer_matches,`):

```python
            discounts=discounts,
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd crawler && python -m pytest tests/test_heuristic_discount_label.py -v`
Expected: PASS.

- [ ] **Step 6: Run the heuristic suite (no regressions)**

Run: `cd crawler && python -m pytest tests/test_heuristic.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add crawler/crawler/models.py crawler/crawler/extract/heuristic.py crawler/tests/test_heuristic_discount_label.py
git commit -m "feat(crawler): per-block discount entry with label on OfferCandidate"
```

---

### Task 7: Crawler — `aggregate_page` (collapse a page's blocks into one candidate)

**Files:**
- Create: `crawler/crawler/extract/aggregate.py`
- Modify: `crawler/crawler/dedup.py` (page-level hash helper)
- Test: `crawler/tests/test_aggregate_page.py`

**Interfaces:**
- Consumes: `OfferCandidate` with `discounts`, `target_category_ids`, `offer_category_matches`, `locations`.
- Produces: `aggregate_page(cands: list[OfferCandidate]) -> OfferCandidate | None` — one candidate: union of discounts (dedup identical `(type, value, label)`), union of `target_category_ids` / `offer_category_matches` / `locations`; page-level `title`/`site_url`/`article_url`/`image_url`/`provider`; `target_url` = first non-null; primary `discount_type`/`discount_value` = best of the list; `content_hash = page_content_hash(title, provider, discounts)`. `page_content_hash(title, provider, discounts: list[dict]) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_aggregate_page.py
from crawler.extract.aggregate import aggregate_page
from crawler.models import OfferCandidate


def _c(**kw):
    base = dict(source_id=1, title="Кафе на розі", provider="Кафе", body="b",
                article_url="https://ex.com/p", site_url="https://ex.com")
    base.update(kw)
    return OfferCandidate(**base)


def test_aggregate_unions_discounts_categories_and_picks_best_primary():
    a = _c(discount_type="percent", discount_value="10", target_category_ids=[1],
           offer_category_matches=[("Їжа", "food")],
           discounts=[{"label": "МВС", "discount_type": "percent", "discount_value": "10"}])
    b = _c(discount_type="percent", discount_value="15", target_category_ids=[2],
           offer_category_matches=[("Кава", "coffee")],
           discounts=[{"label": "ЗСУ", "discount_type": "percent", "discount_value": "15"}])
    out = aggregate_page([a, b])
    assert out is not None
    assert len(out.discounts) == 2
    assert sorted(out.target_category_ids) == [1, 2]
    assert {s for _, s in out.offer_category_matches} == {"food", "coffee"}
    # primary = best (highest percent)
    assert out.discount_type == "percent" and out.discount_value == "15"


def test_aggregate_dedups_identical_discounts_and_hash_is_order_independent():
    a = _c(discounts=[{"label": "МВС", "discount_type": "percent", "discount_value": "10"}],
           discount_type="percent", discount_value="10")
    b = _c(discounts=[{"label": "МВС", "discount_type": "percent", "discount_value": "10"}],
           discount_type="percent", discount_value="10")
    out = aggregate_page([a, b])
    assert len(out.discounts) == 1
    # reversed input -> same content_hash (order-independent)
    assert aggregate_page([b, a]).content_hash == out.content_hash


def test_aggregate_empty_returns_none():
    assert aggregate_page([]) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd crawler && python -m pytest tests/test_aggregate_page.py -v`
Expected: FAIL — module `crawler.extract.aggregate` does not exist.

- [ ] **Step 3: Add the page-hash helper**

In `crawler/crawler/dedup.py`, add:

```python
def page_content_hash(title: str, provider: str, discounts: list[dict]) -> str:
    keys = sorted(
        f"{d.get('discount_type')}|{d.get('discount_value')}|{_norm(d.get('label') or '')}"
        for d in discounts
    )
    joined = " | ".join([_norm(title), _norm(provider), *keys])
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Write `aggregate_page`**

```python
# crawler/crawler/extract/aggregate.py
from dataclasses import replace

from crawler.dedup import page_content_hash
from crawler.models import OfferCandidate

_RANK = {"free": 3, "percent": 2, "fixed": 1}


def _best(discounts: list[dict]) -> tuple[str | None, str | None]:
    """Primary/headline discount: free > highest percent > highest fixed."""
    best = None
    for d in discounts:
        dt = d.get("discount_type")
        if dt is None:
            continue
        val = float(d.get("discount_value") or 0)
        key = (_RANK.get(dt, 0), val)
        if best is None or key > best[0]:
            best = (key, dt, d.get("discount_value"))
    return (best[1], best[2]) if best else (None, None)


def aggregate_page(cands: list[OfferCandidate]) -> OfferCandidate | None:
    if not cands:
        return None
    head = cands[0]
    discounts: list[dict] = []
    seen = set()
    tcats: list[int] = []
    ocats: list[tuple[str, str]] = []
    locations: list[str] = []
    target_url = None
    for c in cands:
        for d in (c.discounts or []):
            k = (d.get("discount_type"), str(d.get("discount_value")), d.get("label"))
            if k not in seen:
                seen.add(k)
                discounts.append(d)
        for t in c.target_category_ids:
            if t not in tcats:
                tcats.append(t)
        for m in c.offer_category_matches:
            if m not in ocats:
                ocats.append(m)
        for loc in c.locations:
            if loc not in locations:
                locations.append(loc)
        if target_url is None and c.target_url:
            target_url = c.target_url
    dtype, dval = _best(discounts)
    return replace(
        head,
        discounts=discounts,
        target_category_ids=tcats,
        offer_category_matches=ocats,
        locations=locations,
        target_url=target_url,
        discount_type=dtype,
        discount_value=dval,
        offer_category_ids=[],
        content_hash=page_content_hash(head.title, head.provider, discounts),
    )
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd crawler && python -m pytest tests/test_aggregate_page.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/extract/aggregate.py crawler/crawler/dedup.py crawler/tests/test_aggregate_page.py
git commit -m "feat(crawler): aggregate_page collapses a page's blocks into one candidate"
```

---

### Task 8: Crawler — wire page aggregation into runner + harvest + payload

**Files:**
- Modify: `crawler/crawler/payloads.py` (send `discounts`)
- Modify: `crawler/crawler/runner.py` (`_crawl_source` / `_crawl_website_deep` group per page)
- Modify: `crawler/crawler/discovery/harvest.py` (`_process_page` aggregates)
- Test: `crawler/tests/test_page_collapse_wiring.py`

**Interfaces:**
- Consumes: `aggregate_page`, `resolve_offer_categories`, `offer_payload`.
- Produces: one `submit_offer` per page in both the passive-source path and the active-harvest path; `offer_payload` carries `discounts`.

- [ ] **Step 1: Add discounts to the payload**

In `crawler/crawler/payloads.py`, add to the dict returned by `offer_payload`:

```python
        "discounts": cand.discounts,
```

- [ ] **Step 2: Write the failing test**

```python
# crawler/tests/test_page_collapse_wiring.py
from crawler.discovery.harvest import ActiveHarvester
from crawler.extract.base import CategoryIndex
from crawler.models import RawItem, SourceCandidate


class _FakeApi:
    def __init__(self):
        self.offers = []
    def submit_offer(self, payload):
        self.offers.append(payload)
    def submit_suggestion(self, payload):
        pass


class _FakeFetcher:
    # two promo blocks from ONE page (same url), different discounts
    def fetch(self, src, last_key):
        url = src["url_or_handle"]
        return ([RawItem(source_id=1, platform="website", key="a",
                         text="Військовим знижка 10% завжди.", url=url, links=[]),
                 RawItem(source_id=1, platform="website", key="b",
                         text="Курсантам знижка 15% на курси.", url=url, links=[])], last_key)


def test_active_harvest_submits_one_offer_per_page():
    from crawler.extract.heuristic import HeuristicExtractor
    api = _FakeApi()
    h = ActiveHarvester(api=api, fetchers={"website": _FakeFetcher()},
                        extractor=HeuristicExtractor(), rate_limiter=None,
                        hardening_enabled=False)
    cats = CategoryIndex(target=[{"id": 1, "slug": "vijskovi", "name": "Військові"}], offer=[])
    cand = SourceCandidate(name="X", type="website", url_or_handle="https://ex.com/promo")
    summary = {"sources": 0, "offers": 0, "suggestions": 0, "expired": 0, "errors": 0}
    h.harvest([cand], cats, set(), summary)
    assert len(api.offers) == 1
    assert len(api.offers[0]["discounts"]) == 2
```

Note: `hardening_enabled=False` and no walker keep the test focused on collapse. Verify the lexicon maps "військовим"/"курсантам" to a target slug so both blocks pass `extract`; otherwise pick verbs that do (see `lexicon.py`). If `attribute()` needs a provider, confirm `_FakeFetcher` items carry enough context or relax the attribution in the test setup.

- [ ] **Step 3: Run to verify it fails**

Run: `cd crawler && python -m pytest tests/test_page_collapse_wiring.py -v`
Expected: FAIL — two offers submitted (one per block) instead of one.

- [ ] **Step 4: Aggregate in `harvest._process_page`**

In `crawler/crawler/discovery/harvest.py`, add the import at top:

```python
from crawler.extract.aggregate import aggregate_page
```

Replace the per-item submit loop in `_process_page` (the `for item in passing:` block) so it collects attributed candidates and submits once:

```python
        collected = []
        for item in passing:
            attr = attribute(item, ctx, hardening_enabled=self._hardening_enabled,
                             aggregator_min_outbound=self._aggregator_min_outbound)
            if attr is None:
                continue
            offer = self._extractor.extract(item, attr.provider, cats)
            collected.append((offer, attr))
        if not collected:
            return
        page_offer = aggregate_page([o for o, _ in collected])
        page_offer.offer_category_ids = resolve_offer_categories(
            self._api, cats, page_offer.offer_category_matches)
        self._api.submit_offer(offer_payload(page_offer))
        summary["offers"] += 1
        for _, attr in collected:
            if attr.suggest_url_or_handle:
                s_ref = normalize_ref(attr.suggest_type, attr.suggest_url_or_handle)
                if s_ref not in known:
                    self._api.submit_suggestion({
                        "name": attr.suggest_name,
                        "type": attr.suggest_type,
                        "url_or_handle": attr.suggest_url_or_handle,
                        "discovered_from_source_id": None,
                        "discovery_note": f"active-search offer from {cand.url_or_handle}",
                    })
                    known.add(s_ref)
                    summary["suggestions"] += 1
```

- [ ] **Step 5: Group per page in the runner (passive sources)**

In `crawler/crawler/runner.py`, add the import:

```python
from crawler.extract.aggregate import aggregate_page
```

Add a shared page helper method on `Runner`:

```python
    def _process_page(self, items, source, cats, known, summary):
        collected = []
        for item in items:
            cand = self._extractor.extract(item, source["name"], cats)
            if self._corpus is not None:
                self._corpus.record(item, cand is not None)
            if cand is not None:
                collected.append(cand)
            for sc in extract_source_candidates(item, known):
                self._api.submit_suggestion(suggestion_payload(sc))
                known.add(normalize_ref(sc.type, sc.url_or_handle))
                summary["suggestions"] += 1
        if collected:
            page = aggregate_page(collected)
            page.offer_category_ids = resolve_offer_categories(
                self._api, cats, page.offer_category_matches)
            self._api.submit_offer(offer_payload(page))
            summary["offers"] += 1
```

Change `_crawl_source` (non-walker branch) to call it with the page's items:

```python
        state = self._api.get_crawl_state(source["id"])
        items, new_key = self._fetch_for(source, state.get("last_seen_key"))
        self._process_page(items, source, cats, known, summary)
        self._api.set_crawl_state(source["id"], new_key)
```

Change `_crawl_website_deep`'s inner loop so each fetched page's items collapse together:

```python
        for url in plan.urls:
            try:
                self._domain_rl.wait(plan.domain, plan.crawl_delay)
                page_src = {"id": source["id"], "type": "website",
                            "name": source["name"], "url_or_handle": url}
                items, last_key = fetcher.fetch(page_src, last_key)
                self._process_page(items, source, cats, known, summary)
            except Exception as exc:  # noqa: BLE001 — one page must not sink the domain walk
                summary["errors"] += 1
                log.warning("passive deep-walk page failed for %s: %s", url, exc)
```

Delete the now-unused `_process_item` method.

- [ ] **Step 6: Run to verify it passes**

Run: `cd crawler && python -m pytest tests/test_page_collapse_wiring.py -v`
Expected: PASS.

- [ ] **Step 7: Run the runner + harvest suites (no regressions)**

Run: `cd crawler && python -m pytest tests/test_runner.py tests/test_active_harvest.py tests/test_runner_discovery.py tests/test_wiring.py -v`
Expected: PASS. Update any test that asserted "N offers from N blocks on one page" to expect one collapsed offer with N discounts (that is the intended behavior change).

- [ ] **Step 8: Commit**

```bash
git add crawler/crawler/payloads.py crawler/crawler/runner.py crawler/crawler/discovery/harvest.py crawler/tests/test_page_collapse_wiring.py
git commit -m "feat(crawler): collapse a page into one offer with a discounts list"
```

---

### Task 9: Public — render the discount list on card + detail

**Files:**
- Modify: `public/src/utils/format.js` (add `discountText`)
- Modify: `public/src/components/OfferCard.vue`
- Modify: `public/src/views/OfferDetailView.vue`
- Test: `public/tests/components/OfferCard.test.js` (extend), `public/tests/utils/format.test.js` (if present; else add)

**Interfaces:**
- Consumes: `offer.discounts: [{label, discount_type, discount_value}]`.
- Produces: `discountText(d) -> string` (e.g. "−15%", "−200 ₴", "Безкоштовно"); card lists `offer.discounts` under the badge.

- [ ] **Step 1: Write the failing test**

```javascript
// public/tests/components/OfferCard.test.js — add a case
import { mount } from "@vue/test-utils";
import OfferCard from "@/components/OfferCard.vue";

it("renders each discount with its label", () => {
  const offer = {
    id: 1, provider: "Кафе", type: "discount",
    discount_type: "percent", discount_value: 15,
    discounts: [
      { label: "МВС", discount_type: "percent", discount_value: 10 },
      { label: "ЗСУ", discount_type: "percent", discount_value: 15 },
    ],
    target_categories: [], offer_categories: [], locations: [],
  };
  const wrapper = mount(OfferCard, { props: { offer },
    global: { stubs: { "router-link": true } } });
  const text = wrapper.text();
  expect(text).toContain("МВС");
  expect(text).toContain("ЗСУ");
  expect(text).toContain("−10%");
  expect(text).toContain("−15%");
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd public && npm run test -- OfferCard`
Expected: FAIL — labels/values not rendered.

- [ ] **Step 3: Add `discountText`**

In `public/src/utils/format.js`, add:

```javascript
export function discountText(d) {
  if (d.discount_type === "free") return "Безкоштовно";
  if (d.discount_type === "percent" && d.discount_value != null) return `−${Number(d.discount_value)}%`;
  if (d.discount_type === "fixed" && d.discount_value != null) return `−${Number(d.discount_value)} ₴`;
  return "Знижка";
}
```

- [ ] **Step 4: Render the list in OfferCard**

In `public/src/components/OfferCard.vue`, import the helper in `<script setup>`:

```javascript
import { discountText } from "@/utils/format";
```

Add a computed for the multi-discount list (show it only when there is more than one, so single-discount offers keep the clean badge look):

```javascript
const discounts = computed(() => props.offer.discounts || []);
const showList = computed(() => discounts.value.length > 1);
```

In the template, add after the `.card__discount` block:

```html
    <ul v-if="showList" class="card__discounts">
      <li v-for="(d, i) in discounts" :key="i" class="card__discount-row">
        <span class="card__discount-val">{{ discountText(d) }}</span>
        <span v-if="d.label" class="card__discount-label">{{ d.label }}</span>
      </li>
    </ul>
```

Add styles in the `<style scoped>` block:

```less
.card__discounts { list-style: none; margin: 8px 0 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.card__discount-row { display: flex; align-items: baseline; gap: 8px; font-size: 12px; }
.card__discount-val { font-weight: 800; color: @text; white-space: nowrap; }
.card__discount-label { color: @desc-muted; overflow-wrap: anywhere; }
```

- [ ] **Step 5: Render the list in OfferDetailView**

Open `public/src/views/OfferDetailView.vue`, import `discountText`, and near where the single discount/badge is shown add the same `v-if="discounts.length > 1"` list (mirror the card markup with a `detail__discounts` class). Keep the existing single-discount display as the fallback.

- [ ] **Step 6: Run tests + build**

Run: `cd public && npm run test && npm run build`
Expected: tests PASS; build succeeds (scoped Less only surfaces at build time — always build).

- [ ] **Step 7: Commit**

```bash
git add public/src/utils/format.js public/src/components/OfferCard.vue public/src/views/OfferDetailView.vue public/tests/components/OfferCard.test.js
git commit -m "feat(public): render multi-discount list on card + detail"
```

---

### Task 10: Admin — discounts editor in OfferForm + queue preview

**Files:**
- Modify: `admin/src/utils/offerForm.js` (`fromInitial`/`buildOfferPayload`/`validateOffer`)
- Modify: `admin/src/components/OfferForm.vue` (rows editor)
- Modify: `admin/src/views/OffersListView.vue` (discount count in preview)
- Test: `admin/tests/utils/offerForm.test.js` (extend), `admin/tests/views/OffersListView.test.js` (extend)

**Interfaces:**
- Consumes: `initial.discounts`; enum options `DISCOUNT_TYPES`.
- Produces: `form.discounts: [{label, discount_type, discount_value}]`; payload includes `discounts`; queue row shows discount count.

- [ ] **Step 1: Write the failing test**

```javascript
// admin/tests/utils/offerForm.test.js — add cases
import { buildOfferPayload, validateOffer } from "@/utils/offerForm";

it("passes discounts through the payload", () => {
  const form = { type: "discount", title: "T", provider: "P",
    discount_type: "percent", discount_value: 15,
    discounts: [{ label: "МВС", discount_type: "percent", discount_value: 10 }],
    locations: [], target_category_ids: [], offer_category_ids: [] };
  const payload = buildOfferPayload(form);
  expect(payload.discounts).toEqual([{ label: "МВС", discount_type: "percent", discount_value: 10 }]);
});

it("rejects a discount row with a value but free type", () => {
  const form = { type: "discount", title: "T", provider: "P",
    discount_type: "percent", discount_value: 15,
    discounts: [{ label: "x", discount_type: "free", discount_value: 5 }],
    locations: [], target_category_ids: [], offer_category_ids: [] };
  expect(validateOffer(form).length).toBeGreaterThan(0);
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && npm run test -- offerForm`
Expected: FAIL — `payload.discounts` undefined / no validation error.

- [ ] **Step 3: Implement in offerForm.js**

In `admin/src/utils/offerForm.js`:
- In `fromInitial`, add: `discounts: o?.discounts ? o.discounts.map((d) => ({ ...d })) : [],`
- In `buildOfferPayload`, include `discounts: (form.discounts || []).map((d) => ({ label: d.label || null, discount_type: d.discount_type || null, discount_value: d.discount_value ?? null })),`
- In `validateOffer`, after the existing checks, add:

```javascript
  for (const d of form.discounts || []) {
    const needsValue = d.discount_type === "percent" || d.discount_type === "fixed";
    if (needsValue && (d.discount_value === null || d.discount_value === undefined)) {
      errors.push("Величина знижки обов'язкова для %/фіксованої знижки");
    }
    if (!needsValue && d.discount_value !== null && d.discount_value !== undefined) {
      errors.push("Величина знижки має бути порожньою, крім %/фіксованої");
    }
  }
```

(If `offerForm.js` builds `fromInitial` inside the component instead of the util, mirror these edits where that logic actually lives — check the file first.)

- [ ] **Step 4: Add the rows editor to OfferForm.vue**

In `admin/src/components/OfferForm.vue`, ensure `form.discounts` is part of the reactive form (it comes from `fromInitial`). Add helpers in `<script setup>`:

```javascript
function addDiscount() { form.discounts.push({ label: "", discount_type: "percent", discount_value: null }); }
function removeDiscount(i) { form.discounts.splice(i, 1); }
```

Add a template block after the primary discount fields (inside `<template v-if="isDiscount">`):

```html
      <el-form-item label="Знижки на сторінці (кому — скільки)">
        <div class="discount-rows">
          <div v-for="(d, i) in form.discounts" :key="i" class="discount-row">
            <el-input v-model="d.label" placeholder="Кому/за що" style="flex: 1" />
            <el-select v-model="d.discount_type" style="width: 130px">
              <el-option v-for="opt in DISCOUNT_TYPES" :key="opt.value" :label="opt.label" :value="opt.value" />
            </el-select>
            <el-input-number v-if="d.discount_type === 'percent' || d.discount_type === 'fixed'"
                             v-model="d.discount_value" :min="0" />
            <el-button text type="danger" @click="removeDiscount(i)">✕</el-button>
          </div>
          <el-button size="small" @click="addDiscount">+ Додати знижку</el-button>
        </div>
      </el-form-item>
```

Add styles:

```less
.discount-rows { display: flex; flex-direction: column; gap: 8px; width: 100%; }
.discount-row { display: flex; align-items: center; gap: 8px; }
```

- [ ] **Step 5: Show discount count in the queue preview**

In `admin/src/views/OffersListView.vue`, in the offer row/preview, add a small indicator when `row.discounts?.length > 1`, e.g. a column/tag rendering `` `${row.discounts.length} знижок` ``. Add a matching assertion in `OffersListView.test.js` for a row with multiple discounts.

- [ ] **Step 6: Run tests + build**

Run: `cd admin && npm run test && npm run build`
Expected: tests PASS; build succeeds.

- [ ] **Step 7: Commit**

```bash
git add admin/src/utils/offerForm.js admin/src/components/OfferForm.vue admin/src/views/OffersListView.vue admin/tests/utils/offerForm.test.js admin/tests/views/OffersListView.test.js
git commit -m "feat(admin): discounts-list editor in OfferForm + queue preview count"
```

---

### Task 11: Full-suite green + live Docker verification

**Files:** none (verification only).

- [ ] **Step 1: Backend full suite**

Run: `cd backend && python -m pytest -q`
Expected: all PASS.

- [ ] **Step 2: Crawler full suite**

Run: `cd crawler && python -m pytest -q`
Expected: all PASS.

- [ ] **Step 3: Public + admin**

Run: `cd public && npm run test && npm run build` then `cd admin && npm run test && npm run build`
Expected: all PASS; both builds succeed.

- [ ] **Step 4: Live Docker end-to-end**

Bring up the stack (backend on canonical image with the new migration; crawler via hot-copy stopgap per project convention). Verify:
- Migration `e5f6a7b8c9d0` applied (`alembic current`).
- A source with a multi-block promo page produces ONE pending offer with multiple `offer_discounts` rows (check via admin queue / DB).
- Editing that offer's discount list in admin persists and shows on the public card.
- Re-running the crawler on an unchanged page bumps `last_seen_at` (no duplicate); changing a discount produces a shadow (`supersedes_offer_id` set) rather than a fresh pending.

- [ ] **Step 5: Request code review**

Use `superpowers:requesting-code-review` (opus) on the branch diff before merge.

---

## Self-Review

**Spec coverage:**
- §1 data model → Tasks 1, 2, 3. §2 create_offer identity → Task 4. §3 crawler collapse → Tasks 6, 7, 8. §4 page content_hash → Task 7 (`page_content_hash`). §5 public → Task 9; admin → Task 10. §6 non-goals → no task (correctly excluded). Testing/delivery → Task 11.
- All spec sections map to a task. No gaps.

**Type consistency:**
- `_discount_rows(data)` defined in Task 4, reused in Task 5. `_apply_content` signature gains `canon_article` in Task 4 and every call site is updated in the same task.
- `OfferCandidate.discounts: list[dict]` (Task 6) consumed by `aggregate_page` (Task 7) and `offer_payload` (Task 8).
- `discountText(d)` (Task 9, public) and `discounts` shape `{label, discount_type, discount_value}` consistent across backend `DiscountOut`, crawler dict, public, admin.
- `page_content_hash(title, provider, discounts)` defined in Task 7, used only there.

**Placeholder scan:** No TBD/TODO. Every code step shows concrete code. The three "check the file first / adjust the slug" notes are grounded verification hints (lexicon slug matching, OfferDetail mirror, offerForm location), not deferred work.
