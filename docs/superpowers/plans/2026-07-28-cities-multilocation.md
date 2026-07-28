# Cities: gazetteer + multi-location offers — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an offer carry several Ukrainian cities — crawler auto-detects all of them (full ~460-city gazetteer, transliteration-aware, homograph-safe), admin picks from a searchable dropdown, public filters by multiple cities and cards show them all.

**Architecture:** A normalized `offer_locations(offer_id, name)` child table replaces the single free-text `Offer.location` column. A build-time generator (OSM Overpass + pymorphy3) emits two committed artifacts: a crawler form-map (inflected + transliterated surface forms, each flagged permissive/marker-only) and an admin names-only list. The crawler matches text against the form-map with a stdlib token matcher; the public API filters by exact city name (OR) and exposes a faceted `/api/locations` endpoint.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Alembic (MySQL), pytest; Python crawler (httpx, pymorphy3 — already a dependency); Vue 3 + Element Plus (admin) and Vue 3 + Less (public), Vitest.

## Global Constraints

- Language of all UI copy: Ukrainian.
- Backend tests need the MySQL test DB (`settings.test_database_url`, container on :3306); the `db_session` fixture builds schema via `Base.metadata.create_all` (NOT alembic), so every model change is reflected in tests automatically — but the alembic migration must still be written and stay in sync.
- `location` participates in NO dedup (`content_hash` / `target_url_canonical`) or search key — restructuring it is safe.
- The backend `location` → `locations` swap (model column, schema, CRUD) is ONE atomic change (Task 1); splitting it leaves `create_offer` referencing a dropped attribute and the suite red.
- The crawler runtime must add NO new dependency; pymorphy3 (`==2.0.6`) + `pymorphy3-dicts-uk` are already in `crawler/pyproject.toml` and are used ONLY at gazetteer build time, mirroring `crawler/crawler/learn/tokenize.py` (`pymorphy3.MorphAnalyzer(lang="uk")`).
- "Онлайн" is a normal location value (not a flag).
- Canonical city name spelling is the single source of truth shared by both artifacts and the DB strings; never diverge spelling between them.
- Alembic head is `b2d4f6a80c11`; the new migration's `down_revision` is `b2d4f6a80c11`.
- Test commands are run from each service dir: `backend/`, `crawler/` → `python -m pytest ...`; `admin/`, `public/` → `npx vitest run ...`. Frontend template/Less changes are verified with `npm run build` (Vitest does not compile scoped styles).

---

## Phase 1 — Backend

### Task 1: `location` → `locations` (model + schema + CRUD, atomic)

**Files:**
- Create: `backend/app/models/offer_location.py`
- Modify: `backend/app/models/offer.py` (imports; remove `location` column line 28; add relationship + proxy)
- Modify: `backend/app/models/__init__.py` (register `OfferLocation`)
- Modify: `backend/app/schemas/offer.py` (`OfferBase`, `OfferUpdate`, `OfferOut`)
- Modify: `backend/app/crud/offer.py` (`_apply_content`, final create block, `update_offer`, `list_offers`; add `_norm_locations`, `list_distinct_locations`; import `OfferLocation`)
- Modify existing tests: `backend/tests/test_models.py:17` (drop `location="Київ",`), `backend/tests/test_offers_public.py:14` (`location="Київ"` → `locations=["Київ"]`)
- Test: `backend/tests/test_offer_locations.py`

**Interfaces:**
- Produces:
  - `OfferLocation(offer_id: int, name: str)`; `Offer.locations: list[OfferLocation]`; `Offer.location_names: list[str]` (association proxy; assigning a `list[str]` replaces rows, delete-orphan removes dropped).
  - `OfferBase.locations: list[str] = []` (→ `OfferCreate`); `OfferUpdate.locations: list[str] | None = None`; `OfferOut.locations: list[str]` (serialized from ORM rows).
  - `offer_crud.list_offers(..., locations: list[str] | None = None, ...)`; `offer_crud.list_distinct_locations(db, status=OfferStatus.published) -> list[str]`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_offer_locations.py`:

```python
from app.crud import offer as offer_crud
from app.models import Offer, OfferLocation, TargetCategory
from app.models.enums import CreatedBy, OfferStatus, OfferType
from app.schemas.offer import OfferCreate, OfferOut, OfferUpdate


def _mk(db, title, locations, status=OfferStatus.published, created_by=CreatedBy.admin):
    return offer_crud.create_offer(
        db, OfferCreate(type=OfferType.discount, title=title, provider="P", locations=locations),
        created_by=created_by, status=status)


def test_location_names_proxy_roundtrip_and_cascade(db_session):
    o = Offer(type=OfferType.discount, title="T", description="", provider="P",
              status=OfferStatus.pending_review, created_by=CreatedBy.crawler)
    o.location_names = ["Київ", "Львів"]
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    assert sorted(o.location_names) == ["Київ", "Львів"]
    assert db_session.query(OfferLocation).count() == 2
    o.location_names = ["Одеса"]
    db_session.commit()
    assert o.location_names == ["Одеса"]
    assert db_session.query(OfferLocation).count() == 1
    db_session.delete(o)
    db_session.commit()
    assert db_session.query(OfferLocation).count() == 0


def test_create_dedupes_and_strips_locations(db_session):
    o = _mk(db_session, "A", ["Київ", " Київ ", "", "Львів"])
    assert sorted(o.location_names) == ["Київ", "Львів"]


def test_offer_out_serializes_names(db_session):
    o = _mk(db_session, "A", ["Київ", "Львів"])
    assert sorted(OfferOut.model_validate(o).locations) == ["Київ", "Львів"]
    o2 = offer_crud.create_offer(
        db_session, OfferCreate(type=OfferType.event, title="B", provider="P"),
        created_by=CreatedBy.admin, status=OfferStatus.published)
    assert OfferOut.model_validate(o2).locations == []


def test_update_replaces_locations(db_session):
    o = _mk(db_session, "A", ["Київ"])
    offer_crud.update_offer(db_session, o.id, OfferUpdate(locations=["Одеса", "Львів"]))
    db_session.refresh(o)
    assert sorted(o.location_names) == ["Львів", "Одеса"]


def test_update_without_locations_keeps_them(db_session):
    o = _mk(db_session, "A", ["Київ"])
    offer_crud.update_offer(db_session, o.id, OfferUpdate(title="A2"))
    db_session.refresh(o)
    assert o.location_names == ["Київ"]


