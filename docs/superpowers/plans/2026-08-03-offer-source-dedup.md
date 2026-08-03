# Дедуп оферів + lifecycle джерел Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Прибрати near-дублі оферів у черзі (batart 5→1): нормалізувати пагінацію в canonical, тримати одне активне website-джерело на хост, і полагодити delete-source (500).

**Architecture:** Backend-only. (A) `canonicalize_target_url` стрипає пагінаційні query-параметри → пагіновані сторінки схлопуються (target+article canonical). (B) host-guard у `create_suggestion` та `create_source` не пускає друге активне website-джерело того самого хоста. (C) `delete_source` чистить FK-залежності. Alembic-міграція backfill-ить canonical, деактивує наявні дубль-джерела й реджектить накопичені pending-дублі.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Alembic, pytest, MySQL.

## Global Constraints

- `canonicalize_target_url` стрипає лише пагінаційні ключі (`page`,`p`,`start`,`offset`) додатково до наявних `utm_*`/`_TRACKING_PARAMS`; змістовні query зберігаються; той самий виклик живить `target_url_canonical` І `article_url_canonical`.
- Політика: **одне активне website-джерело на хост**; guard лише для `type == website` (telegram/instagram/facebook — per-ref, незмінно).
- `delete_source` не має кидати: прибрати `SourceCrawlState` рядки + `offers.source_id → NULL` (nullable) перед `db.delete`.
- Міграція down_revision = `e5f6a7b8c9d0` (поточний head; звірити `alembic heads`). Backfill/cleanup deterministичні; логіка у named `_helper(conn)`-функціях (importlib-тест, як `test_migration_canonical.py`).
- Backend-тести: з `backend/` `./.venv/Scripts/python.exe -m pytest -q` (потрібен MySQL — `docker start mysql-container` або compose `db`).
- TDD, часті коміти, українською.

---

### Task 1: Пагінація-strip + `source_host` (urlnorm)

**Files:**
- Modify: `backend/app/core/urlnorm.py`
- Test: `backend/tests/test_urlnorm.py` (доповнити)

**Interfaces:**
- Produces: `canonicalize_target_url` ігнорує пагінаційні query-ключі; `source_host(url) -> str | None` (host lowercased, www-less, None для не-http(s)).

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_urlnorm.py`:

```python
from app.core.urlnorm import canonicalize_target_url, source_host


def test_pagination_params_stripped():
    base = "https://batart.army/en/en-gb-specials"
    assert canonicalize_target_url(base + "?page=2") == "batart.army/en/en-gb-specials"
    assert canonicalize_target_url(base + "?page=3") == canonicalize_target_url(base)
    assert canonicalize_target_url(base + "?p=5") == "batart.army/en/en-gb-specials"
    assert canonicalize_target_url(base + "?start=20&offset=40") == "batart.army/en/en-gb-specials"


def test_meaningful_query_kept():
    assert canonicalize_target_url("https://s.ua/x?id=5") == "s.ua/x?id=5"
    # meaningful param survives alongside a stripped pagination param
    assert canonicalize_target_url("https://s.ua/x?id=5&page=2") == "s.ua/x?id=5"


def test_source_host():
    assert source_host("https://www.Batart.Army/en/specials?page=2") == "batart.army"
    assert source_host("http://foo.ua") == "foo.ua"
    assert source_host("t.me/chan") is None          # non-http(s)
    assert source_host("") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_urlnorm.py -q`
Expected: FAIL — `ImportError: cannot import name 'source_host'` and pagination asserts fail.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/core/urlnorm.py`, add pagination set near `_TRACKING_PARAMS`:

```python
# Pagination/sort params stripped for offer dedup (a paginated listing is one identity).
_PAGINATION_PARAMS = frozenset({"page", "p", "start", "offset"})
```

In `canonicalize_target_url`, extend the `kept` filter to also drop pagination keys:

```python
    kept = sorted((k, v) for k, v in parse_qsl(p.query)
                  if not k.lower().startswith("utm_")
                  and k.lower() not in _TRACKING_PARAMS
                  and k.lower() not in _PAGINATION_PARAMS)
```

Add `source_host` at the end of the file:

```python
def source_host(url: str) -> str | None:
    """Bare host for source dedup: lowercased, www-less; None for non-http(s)/junk."""
    if not url:
        return None
    p = urlsplit(url.strip())
    if p.scheme not in ("http", "https") or not p.netloc:
        return None
    host = (p.hostname or "").removeprefix("www.").lower()
    return host or None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_urlnorm.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/urlnorm.py backend/tests/test_urlnorm.py
git commit -m "feat(backend): canonicalize strips pagination params; add source_host helper"
```

---

### Task 2: Host-dedup guards (suggestion + source creation)

**Files:**
- Modify: `backend/app/crud/suggested_source.py` (`create_suggestion`, ~14-34)
- Modify: `backend/app/crud/source.py` (`create_source`, ~9-15)
- Test: `backend/tests/test_suggestion_guard.py` (доповнити), `backend/tests/test_sources.py` (доповнити)

**Interfaces:**
- Consumes: `source_host` (Task 1).
- Produces: `create_suggestion` returns `None` (→204) for a website URL whose host already has an active website source; `create_source` returns the existing active website source for a host instead of creating a duplicate.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_sources.py`:

```python
from app.crud import source as source_crud
from app.schemas.source import SourceCreate
from app.models.enums import CreatedBy, SourceType


def test_create_source_dedups_website_by_host(db_session):
    a = source_crud.create_source(db_session, SourceCreate(
        name="Root", type=SourceType.website, url_or_handle="https://batart.army"),
        created_by=CreatedBy.admin)
    b = source_crud.create_source(db_session, SourceCreate(
        name="Specials", type=SourceType.website,
        url_or_handle="https://batart.army/en/specials?page=2"), created_by=CreatedBy.admin)
    assert b.id == a.id                                   # same host -> existing returned
    n = db_session.query(source_crud.Source).filter_by(url_or_handle="https://batart.army").count()
    assert n == 1


def test_create_source_allows_different_host_and_type(db_session):
    a = source_crud.create_source(db_session, SourceCreate(
        name="A", type=SourceType.website, url_or_handle="https://a.ua"),
        created_by=CreatedBy.admin)
    b = source_crud.create_source(db_session, SourceCreate(
        name="B", type=SourceType.website, url_or_handle="https://b.ua"),
        created_by=CreatedBy.admin)
    assert b.id != a.id                                   # different host -> new
```

Append to `backend/tests/test_suggestion_guard.py`:

```python
def test_website_suggestion_deduped_by_host(db_session):
    from app.crud import source as source_crud, suggested_source as sug_crud
    from app.schemas.source import SourceCreate
    from app.schemas.suggested_source import SuggestedSourceCreate
    from app.models.enums import CreatedBy, SourceType
    source_crud.create_source(db_session, SourceCreate(
        name="Root", type=SourceType.website, url_or_handle="https://batart.army"),
        created_by=CreatedBy.admin)
    # a DIFFERENT path on the same host must be 204'd (None)
    out = sug_crud.create_suggestion(db_session, SuggestedSourceCreate(
        name="Specials", type=SourceType.website,
        url_or_handle="https://batart.army/en/specials?page=3"))
    assert out is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_sources.py::test_create_source_dedups_website_by_host tests/test_suggestion_guard.py::test_website_suggestion_deduped_by_host -q`
Expected: FAIL — a second source/suggestion is created (b.id != a.id / out is not None).

- [ ] **Step 3: Write minimal implementation**

In `backend/app/crud/source.py`, add `source_host` import and a host-dedup check at the top of `create_source`:

```python
from app.core.urlnorm import source_host   # add near other imports
```

```python
def create_source(db: Session, data: SourceCreate, created_by: CreatedBy) -> Source:
    if data.type == SourceType.website:
        host = source_host(data.url_or_handle)
        if host:
            for s in (db.query(Source)
                      .filter(Source.type == SourceType.website, Source.is_active.is_(True))
                      .all()):
                if source_host(s.url_or_handle) == host:
                    return s                              # dedup: one active website source per host
    obj = Source(name=data.name, type=data.type, url_or_handle=data.url_or_handle,
                 is_active=data.is_active, created_by=created_by)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj
```

In `backend/app/crud/suggested_source.py`, add `source_host` import and a host check in `create_suggestion` after the exact-ref guard (after line ~19):

```python
from app.core.urlnorm import normalize_ref, source_host   # extend existing import
```

```python
    # exact-ref guard (existing) ...
    if any(normalize_ref(...) == ref for s in active):
        return None
    if data.type == "website":                            # host-level dedup for websites
        host = source_host(data.url_or_handle)
        if host and any(source_host(s.url_or_handle) == host for s in active):
            return None
    # ... existing SuggestedSource dup check + create
```

(`active` already = active sources of `data.type`; for website that's active website sources.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_sources.py tests/test_suggestion_guard.py tests/test_suggested_sources.py -q`
Expected: PASS (нові + наявні; `approve` через `create_source` тепер лінкує на наявне джерело замість дубля).

- [ ] **Step 5: Commit**

```bash
git add backend/app/crud/source.py backend/app/crud/suggested_source.py backend/tests/test_sources.py backend/tests/test_suggestion_guard.py
git commit -m "feat(backend): one active website source per host (suggestion + create guards)"
```

---

### Task 3: Фікс `delete_source` (FK-каскад, 500 → робочий)

**Files:**
- Modify: `backend/app/crud/source.py` (`delete_source`, ~41-44)
- Test: `backend/tests/test_sources.py` (доповнити)

**Interfaces:**
- Produces: `delete_source` прибирає `SourceCrawlState` рядки + `offers.source_id → NULL`, тоді видаляє Source; не кидає IntegrityError.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_sources.py`:

```python
def test_delete_source_with_crawl_state_and_offers(db_session):
    from app.crud import source as source_crud
    from app.schemas.source import SourceCreate
    from app.models import Offer, SourceCrawlState
    from app.models.enums import CreatedBy, OfferStatus, OfferType, SourceType
    src = source_crud.create_source(db_session, SourceCreate(
        name="S", type=SourceType.website, url_or_handle="https://del.ua"),
        created_by=CreatedBy.admin)
    db_session.add(SourceCrawlState(source_id=src.id, last_seen_key="k"))
    off = Offer(type=OfferType.discount, title="T", description="", provider="P",
                source_id=src.id, status=OfferStatus.published, created_by=CreatedBy.crawler)
    db_session.add(off)
    db_session.commit()
    off_id = off.id

    source_crud.delete_source(db_session, src.id)          # must NOT raise IntegrityError
    db_session.expire_all()
    assert db_session.get(source_crud.Source, src.id) is None          # source gone
    assert db_session.get(Offer, off_id).source_id is None             # offer orphaned, survives
    assert db_session.query(SourceCrawlState).filter_by(source_id=src.id).count() == 0
```

(Confirm `SourceCrawlState`'s NOT-NULL columns: if `last_seen_key` is required, keep as above; if the model needs other fields, add them per `backend/app/models/source_crawl_state.py`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_sources.py::test_delete_source_with_crawl_state_and_offers -q`
Expected: FAIL — `IntegrityError` (FK `source_crawl_state` / `offers`).

- [ ] **Step 3: Write minimal implementation**

In `backend/app/crud/source.py`, replace `delete_source`:

```python
def delete_source(db: Session, source_id: int) -> None:
    from app.models import Offer, SourceCrawlState   # local import avoids cycle
    obj = get_source(db, source_id)
    db.query(SourceCrawlState).filter(SourceCrawlState.source_id == source_id)\
        .delete(synchronize_session=False)                # ephemeral crawl cursor — safe to drop
    db.query(Offer).filter(Offer.source_id == source_id)\
        .update({Offer.source_id: None}, synchronize_session=False)   # offers survive orphaned
    db.delete(obj)
    db.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_sources.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/crud/source.py backend/tests/test_sources.py
git commit -m "fix(backend): delete_source clears crawl_state + nulls offer FK (no more 500)"
```