def test_list_offers_filters_by_any_location(db_session):
    _mk(db_session, "A", ["Київ"]); _mk(db_session, "B", ["Львів"]); _mk(db_session, "C", ["Одеса"])
    items, total = offer_crud.list_offers(db_session, status=OfferStatus.published,
                                          locations=["Київ", "Одеса"])
    assert total == 2
    assert {i.title for i in items} == {"A", "C"}


def test_facet_lists_distinct_published_only(db_session):
    _mk(db_session, "A", ["Київ", "Львів"]); _mk(db_session, "B", ["Київ"])
    _mk(db_session, "P", ["Суми"], status=OfferStatus.pending_review, created_by=CreatedBy.crawler)
    assert offer_crud.list_distinct_locations(db_session) == ["Київ", "Львів"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`): `python -m pytest tests/test_offer_locations.py -v`
Expected: FAIL — `cannot import name 'OfferLocation'`.

- [ ] **Step 3: Create the `OfferLocation` model**

Create `backend/app/models/offer_location.py`:

```python
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

if TYPE_CHECKING:
    from app.models.offer import Offer


class OfferLocation(Base):
    __tablename__ = "offer_locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    offer_id: Mapped[int] = mapped_column(
        ForeignKey("offers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    offer: Mapped["Offer"] = relationship(back_populates="locations")
```

- [ ] **Step 4: Wire up `Offer`**

In `backend/app/models/offer.py`:
1. After the `from sqlalchemy.orm import ...` line add: `from sqlalchemy.ext.associationproxy import association_proxy`
2. In the `if TYPE_CHECKING:` block add: `    from app.models.offer_location import OfferLocation`
3. Delete line 28 (`    location: Mapped[str | None] = mapped_column(String(255), nullable=True)`).
4. After the `TYPE_CHECKING` block (module level, above `class Offer`) add:

```python
def _mk_location(name: str):
    from app.models.offer_location import OfferLocation
    return OfferLocation(name=name)
```

5. Inside `Offer`, next to the `links` relationship, add:

```python
    locations: Mapped[list["OfferLocation"]] = relationship(
        back_populates="offer", cascade="all, delete-orphan", lazy="selectin"
    )
    location_names = association_proxy("locations", "name", creator=_mk_location)
```

- [ ] **Step 5: Register the model**

In `backend/app/models/__init__.py`: add `from app.models.offer_location import OfferLocation` and add `"OfferLocation"` to `__all__`.

- [ ] **Step 6: Edit the schemas**

In `backend/app/schemas/offer.py`:
1. In `OfferBase`, replace `location: str | None = None` with `    locations: list[str] = []`
2. In `OfferUpdate`, replace `location: str | None = None` with `    locations: list[str] | None = None`
3. In `OfferOut`, replace `location: str | None` with `    locations: list[str] = []`
4. Add to `OfferOut`, right after its `model_config` line:

```python
    @field_validator("locations", mode="before")
    @classmethod
    def _location_names(cls, v):
        return [getattr(x, "name", x) for x in (v or [])]
```

(`field_validator` is already imported.)

- [ ] **Step 7: Edit the CRUD**

In `backend/app/crud/offer.py`:
1. Change import line 7 to: `from app.models import Offer, OfferCategory, OfferLocation, TargetCategory`
2. Add above `_load_categories`:

```python
def _norm_locations(names):
    seen, out = set(), []
    for n in names or []:
        n = (n or "").strip()
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out
```

3. In `_apply_content`, replace `obj.location = data.location` with `    obj.location_names = _norm_locations(data.locations)`
4. In the final `obj = Offer(...)` create block, remove `location=data.location,` from the kwargs, and immediately after that statement (before `db.add(obj)`) add: `    obj.location_names = _norm_locations(data.locations)`
5. In `list_offers`, change the signature param `location: str | None = None` to `locations: list[str] | None = None`, and replace:

```python
    if location:
        q = q.filter(Offer.location.ilike(f"%{location}%"))
```

with:

```python
    if locations:
        q = q.filter(Offer.locations.any(OfferLocation.name.in_(locations)))
```

6. In `update_offer`, after `payload = data.model_dump(exclude_unset=True)` add `    locations = payload.pop("locations", None)`; and after the `for field, value in payload.items(): setattr(obj, field, value)` loop add:

```python
    if locations is not None:
        obj.location_names = _norm_locations(locations)
```

7. Append at end of file:

```python
def list_distinct_locations(db: Session, status: OfferStatus = OfferStatus.published):
    rows = (db.query(OfferLocation.name)
            .join(Offer, Offer.id == OfferLocation.offer_id)
            .filter(Offer.status == status)
            .distinct().order_by(OfferLocation.name).all())
    return [r[0] for r in rows]
```

- [ ] **Step 8: Fix the two existing tests**

- `backend/tests/test_models.py:17`: remove `location="Київ",` from the `Offer(...)` constructor.
- `backend/tests/test_offers_public.py:14`: replace `location="Київ"` with `locations=["Київ"]`.

- [ ] **Step 9: Run the backend suite to verify green**

Run (from `backend/`): `python -m pytest tests/test_offer_locations.py tests/test_models.py tests/test_offers_public.py tests/test_offer_merge.py tests/test_offer_shadow.py tests/test_offer_schema.py -v`
Expected: PASS (shadow/merge confirm `_apply_content` still works).

- [ ] **Step 10: Commit**

```bash
git add backend/app/models/offer_location.py backend/app/models/offer.py backend/app/models/__init__.py backend/app/schemas/offer.py backend/app/crud/offer.py backend/tests/test_offer_locations.py backend/tests/test_models.py backend/tests/test_offers_public.py
git commit -m "feat(backend): offer_locations child table replaces free-text location (model+schema+crud)"
```

---

### Task 2: Alembic migration (create table, backfill, drop column)

**Files:**
- Create: `backend/alembic/versions/a1b2c3d4e5f6_offer_locations.py`
- Test: `backend/tests/test_migration_offer_locations.py`

**Interfaces:**
- Produces: migration module exposing `_backfill(conn)` (mirrors the factored helper in `9a1c7b3e2f10`).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_migration_offer_locations.py`:

```python
import importlib.util
import pathlib

from sqlalchemy import text

from app.models import Offer, OfferLocation
from app.models.enums import CreatedBy, OfferStatus, OfferType


def _load_backfill():
    path = (pathlib.Path(__file__).resolve().parents[1]
            / "alembic" / "versions" / "a1b2c3d4e5f6_offer_locations.py")
    spec = importlib.util.spec_from_file_location("mig_offer_locations", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._backfill


def test_backfill_copies_legacy_location_into_rows(db_session):
    conn = db_session.connection()
    conn.execute(text("ALTER TABLE offers ADD COLUMN location VARCHAR(255)"))
    o = Offer(type=OfferType.discount, title="T", description="", provider="P",
              status=OfferStatus.published, created_by=CreatedBy.crawler)
    db_session.add(o)
    db_session.commit()
    conn.execute(text("UPDATE offers SET location = 'Київ' WHERE id = :i"), {"i": o.id})

    _load_backfill()(conn)

    names = [r.name for r in db_session.query(OfferLocation).filter_by(offer_id=o.id)]
    assert names == ["Київ"]
    conn.execute(text("ALTER TABLE offers DROP COLUMN location"))
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `backend/`): `python -m pytest tests/test_migration_offer_locations.py -v`
Expected: FAIL — migration file does not exist.

- [ ] **Step 3: Write the migration**

Create `backend/alembic/versions/a1b2c3d4e5f6_offer_locations.py`:

```python
"""offer_locations child table

Revision ID: a1b2c3d4e5f6
Revises: b2d4f6a80c11
Create Date: 2026-07-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "b2d4f6a80c11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _backfill(conn) -> None:
    conn.execute(sa.text(
        "INSERT INTO offer_locations (offer_id, name) "
        "SELECT id, location FROM offers "
        "WHERE location IS NOT NULL AND location <> ''"
    ))


def upgrade() -> None:
    op.create_table(
        "offer_locations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("offer_id", sa.Integer(),
                  sa.ForeignKey("offers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
    )
    op.create_index("ix_offer_locations_offer_id", "offer_locations", ["offer_id"])
    op.create_index("ix_offer_locations_name", "offer_locations", ["name"])
    _backfill(op.get_bind())
    op.drop_column("offers", "location")


def downgrade() -> None:
    op.add_column("offers", sa.Column("location", sa.String(length=255), nullable=True))
    op.get_bind().execute(sa.text(
        "UPDATE offers o JOIN offer_locations l ON l.offer_id = o.id SET o.location = l.name"
    ))
    op.drop_index("ix_offer_locations_name", table_name="offer_locations")
    op.drop_index("ix_offer_locations_offer_id", table_name="offer_locations")
    op.drop_table("offer_locations")
```

- [ ] **Step 4: Run test to verify it passes**

Run (from `backend/`): `python -m pytest tests/test_migration_offer_locations.py -v`
Expected: PASS.

- [ ] **Step 5: Verify a single linear head**

Run (from `backend/`): `python -m alembic heads`
Expected: single head `a1b2c3d4e5f6 (head)`.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/a1b2c3d4e5f6_offer_locations.py backend/tests/test_migration_offer_locations.py
git commit -m "feat(backend): migration for offer_locations (create + backfill + drop location)"
```

---

### Task 3: Public router — multi-location filter + `/api/locations`

**Files:**
- Modify: `backend/app/routers/public.py` (offers route param; new locations route)
- Test: `backend/tests/test_offers_public.py` (add cases)

**Interfaces:**
- Consumes: `offer_crud.list_offers(..., locations=...)`, `offer_crud.list_distinct_locations`.
- Produces: `GET /api/offers?location=A&location=B` (OR filter); `GET /api/locations -> list[str]`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_offers_public.py`:

```python
def test_filter_by_multiple_locations(client, db_session):
    for title, locs in [("A", ["Київ"]), ("B", ["Львів"]), ("C", ["Одеса"])]:
        offer_crud.create_offer(
            db_session, OfferCreate(type=OfferType.discount, title=title, provider="P", locations=locs),
            created_by=CreatedBy.admin, status=OfferStatus.published)
    body = client.get("/api/offers?location=Київ&location=Одеса").json()
    assert body["total"] == 2
    assert {i["title"] for i in body["items"]} == {"A", "C"}


def test_locations_facet_endpoint_lists_published_only(client, db_session):
    offer_crud.create_offer(
        db_session, OfferCreate(type=OfferType.discount, title="A", provider="P",
                                locations=["Львів", "Київ"]),
        created_by=CreatedBy.admin, status=OfferStatus.published)
    offer_crud.create_offer(
        db_session, OfferCreate(type=OfferType.discount, title="P", provider="P", locations=["Суми"]),
        created_by=CreatedBy.crawler, status=OfferStatus.pending_review)
    assert client.get("/api/locations").json() == ["Київ", "Львів"]
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `backend/`): `python -m pytest tests/test_offers_public.py -k "multiple_locations or facet" -v`
Expected: FAIL — 404 on `/api/locations`; multi-filter ignored.

- [ ] **Step 3: Edit the router**

In `backend/app/routers/public.py`:
1. In the `list_offers` route signature, replace `location: str | None = None` with `location: list[str] | None = Query(None)`, and in the `offer_crud.list_offers(...)` call replace `location=location` with `locations=location`.
2. Add after `list_offer_categories`:

```python
@router.get("/locations", response_model=list[str])
def list_locations(db: Session = Depends(get_db)):
    return offer_crud.list_distinct_locations(db)
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `backend/`): `python -m pytest tests/test_offers_public.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/public.py backend/tests/test_offers_public.py
git commit -m "feat(backend): public multi-location filter + GET /api/locations facet"
```

---

## Phase 2 — Gazetteer generation

### Task 4: Generator + committed artifacts

**Files:**
- Create: `crawler/crawler/discovery/homograph_overrides.py`
- Create: `crawler/scripts/build_gazetteer.py`
- Create (generated, committed): `crawler/crawler/discovery/gazetteer.json`
- Create (generated, committed): `admin/src/constants/gazetteer.js`

**Interfaces:**
- Produces: `gazetteer.json` — `[{"name": str, "forms": [{"f": str, "m": 0|1}, ...]}, ...]`; `admin/src/constants/gazetteer.js` exporting `GAZETTEER: string[]`.

- [ ] **Step 1: Create the overrides module**

Create `crawler/crawler/discovery/homograph_overrides.py`:

```python
"""Manual veto tuning for the gazetteer generator.

- FORCE_MARKER: canonical names whose EVERY surface form must be marker-only
  (matched only after м./с./смт/місто), regardless of the automatic word check.
- FORCE_PERMISSIVE: (canonical, form) pairs kept permissive despite the automatic
  homograph veto — e.g. whitelisting an oblast-centre nominative.
Both start conservative; tune after eyeballing the generated output.
"""

FORCE_MARKER: set[str] = set()
FORCE_PERMISSIVE: set[tuple[str, str]] = set()
```

- [ ] **Step 2: Write the generator**

Create `crawler/scripts/build_gazetteer.py`:

```python
"""Build the shared gazetteer artifacts from open data.

Sources: OSM Overpass (Ukrainian city/town names, name:uk) + pymorphy3 inflection
(build-time only) + KMU transliteration. Emits:
  - crawler/crawler/discovery/gazetteer.json  (form-map for the crawler matcher)
  - admin/src/constants/gazetteer.js          (names-only list for the admin dropdown)

Run:  cd crawler && python scripts/build_gazetteer.py
"""
import json
import pathlib
import sys

import httpx
import pymorphy3

from crawler.discovery.homograph_overrides import FORCE_MARKER, FORCE_PERMISSIVE

ROOT = pathlib.Path(__file__).resolve().parents[2]
CRAWLER_OUT = ROOT / "crawler" / "crawler" / "discovery" / "gazetteer.json"
ADMIN_OUT = ROOT / "admin" / "src" / "constants" / "gazetteer.js"

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
QUERY = """
[out:json][timeout:180];
area["ISO3166-1"="UA"][admin_level=2]->.ua;
( node["place"~"^(city|town)$"]["name:uk"](area.ua); );
out tags;
"""

CASES = ["gent", "datv", "accs", "loct", "ablt"]
# KMU-2010 Ukrainian -> Latin (multi-char first).
TRANSLIT = [
    ("зг", "zgh"),
    ("ж", "zh"), ("х", "kh"), ("ц", "ts"), ("ч", "ch"), ("ш", "sh"), ("щ", "shch"),
    ("ю", "iu"), ("я", "ia"), ("є", "ie"), ("ї", "i"), ("й", "i"),
    ("а", "a"), ("б", "b"), ("в", "v"), ("г", "h"), ("ґ", "g"), ("д", "d"), ("е", "e"),
    ("з", "z"), ("и", "y"), ("і", "i"), ("к", "k"), ("л", "l"), ("м", "m"), ("н", "n"),
    ("о", "o"), ("п", "p"), ("р", "r"), ("с", "s"), ("т", "t"), ("у", "u"), ("ф", "f"),
    ("ь", ""), ("'", ""), ("’", ""),
]
ALT_TRANSLIT = {
    "Київ": ["kyiv", "kiev"], "Львів": ["lviv", "lvov"], "Одеса": ["odesa", "odessa"],
    "Харків": ["kharkiv", "kharkov"], "Дніпро": ["dnipro", "dnepr"],
    "Запоріжжя": ["zaporizhzhia", "zaporozhye"], "Миколаїв": ["mykolaiv", "nikolaev"],
    "Чернігів": ["chernihiv", "chernigov"], "Чернівці": ["chernivtsi"],
}

_morph = pymorphy3.MorphAnalyzer(lang="uk")


def transliterate(name: str) -> str:
    s = name.lower()
    for src, dst in TRANSLIT:
        s = s.replace(src, dst)
    return "".join(ch for ch in s if ch.isascii()).strip()


def inflect_forms(name: str) -> set[str]:
    words = name.split()
    forms = {name.lower()}
    for case in CASES:
        parts, ok = [], True
        for w in words:
            infl = _morph.parse(w)[0].inflect({case})
            if infl is None:
                ok = False
                break
            parts.append(infl.word)
        if ok:
            forms.add(" ".join(parts))
    return forms


def is_common(form: str) -> bool:
    if " " in form:        # multiword names are low-collision — never auto-veto
        return False
    return _morph.word_is_known(form)


def fetch_names() -> list[str]:
    last = None
    for url in OVERPASS_ENDPOINTS:
        try:
            r = httpx.post(url, data={"data": QUERY}, timeout=200)
            r.raise_for_status()
            names = {e["tags"]["name:uk"].strip()
                     for e in r.json()["elements"] if e["tags"].get("name:uk")}
            return sorted(n for n in names if n)
        except Exception as exc:  # noqa: BLE001 — try the next mirror
            last = exc
    raise SystemExit(f"Overpass fetch failed on all endpoints: {last}")


def build_entry(name: str) -> dict:
    forms, seen = [], set()
    for f in sorted(inflect_forms(name), key=len, reverse=True):
        if f in seen:
            continue
        seen.add(f)
        marker = name in FORCE_MARKER or (is_common(f) and (name, f) not in FORCE_PERMISSIVE)
        forms.append({"f": f, "m": 1 if marker else 0})
    for tr in [transliterate(name), *ALT_TRANSLIT.get(name, [])]:
        if tr and tr not in seen:
            seen.add(tr)
            forms.append({"f": tr, "m": 1 if name in FORCE_MARKER else 0})
    return {"name": name, "forms": forms}


def main() -> None:
    names = fetch_names()
    entries = [build_entry(n) for n in names]
    CRAWLER_OUT.write_text(json.dumps(entries, ensure_ascii=False, indent=0), encoding="utf-8")
    ADMIN_OUT.write_text(
        "// AUTO-GENERATED by crawler/scripts/build_gazetteer.py — do not edit by hand.\n"
        "export const GAZETTEER = " + json.dumps(names, ensure_ascii=False) + ";\n",
        encoding="utf-8")
    print(f"wrote {len(entries)} cities -> {CRAWLER_OUT} and {ADMIN_OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Generate the artifacts**

Run (from `crawler/`, with the crawler venv so `crawler` imports):

```bash
python scripts/build_gazetteer.py
```

Expected stderr: `wrote NNN cities -> ...` with NNN ≥ 400. (Re-run on Overpass rate-limit; it tries two mirrors.)

- [ ] **Step 4: Verify the generated data**

Run (from `crawler/`):

```bash
python -c "import json; d=json.load(open('crawler/discovery/gazetteer.json',encoding='utf-8')); names={e['name'] for e in d}; print(len(d)); assert len(d)>=400; assert {'Київ','Львів','Одеса','Харків'} <= names; s=[e for e in d if e['name']=='Суми'][0]; print(s); assert any(f['f']=='суми' and f['m']==1 for f in s['forms'])"
```

Expected: count ≥ 400 and `Суми`'s nominative `{"f": "суми", "m": 1}`. If not flagged, add `"Суми"` to `homograph_overrides.FORCE_MARKER` and re-run Step 3.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/homograph_overrides.py crawler/scripts/build_gazetteer.py crawler/crawler/discovery/gazetteer.json admin/src/constants/gazetteer.js
git commit -m "feat(crawler): gazetteer generator (Overpass+pymorphy+translit+veto) and committed artifacts"
```

---

## Phase 3 — Crawler detection

### Task 5: `geo.py` — full-gazetteer token matcher

**Files:**
- Rewrite: `crawler/crawler/discovery/geo.py`
- Rewrite: `crawler/tests/test_geo.py`

**Interfaces:**
- Consumes: `crawler/crawler/discovery/gazetteer.json` (Task 4).
- Produces: `build_lookup(entries) -> (dict, int)`; `find_cities(text, lookup=None, maxn=None) -> list[str]`; `find_city(text, *ignore) -> str | None`; `is_online(text) -> bool` (unchanged behavior). `find_city` keeps a permissive signature so `website.py`'s `find_city(" ".join(parts))` still works.

- [ ] **Step 1: Write the failing test**

Replace `crawler/tests/test_geo.py` with:

```python
from crawler.discovery.geo import build_lookup, find_cities, find_city, is_online

FIX = [
    {"name": "Львів", "forms": [{"f": "львів", "m": 0}, {"f": "львові", "m": 0}, {"f": "lviv", "m": 0}]},
    {"name": "Суми", "forms": [{"f": "суми", "m": 1}, {"f": "сумах", "m": 0}, {"f": "sumy", "m": 0}]},
    {"name": "Біла Церква", "forms": [{"f": "біла церква", "m": 0}, {"f": "білій церкві", "m": 0}]},
]
LK, MAXN = build_lookup(FIX)


def _f(text):
    return find_cities(text, LK, MAXN)


def test_permissive_match_in_prose():
    assert _f("Акція діє у Львові") == ["Львів"]


def test_transliteration_maps_to_canonical():
    assert _f("Discount in Lviv only") == ["Львів"]


def test_marker_only_form_not_matched_as_bare_word():
    assert _f("Виграйте великі суми грошей") == []


def test_marker_only_form_matched_with_marker():
    assert _f("Наш заклад: м. Суми, центр") == ["Суми"]


def test_permissive_oblique_of_vetoed_city_still_matches():
    assert _f("Знижки для військових у Сумах") == ["Суми"]


def test_multiword_name_with_marker():
    assert _f("м. Біла Церква, вул. Шевченка") == ["Біла Церква"]


def test_multi_return_first_appearance_order():
    assert _f("Спершу у Львові, а також м. Суми") == ["Львів", "Суми"]


def test_find_city_single_and_none():
    assert find_city("у Львові") == "Львів"
    assert _f("немає міста") == []


def test_online_signal_unchanged():
    assert is_online("Працюємо онлайн по всій Україні")
    assert not is_online("Знижка у кафе на вулиці")


def test_default_file_detects_major_city():
    assert "Київ" in find_cities("Велика знижка у Києві для ветеранів")
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `crawler/`): `python -m pytest tests/test_geo.py -v`
Expected: FAIL — `build_lookup` not defined.

- [ ] **Step 3: Rewrite `geo.py`**

Replace `crawler/crawler/discovery/geo.py` with:

```python
"""Gazetteer matcher: map Ukrainian city surface forms (incl. transliteration and
inflected cases, generated in crawler/scripts/build_gazetteer.py) to canonical names.

Precision guard: forms colliding with common Ukrainian words are flagged marker-only
(m=1) at build time and match only after a locality marker (м./с./смт/місто);
permissive forms (m=0) match anywhere. Token matching gives word boundaries for free
and supports multi-word names."""

import json
import re
from pathlib import Path

_MARKERS = {"м", "с", "смт", "місто", "селище"}
_TOKEN = re.compile(r"[a-zа-яїієґ'’\-]+", re.IGNORECASE)
_DATA_PATH = Path(__file__).with_name("gazetteer.json")


def _load_entries(path: Path = _DATA_PATH) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return []


def build_lookup(entries: list[dict]):
    """form(lower) -> (canonical, marker_only, nwords); returns (lookup, max_words)."""
    lookup: dict[str, tuple[str, bool, int]] = {}
    maxn = 1
    for e in entries:
        canon = e["name"]
        for form in e["forms"]:
            f = form["f"].lower()
            if not f:
                continue
            n = len(f.split())
            maxn = max(maxn, n)
            lookup.setdefault(f, (canon, bool(form["m"]), n))
    return lookup, maxn


_LOOKUP, _MAXN = build_lookup(_load_entries())


def _tokenize(text: str) -> list[str]:
    return [m.group(0).lower().strip("’'") for m in _TOKEN.finditer(text)]


def find_cities(text: str | None, lookup=None, maxn: int | None = None) -> list[str]:
    if not text:
        return []
    lookup = _LOOKUP if lookup is None else lookup
    maxn = _MAXN if maxn is None else maxn
    toks = _tokenize(text)
    found: list[str] = []
    seen: set[str] = set()
    i, n = 0, len(toks)
    while i < n:
        matched = False
        for w in range(min(maxn, n - i), 0, -1):
            hit = lookup.get(" ".join(toks[i:i + w]))
            if hit is None:
                continue
            canon, marker_only, _ = hit
            if marker_only:
                prev = toks[i - 1].rstrip(".") if i > 0 else ""
                if prev not in _MARKERS:
                    continue
            if canon not in seen:
                seen.add(canon)
                found.append(canon)
            i += w
            matched = True
            break
        if not matched:
            i += 1
    return found


def find_city(text: str | None, *_ignore) -> str | None:
    cities = find_cities(text)
    return cities[0] if cities else None


_ONLINE = re.compile(r"(?<!\w)(онлайн|інтернет[-\s]?магазин)\w*", re.IGNORECASE)


def is_online(text: str | None) -> bool:
    """Online-only signal — used as a location fallback when no city is found."""
    return bool(text and _ONLINE.search(text))
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `crawler/`): `python -m pytest tests/test_geo.py -v`
Expected: PASS.

- [ ] **Step 5: Confirm dependents still import cleanly**

Run (from `crawler/`): `python -m pytest tests/test_heuristic.py -v`
Expected: PASS (heuristic still uses the old `find_city` API until Task 6).

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/discovery/geo.py crawler/tests/test_geo.py
git commit -m "feat(crawler): full-gazetteer token matcher, find_cities multi-return + marker gating"
```

---

### Task 6: Candidate carries `locations`; heuristic unions all cities

**Files:**
- Modify: `crawler/crawler/models.py` (`OfferCandidate.location` → `locations`)
- Modify: `crawler/crawler/extract/heuristic.py` (import; `_locations` helper; candidate field)
- Modify: `crawler/crawler/payloads.py` (`location` → `locations`)
- Rewrite: `crawler/tests/test_payloads.py`; update `crawler/tests/test_heuristic.py`

**Interfaces:**
- Consumes: `find_cities`, `is_online` (Task 5).
- Produces: `OfferCandidate.locations: list[str]`; `offer_payload(cand)["locations"]: list[str]`.

- [ ] **Step 1: Write the failing tests**

Replace `crawler/tests/test_payloads.py` with:

```python
from crawler.models import OfferCandidate
from crawler.payloads import offer_payload


def test_offer_payload_includes_locations():
    cand = OfferCandidate(source_id=1, title="T", provider="P", body="b",
                          locations=["Львів", "Київ"])
    assert offer_payload(cand)["locations"] == ["Львів", "Київ"]


def test_offer_payload_locations_default_empty():
    cand = OfferCandidate(source_id=1, title="T", provider="P", body="b")
    assert offer_payload(cand)["locations"] == []
```

In `crawler/tests/test_heuristic.py`, update the four location assertions:
- `test_location_from_structured_locality`: `assert cand.location == "Львів"` → `assert cand.locations == ["Львів"]`
- `test_location_from_gazetteer_fallback`: `assert cand.location == "Одеса"` → `assert cand.locations == ["Одеса"]`
- `test_location_none_when_absent`: `assert cand.location is None` → `assert cand.locations == []`
- `test_location_online_fallback`: `assert cand.location == "Онлайн"` → `assert cand.locations == ["Онлайн"]`

- [ ] **Step 2: Run tests to verify they fail**

Run (from `crawler/`): `python -m pytest tests/test_payloads.py tests/test_heuristic.py -v`
Expected: FAIL — `OfferCandidate` has no `locations`.

- [ ] **Step 3: Edit `models.py`**

In `crawler/crawler/models.py`, in `OfferCandidate`, replace `location: str | None = None` with `    locations: list[str] = field(default_factory=list)` (`field` is already imported).

- [ ] **Step 4: Edit `heuristic.py`**

1. Change import line 26 to: `from crawler.discovery.geo import find_cities, is_online`
2. Add a helper after the `_pick_target` function block:

```python
def _locations(locality: str | None, text: str) -> list[str]:
    names: list[str] = []
    if locality:
        resolved = find_cities(locality)
        names.extend(resolved if resolved else [locality.strip()])
    names.extend(find_cities(text))
    out, seen = [], set()
    for n in names:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    if not out and is_online(text):
        out = ["Онлайн"]
    return out
```

3. In the `OfferCandidate(...)` construction (~line 103), replace:

```python
            location=item.locality or find_city(text) or ("Онлайн" if is_online(text) else None),
```

with:

```python
            locations=_locations(item.locality, text),
```

- [ ] **Step 5: Edit `payloads.py`**

In `crawler/crawler/payloads.py`, replace `"location": cand.location,` with `        "locations": cand.locations,`

- [ ] **Step 6: Run tests to verify they pass**

Run (from `crawler/`): `python -m pytest tests/test_payloads.py tests/test_heuristic.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add crawler/crawler/models.py crawler/crawler/extract/heuristic.py crawler/crawler/payloads.py crawler/tests/test_payloads.py crawler/tests/test_heuristic.py
git commit -m "feat(crawler): OfferCandidate.locations union of all detected cities; payload emits locations"
```

---

## Phase 4 — Admin UI

### Task 7: `offerForm.js` util carries `locations`

**Files:**
- Modify: `admin/src/utils/offerForm.js` (`buildOfferPayload`)
- Modify: `admin/tests/utils/offerForm.test.js`

**Interfaces:**
- Produces: `buildOfferPayload(form).locations: string[]` (from `form.locations`, default `[]`); `location` key removed.

- [ ] **Step 1: Write the failing test**

In `admin/tests/utils/offerForm.test.js`:
- In the "nulls discount fields for events and maps category ids" test, change the input `location: ""` to `locations: ["Київ"]`, and replace `expect(payload.location).toBe(null);` with `expect(payload.locations).toEqual(["Київ"]);`.
- Add to the `buildOfferPayload` describe block:

```javascript
  it("defaults locations to an empty array and drops the old location key", () => {
    const p = buildOfferPayload({ type: "event", title: "T", provider: "P" });
    expect(p.locations).toEqual([]);
    expect("location" in p).toBe(false);
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `admin/`): `npx vitest run tests/utils/offerForm.test.js`
Expected: FAIL — `payload.locations` undefined / `location` still present.

- [ ] **Step 3: Edit the util**

In `admin/src/utils/offerForm.js`, in `buildOfferPayload`, replace `location: form.location || null,` with `    locations: form.locations || [],`

- [ ] **Step 4: Run test to verify it passes**

Run (from `admin/`): `npx vitest run tests/utils/offerForm.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add admin/src/utils/offerForm.js admin/tests/utils/offerForm.test.js
git commit -m "feat(admin): buildOfferPayload carries locations array"
```

---

### Task 8: `OfferForm.vue` — searchable multi-select of cities

**Files:**
- Modify: `admin/src/components/OfferForm.vue` (`fromInitial`; import gazetteer; template field)
- Modify: `admin/tests/components/OfferForm.test.js`

**Interfaces:**
- Consumes: `@/constants/gazetteer` (`GAZETTEER: string[]`, Task 4); `form.locations`.

- [ ] **Step 1: Write the failing test**

In `admin/tests/components/OfferForm.test.js`, add:

```javascript
  it("seeds locations from the initial offer and includes them in the payload", () => {
    const wrapper = mount(OfferForm, {
      props: { initial: { type: "discount", title: "T", provider: "P",
                          locations: ["Київ", "Львів"], target_categories: [], offer_categories: [] } },
      global: { plugins: [ElementPlus] },
    });
    expect(wrapper.vm.form.locations).toEqual(["Київ", "Львів"]);
    Object.assign(wrapper.vm.form, { discount_type: "percent", discount_value: 10 });
    wrapper.vm.submit();
    expect(wrapper.emitted().submit[0][0].locations).toEqual(["Київ", "Львів"]);
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `admin/`): `npx vitest run tests/components/OfferForm.test.js`
Expected: FAIL — `form.locations` undefined.

- [ ] **Step 3: Edit the component**

In `admin/src/components/OfferForm.vue`:
1. Add to `<script setup>`: `import { GAZETTEER } from "@/constants/gazetteer";`
2. In `fromInitial(o)`, replace `location: o?.location || "",` with `    locations: o?.locations ? [...o.locations] : [],`
3. In the template, replace the whole "Локація" form item:

```html
    <el-form-item label="Локація">
      <el-input v-model="form.location" placeholder="Місто або «онлайн»" />
    </el-form-item>
```

with:

```html
    <el-form-item label="Локація (міста)">
      <el-select v-model="form.locations" multiple filterable clearable
                 style="width: 100%" placeholder="Оберіть міста або «Онлайн»">
        <el-option label="Онлайн" value="Онлайн" />
        <el-option v-for="c in GAZETTEER" :key="c" :label="c" :value="c" />
      </el-select>
    </el-form-item>
```

- [ ] **Step 4: Run test to verify it passes**

Run (from `admin/`): `npx vitest run tests/components/OfferForm.test.js`
Expected: PASS.

- [ ] **Step 5: Build to confirm the template compiles**

Run (from `admin/`): `npm run build`
Expected: build succeeds.

- [ ] **Step 6: Commit**

```bash
git add admin/src/components/OfferForm.vue admin/tests/components/OfferForm.test.js
git commit -m "feat(admin): OfferForm city multi-select from gazetteer + Онлайн"
```

---

## Phase 5 — Public UI

### Task 9: API client array params, `locations()` fetch, dictionaries

**Files:**
- Modify: `public/src/api/client.js` (paramsSerializer)
- Modify: `public/src/api/offers.js` (add `locations`)
- Modify: `public/src/composables/useDictionaries.js` (load locations)
- Modify: `public/tests/api/api.test.js`; `public/tests/composables/useDictionaries.test.js`

**Interfaces:**
- Produces: `offersApi.locations() -> Promise<string[]>`; axios serializes array params as repeated `key=` (no `[]`); `useDictionaries().locations: Ref<string[]>`.

- [ ] **Step 1: Write the failing tests**

In `public/tests/api/api.test.js`, add a case for `offersApi.locations()` GETting `/locations` (mirror the file's existing spy/mock style):

```javascript
  it("locations() fetches the facet list", async () => {
    const spy = vi.spyOn(client, "get").mockResolvedValue({ data: ["Київ", "Львів"] });
    await expect(offersApi.locations()).resolves.toEqual(["Київ", "Львів"]);
    expect(spy).toHaveBeenCalledWith("/locations");
  });
```

Ensure `client` and `offersApi` are imported as the file already imports them (e.g. `import client from "@/api/client";` and `import * as offersApi from "@/api/offers";`); add whichever import is missing.

In `public/tests/composables/useDictionaries.test.js`, add a case asserting that after `load()` the `locations` ref is populated — mock `@/api/offers`'s `locations` to resolve `["Київ"]` in the same place the file mocks `@/api/categories`, then assert `useDictionaries().locations.value` equals `["Київ"]`.

- [ ] **Step 2: Run tests to verify they fail**

Run (from `public/`): `npx vitest run tests/api/api.test.js tests/composables/useDictionaries.test.js`
Expected: FAIL — `offersApi.locations` undefined / `locations` not on dictionaries.

- [ ] **Step 3: Edit the client**

In `public/src/api/client.js`, add `paramsSerializer` to the axios config:

```javascript
const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || "/api",
  paramsSerializer: { indexes: null },
});
```

- [ ] **Step 4: Add the API call**

In `public/src/api/offers.js`, add:

```javascript
export const locations = () => client.get("/locations").then((r) => r.data);
```

- [ ] **Step 5: Load locations in dictionaries**

In `public/src/composables/useDictionaries.js`:
1. Add import: `import { locations as fetchLocations } from "@/api/offers";`
2. Add `const locations = ref([]);` next to the other refs.
3. Change `Promise.all([listTarget(), listOffer()])` to `Promise.all([listTarget(), listOffer(), fetchLocations()])`, and the `.then(([t, o]) => {` to `.then(([t, o, l]) => {` adding `        locations.value = l;` in the body.
4. Add `locations` to the returned object.

- [ ] **Step 6: Run tests to verify they pass**

Run (from `public/`): `npx vitest run tests/api/api.test.js tests/composables/useDictionaries.test.js`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add public/src/api/client.js public/src/api/offers.js public/src/composables/useDictionaries.js public/tests/api/api.test.js public/tests/composables/useDictionaries.test.js
git commit -m "feat(public): repeated-param serialization, locations() facet fetch, dictionaries load cities"
```

---

### Task 10: `OfferFilters.vue` — multi-select city filter

**Files:**
- Modify: `public/src/components/OfferFilters.vue`
- Modify: `public/src/views/OffersView.vue` (pass `:locations`)
- Modify: `public/tests/components/OfferFilters.test.js`

**Interfaces:**
- Consumes: `locations` prop (`string[]`).
- Produces: `apply` emits `{ ..., location: string[] }` when cities chosen; `activeCount` counts a non-empty selection as one.

- [ ] **Step 1: Write the failing test**

In `public/tests/components/OfferFilters.test.js`:
1. In `mountFilters`, add `locations: ["Київ", "Львів", "Одеса"]` to `props`.
2. In the "apply emits cleaned filters" test, replace `Object.assign(w.vm.draft, { type: "event", location: "", q: "музей" });` with `Object.assign(w.vm.draft, { type: "event", locations: [], q: "музей" });` (expected result unchanged: `{ type: "event", q: "музей" }`).
3. Add:

```javascript
  it("emits selected cities as a location array", () => {
    const w = mountFilters({});
    w.vm.open = true;
    Object.assign(w.vm.draft, { locations: ["Київ", "Одеса"] });
    w.vm.apply();
    expect(w.emitted().apply[0][0]).toEqual({ location: ["Київ", "Одеса"] });
  });

  it("counts a non-empty location selection as one active filter", () => {
    const w = mountFilters({ location: ["Київ", "Львів"] });
    expect(w.vm.activeCount).toBe(1);
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `public/`): `npx vitest run tests/components/OfferFilters.test.js`
Expected: FAIL — draft has no `locations`; `location` array not emitted.

- [ ] **Step 3: Edit the component**

In `public/src/components/OfferFilters.vue`:
1. Add to `props`: `  locations: { type: Array, default: () => [] },`
2. Replace the `draft` line with: `const draft = reactive({ type: "", target_category: "", offer_category: "", locations: [], q: "" });`
3. After the `draft` declaration add: `const locSearch = ref("");`
4. Replace `seed()`:

```javascript
function seed() {
  draft.type = props.modelValue.type || "";
  draft.target_category = props.modelValue.target_category || "";
  draft.offer_category = props.modelValue.offer_category || "";
  const loc = props.modelValue.location;
  draft.locations = Array.isArray(loc) ? [...loc] : (loc ? [loc] : []);
  draft.q = props.modelValue.q || "";
  locSearch.value = "";
}
```

5. Replace `activeCount`:

```javascript
const activeCount = computed(() => {
  let n = 0;
  for (const k of ["type", "target_category", "offer_category", "q"]) if (props.modelValue[k]) n++;
  const loc = props.modelValue.location;
  if (Array.isArray(loc) ? loc.length : loc) n++;
  return n;
});
```

6. Add after `activeCount`:

```javascript
const filteredLocations = computed(() => {
  const term = locSearch.value.trim().toLowerCase();
  return term ? props.locations.filter((c) => c.toLowerCase().includes(term)) : props.locations;
});
```

7. Replace `clean()`:

```javascript
function clean() {
  const out = {};
  for (const k of ["type", "target_category", "offer_category", "q"]) {
    if (draft[k]) out[k] = draft[k];
  }
  if (draft.locations.length) out.location = [...draft.locations];
  return out;
}
```

8. Append `filteredLocations` and `locSearch` to the `defineExpose({ ... })` object.
9. In the template, replace the "Локація" label block:

```html
      <label>Локація
        <input v-model="draft.location" type="text" placeholder="Місто або «онлайн»" />
      </label>
```

with:

```html
      <fieldset class="filters__loc">
        <legend>Локація</legend>
        <input v-if="locations.length > 8" v-model="locSearch" type="text"
               class="filters__locsearch" placeholder="Пошук міста" />
        <div class="filters__loclist">
          <label v-for="c in filteredLocations" :key="c" class="filters__loccheck">
            <input type="checkbox" :value="c" v-model="draft.locations" />{{ c }}
          </label>
        </div>
      </fieldset>
```

10. In `<style scoped lang="less">`, add:

```less
.filters__loc { border: 1px solid @divider; border-radius: @radius-sm; padding: 8px; margin: 0; }
.filters__loc legend { font-size: 14px; color: @meta-muted; padding: 0 4px; }
.filters__locsearch { width: 100%; padding: 6px; margin-bottom: 6px; border: 1px solid @divider; border-radius: @radius-sm; }
.filters__loclist { max-height: 160px; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; }
.filters__loccheck { flex-direction: row; align-items: center; gap: 6px; font-size: 14px; color: @text; text-transform: none; }
```

- [ ] **Step 4: Pass the prop from OffersView**

In `public/src/views/OffersView.vue`:
1. Change `const { targetCategories, offerCategories, load: loadDicts } = useDictionaries();` to `const { targetCategories, offerCategories, locations, load: loadDicts } = useDictionaries();`
2. Add `:locations="locations"` to the `<OfferFilters ... />` tag.

- [ ] **Step 5: Run tests to verify they pass**

Run (from `public/`): `npx vitest run tests/components/OfferFilters.test.js tests/views/OffersView.test.js`
Expected: PASS.

- [ ] **Step 6: Build to confirm scoped Less compiles**

Run (from `public/`): `npm run build`
Expected: build succeeds.

- [ ] **Step 7: Commit**

```bash
git add public/src/components/OfferFilters.vue public/src/views/OffersView.vue public/tests/components/OfferFilters.test.js
git commit -m "feat(public): multi-select city filter with inline search"
```

---

### Task 11: Cards & detail show all cities

**Files:**
- Modify: `public/src/components/OfferCard.vue` (`meta`)
- Modify: `public/src/views/OfferDetailView.vue` (locations row, line 78)
- Modify: `public/tests/components/OfferCard.test.js`; `public/tests/views/OfferDetailView.test.js`

**Interfaces:**
- Consumes: `offer.locations: string[]` from `OfferOut`.

- [ ] **Step 1: Write the failing test**

In `public/tests/components/OfferCard.test.js`, add:

```javascript
  it("shows all offer cities joined in the footer meta", () => {
    const w = mountCard({
      id: 20, type: "discount", title: "T", provider: "P", description: "d", image_url: null,
      target_categories: [], offer_categories: [], locations: ["Київ", "Львів"],
    });
    expect(w.get(".card__meta").text()).toBe("Київ · Львів");
  });
```

In `public/tests/views/OfferDetailView.test.js`, add a case (matching the file's existing mount/mocking style) that stubs `offersApi.get` to resolve an offer with `locations: ["Київ", "Львів"]` and asserts the rendered text contains `Київ, Львів`.

- [ ] **Step 2: Run tests to verify they fail**

Run (from `public/`): `npx vitest run tests/components/OfferCard.test.js tests/views/OfferDetailView.test.js`
Expected: FAIL — meta still reads `offer.location`.

- [ ] **Step 3: Edit the card**

In `public/src/components/OfferCard.vue`, replace `const meta = computed(() => props.offer.location || "");` with:

```javascript
const meta = computed(() => (props.offer.locations || []).join(" · "));
```

- [ ] **Step 4: Edit the detail view**

In `public/src/views/OfferDetailView.vue`, replace line 78:

```html
      <div v-if="offer.location" class="detail__row"><span class="detail__label">Локація:</span> {{ offer.location }}</div>
```

with:

```html
      <div v-if="offer.locations?.length" class="detail__row"><span class="detail__label">Локація:</span> {{ offer.locations.join(", ") }}</div>
```

- [ ] **Step 5: Run tests to verify they pass**

Run (from `public/`): `npx vitest run tests/components/OfferCard.test.js tests/views/OfferDetailView.test.js`
Expected: PASS.

- [ ] **Step 6: Full public suite + build**

Run (from `public/`): `npx vitest run` then `npm run build`
Expected: all pass; build succeeds.

- [ ] **Step 7: Commit**

```bash
git add public/src/components/OfferCard.vue public/src/views/OfferDetailView.vue public/tests/components/OfferCard.test.js public/tests/views/OfferDetailView.test.js
git commit -m "feat(public): offer card + detail show all cities"
```

---

## Final verification (before finishing the branch)

- [ ] Backend: `cd backend && python -m pytest -q` — all green.
- [ ] Crawler: `cd crawler && python -m pytest -q` — all green.
- [ ] Admin: `cd admin && npx vitest run && npm run build` — all green, build ok.
- [ ] Public: `cd public && npx vitest run && npm run build` — all green, build ok.
- [ ] Alembic: `cd backend && python -m alembic heads` — single head `a1b2c3d4e5f6`.

## Rollout (after review + merge to main)

Standard workflow: merge `--no-ff` to main, push, canonical rebuild of backend + crawler + admin + public images, live Docker smoke check — migration applied (`offer_locations` exists, `offers.location` gone), crawler emits multi-city payloads, admin city multi-select works, `GET /api/locations` returns the facet, public multi-city filter narrows results, cards/detail show all cities — then update memory / RESUME.
```