---

### Task 4: Alembic-міграція (backfill canonical + dedup sources + reject pending dups)

**Files:**
- Create: `backend/alembic/versions/c3d5e7f9a1b2_offer_source_dedup.py`
- Test: `backend/tests/test_migration_dedup.py`

**Interfaces:**
- Consumes: `canonicalize_target_url` (Task 1), `source_host` (Task 1).
- Produces: three importlib-testable helpers — `_backfill_canonical(conn)`, `_dedup_sources(conn)`, `_reject_published_pending_dups(conn)` — called by `upgrade()`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_migration_dedup.py`:

```python
import importlib.util
import pathlib

from app.models import Offer, Source
from app.models.enums import CreatedBy, OfferStatus, OfferType, SourceType


def _load(name):
    path = (pathlib.Path(__file__).resolve().parents[1]
            / "alembic" / "versions" / "c3d5e7f9a1b2_offer_source_dedup.py")
    spec = importlib.util.spec_from_file_location("mig_dedup", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, name)


def test_backfill_strips_pagination(db_session):
    o = Offer(type=OfferType.discount, title="T", description="", provider="P",
              target_url="https://b.army/specials?page=2",
              article_url="https://b.army/specials?page=2",
              status=OfferStatus.published, created_by=CreatedBy.crawler)
    db_session.add(o); db_session.commit()
    _load("_backfill_canonical")(db_session.connection())
    db_session.expire_all()
    r = db_session.get(Offer, o.id)
    assert r.target_url_canonical == "b.army/specials"
    assert r.article_url_canonical == "b.army/specials"


def test_dedup_sources_keeps_owner_of_most_offers(db_session):
    s_root = Source(name="Root", type=SourceType.website, url_or_handle="https://b.army",
                    is_active=True, created_by=CreatedBy.admin)
    s_pg = Source(name="Pg", type=SourceType.website,
                  url_or_handle="https://b.army/specials?page=2", is_active=True,
                  created_by=CreatedBy.admin)
    db_session.add_all([s_root, s_pg]); db_session.commit()
    # s_pg owns an offer -> must stay active; s_root deactivated
    db_session.add(Offer(type=OfferType.discount, title="T", description="", provider="P",
                         source_id=s_pg.id, status=OfferStatus.published,
                         created_by=CreatedBy.crawler))
    db_session.commit()
    _load("_dedup_sources")(db_session.connection())
    db_session.expire_all()
    assert db_session.get(Source, s_pg.id).is_active is True
    assert db_session.get(Source, s_root.id).is_active is False


def test_reject_pending_dups_of_published(db_session):
    pub = Offer(type=OfferType.discount, title="P", description="", provider="P",
                article_url_canonical="b.army/specials", status=OfferStatus.published,
                created_by=CreatedBy.crawler)
    pend = Offer(type=OfferType.discount, title="D", description="", provider="P",
                 article_url_canonical="b.army/specials", status=OfferStatus.pending_review,
                 created_by=CreatedBy.crawler)
    db_session.add_all([pub, pend]); db_session.commit()
    _load("_reject_published_pending_dups")(db_session.connection())
    db_session.expire_all()
    assert db_session.get(Offer, pend.id).status == OfferStatus.rejected
    assert db_session.get(Offer, pub.id).status == OfferStatus.published
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_migration_dedup.py -q`
Expected: FAIL — migration file / helpers do not exist.

- [ ] **Step 3: Write minimal implementation**

Create `backend/alembic/versions/c3d5e7f9a1b2_offer_source_dedup.py`:

```python
"""offer/source dedup: pagination canonical + one website source per host + reject dups

Revision ID: c3d5e7f9a1b2
Revises: e5f6a7b8c9d0
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d5e7f9a1b2"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _backfill_canonical(conn) -> None:
    from app.core.urlnorm import canonicalize_target_url
    rows = conn.execute(sa.text(
        "SELECT id, target_url, article_url FROM offers "
        "WHERE target_url IS NOT NULL OR article_url IS NOT NULL")).fetchall()
    for rid, turl, aurl in rows:
        conn.execute(sa.text(
            "UPDATE offers SET target_url_canonical=:t, article_url_canonical=:a WHERE id=:i"),
            {"t": canonicalize_target_url(turl) if turl else None,
             "a": canonicalize_target_url(aurl) if aurl else None, "i": rid})


def _dedup_sources(conn) -> None:
    from app.core.urlnorm import source_host
    rows = conn.execute(sa.text(
        "SELECT id, url_or_handle FROM sources WHERE type='website' AND is_active=1")).fetchall()
    by_host: dict[str, list[int]] = {}
    for sid, url in rows:
        h = source_host(url)
        if h:
            by_host.setdefault(h, []).append(sid)
    for h, ids in by_host.items():
        if len(ids) < 2:
            continue
        counts = {sid: conn.execute(sa.text(
            "SELECT COUNT(*) FROM offers WHERE source_id=:s"), {"s": sid}).scalar() for sid in ids}
        keep = max(ids, key=lambda s: (counts[s], -s))     # most offers; tie -> lowest id
        for sid in ids:
            if sid != keep:
                conn.execute(sa.text("UPDATE sources SET is_active=0 WHERE id=:s"), {"s": sid})


def _reject_published_pending_dups(conn) -> None:
    conn.execute(sa.text(
        "UPDATE offers p JOIN ("
        "  SELECT DISTINCT article_url_canonical AS a FROM offers "
        "  WHERE status='published' AND article_url_canonical IS NOT NULL"
        ") pub ON p.article_url_canonical = pub.a "
        "SET p.status='rejected' WHERE p.status='pending_review'"))


def upgrade() -> None:
    conn = op.get_bind()
    _backfill_canonical(conn)
    _dedup_sources(conn)
    _reject_published_pending_dups(conn)


def downgrade() -> None:
    pass   # data cleanup — not reversible (matches prior backfill migrations)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_migration_dedup.py -q`
Expected: PASS (3 helpers).

- [ ] **Step 5: Run full backend suite + alembic round-trip**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — усі наявні + нові.

Run: `cd backend && ./.venv/Scripts/python.exe -m alembic upgrade head && ./.venv/Scripts/python.exe -m alembic heads`
Expected: head = `c3d5e7f9a1b2`, no error.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/c3d5e7f9a1b2_offer_source_dedup.py backend/tests/test_migration_dedup.py
git commit -m "feat(backend): migration — pagination canonical backfill + source dedup + reject pending dups"
```

---

## Post-implementation

- Requesting-code-review (opus whole-branch) перед merge.
- Жива Docker-перевірка: перезібрати backend, `alembic upgrade head` на реальній `ubd`; batart → одна картка (#173 published, 254–258 rejected); один активний website-source на batart; delete-source в адмінці більше не 500.
- Merge (ff) у main, push, оновити пам'ять.

## Self-Review (виконано)

**Spec coverage:** A пагінація (Task 1) · source_host (Task 1) · host-guard suggestion+create (Task 2) · delete_source fix (Task 3) · міграція backfill+dedup+reject (Task 4). Усі секції спеки покрито.

**Placeholder scan:** плейсхолдерів немає; код наведено дослівно. `SourceCrawlState` поля — нотатка в Task 3 звірити модель.

**Type consistency:** `source_host(url)->str|None`, `canonicalize_target_url` (Task 1) вжиті однаково в Tasks 2/4; міграція-хелпери `_backfill_canonical`/`_dedup_sources`/`_reject_published_pending_dups` узгоджені між кодом і тестом (Task 4); `create_source` повертає `Source` (наявне або нове) — консистентно з `approve`.
