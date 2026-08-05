# Auto-reject noise offers by source host + learn blocklist — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-reject crawler offers whose source host (site_url/article_url/provider) is a blocked media/social host, seed the observed hosts, and grow the blocklist from moderator rejections (host with ≥2 rejected and 0 published auto-blocks).

**Architecture:** Backend-only. Reuse the existing `blocked_hosts` table (approved list already consumed by the crawler for no-fetch). A gate in `create_offer` forces `rejected`; a learner in `set_status` auto-blocks culprit hosts on rejection; an Alembic migration seeds the curated host list. Host membership is **suffix-match** (a blocked registrable domain covers its subdomains), mirroring the crawler's `is_blocked_host`.

**Tech Stack:** Python, SQLAlchemy, Alembic, pytest. Backend tests need a MySQL at :3306 — `docker start mysql-container` first.

## Global Constraints

- Backend-only. Do NOT change crawler/admin/public.
- Test command (from `backend/`): `./.venv/Scripts/python.exe -m pytest -q` (requires `mysql-container` on :3306).
- Reuse `blocked_hosts` (`app/crud/blocked_host.py`, `app/models/blocked_host.py`). Statuses: `pending`/`approved`/`rejected` (`BlockedHostStatus`). Approved list = live blocklist.
- Host normalization = `bare_host` (lowercase, strip scheme/path/port and leading `www.`). Membership = exact OR suffix (`h == b or h.endswith("." + b)`).
- Gate applies ONLY to `created_by == CreatedBy.crawler`. Admin offers untouched.
- Auto-learn guard: block a host only when it has **≥2 rejected AND 0 published** offers (protects dual-status business hosts). Threshold constant `_AUTOBLOCK_MIN_REJECTS = 2`.
- Auto-block sets `reviewed_by = None` (system), status `approved`.
- Alembic head to build on: `down_revision = "c3d5e7f9a1b2"`.
- OfferCreate/OfferBase fields available: `type, title, description, provider, discount_type, discount_value, site_url, article_url, target_url, target_category_ids, offer_category_ids`. Crawler test pattern: `OfferCreate(type="discount", title="T", provider="P", site_url=..., ...)` then `create_offer(db, data, CreatedBy.crawler, OfferStatus.pending_review)`.

---

### Task 1: `blocked_host` — public `bare_host` + `auto_block`

**Files:**
- Modify: `backend/app/crud/blocked_host.py`
- Test: `backend/tests/test_blocked_hosts.py`

**Interfaces:**
- Produces: `bare_host(value: str) -> str` (public rename of `_bare_host`); `auto_block(db: Session, host: str) -> BlockedHost` (upsert host → status approved, reviewed_by None; idempotent).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_blocked_hosts.py` (uses the existing `db_session` fixture):
```python
def test_auto_block_creates_approved_system_row(db_session):
    from app.crud import blocked_host as bh
    from app.models.enums import BlockedHostStatus
    obj = bh.auto_block(db_session, "Fraza.UA")
    assert obj.host == "fraza.ua"
    assert obj.status == BlockedHostStatus.approved
    assert obj.reviewed_by is None
    assert "fraza.ua" in bh.list_approved_hosts(db_session)

def test_auto_block_is_idempotent(db_session):
    from app.crud import blocked_host as bh
    bh.auto_block(db_session, "znaj.ua")
    bh.auto_block(db_session, "znaj.ua")
    approved = bh.list_approved_hosts(db_session)
    assert approved.count("znaj.ua") == 1

def test_bare_host_is_public(db_session):
    from app.crud.blocked_host import bare_host
    assert bare_host("https://www.Focus.ua/x?y=1") == "focus.ua"
    assert bare_host("") == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_blocked_hosts.py -k "auto_block or bare_host_is_public"`
Expected: FAIL — `auto_block` / public `bare_host` not defined (ImportError/AttributeError).

- [ ] **Step 3: Implement in `blocked_host.py`**

Rename `_bare_host` → `bare_host` (the `def` at line ~12 and its use inside `add_manual` at line ~77: `h = bare_host(host)`). Then add:
```python
def auto_block(db: Session, host: str) -> BlockedHost:
    """System (non-human) block: upsert host to approved with reviewed_by=None.
    Idempotent — an existing row is promoted to approved."""
    h = bare_host(host)
    if not h:
        raise validation_error("host is required")
    obj = db.query(BlockedHost).filter(BlockedHost.host == h).first()
    if obj is None:
        obj = BlockedHost(host=h, status=BlockedHostStatus.approved, reviewed_by=None,
                          reviewed_at=datetime.now(timezone.utc))
        db.add(obj)
    else:
        obj.status = BlockedHostStatus.approved
    db.commit()
    db.refresh(obj)
    return obj
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_blocked_hosts.py`
Expected: PASS (existing blocked-host tests still green after the rename).

- [ ] **Step 5: Commit**

```bash
git add backend/app/crud/blocked_host.py backend/tests/test_blocked_hosts.py
git commit -m "feat(backend): blocked_host public bare_host + auto_block (system block)"
```

---

### Task 2: Auto-reject gate in `create_offer`

**Files:**
- Modify: `backend/app/crud/offer.py`
- Test: `backend/tests/test_offer_autoreject.py` (create)

**Interfaces:**
- Consumes: `bare_host`, `list_approved_hosts` from `app.crud.blocked_host` (Task 1).
- Produces: module helpers `_host_blocked(h: str, approved: set[str]) -> bool`, `_blocked_source_host(db, data) -> str | None`. `create_offer` unchanged signature; a crawler offer with a blocked source host is created with `status=OfferStatus.rejected` and skips dedup branches.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_offer_autoreject.py`:
```python
from app.crud import offer as offer_crud
from app.crud import blocked_host as bh
from app.schemas.offer import OfferCreate
from app.models.enums import CreatedBy, OfferStatus


def _crawler(db, **kw):
    data = OfferCreate(type="discount", title=kw.pop("title", "T"),
                       provider=kw.pop("provider", "Biz"), **kw)
    return offer_crud.create_offer(db, data, CreatedBy.crawler, OfferStatus.pending_review)


def test_gate_rejects_offer_from_blocked_site_host(db_session):
    bh.auto_block(db_session, "fraza.ua")
    o = _crawler(db_session, site_url="https://fraza.ua/x", article_url="https://fraza.ua/x",
                 provider="uglovoy.com.ua", target_url="https://uglovoy.com.ua")
    assert o.status == OfferStatus.rejected


def test_gate_matches_subdomain_of_blocked_host(db_session):
    bh.auto_block(db_session, "znaj.ua")
    o = _crawler(db_session, article_url="https://breaking.znaj.ua/post", provider="Shop")
    assert o.status == OfferStatus.rejected


def test_gate_rejects_on_blocked_provider_host(db_session):
    bh.auto_block(db_session, "google.com")
    o = _crawler(db_session, provider="google.com", site_url="https://google.com/x")
    assert o.status == OfferStatus.rejected


def test_gate_passes_clean_business_host(db_session):
    o = _crawler(db_session, site_url="https://reima.ua/mil", provider="reima.ua",
                 target_url="https://reima.ua")
    assert o.status == OfferStatus.pending_review


def test_gate_ignores_admin_offers(db_session):
    bh.auto_block(db_session, "fraza.ua")
    data = OfferCreate(type="discount", title="T", provider="fraza.ua",
                       site_url="https://fraza.ua/x")
    o = offer_crud.create_offer(db_session, data, CreatedBy.admin, OfferStatus.published)
    assert o.status == OfferStatus.published   # admin path untouched
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_offer_autoreject.py`
Expected: FAIL — gate not implemented (blocked-host offers still go pending_review / merge).

- [ ] **Step 3: Implement the gate in `offer.py`**

At the top of `offer.py`, add imports and helpers (place near other module-level helpers):
```python
from app.crud.blocked_host import bare_host, list_approved_hosts


def _host_blocked(h: str, approved: set[str]) -> bool:
    return bool(h) and any(h == b or h.endswith("." + b) for b in approved)


def _blocked_source_host(db: Session, data) -> str | None:
    approved = set(list_approved_hosts(db))
    if not approved:
        return None
    for val in (getattr(data, "site_url", None), getattr(data, "article_url", None),
                getattr(data, "provider", None)):
        h = bare_host(val or "")
        if _host_blocked(h, approved):
            return h
    return None
```

In `create_offer`, right after `crawler = created_by == CreatedBy.crawler` (≈ line 76), add:
```python
    blocked = crawler and _blocked_source_host(db, data) is not None
    if blocked:
        status = OfferStatus.rejected   # force-reject a blocked-source offer
```
Then guard the four dedup branches so a blocked offer skips them and falls through to the plain create. Change the branch conditions:
- Branch 1 guard `if content_hash is not None and crawler:` → `if content_hash is not None and crawler and not blocked:`
- Branch 2/3 guard `if crawler and canon_article and source_id is not None:` → `if crawler and canon_article and source_id is not None and not blocked:`
- Branch 4 guard `if crawler and canon:` → `if crawler and canon and not blocked:`

The final `Offer(...)` create already uses `status=status`, which is now `rejected` for blocked offers — no further change.

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_offer_autoreject.py tests/test_offer_merge.py tests/test_offer_shadow.py`
Expected: PASS (gate works; existing merge/shadow dedup unaffected for non-blocked offers).

- [ ] **Step 5: Commit**

```bash
git add backend/app/crud/offer.py backend/tests/test_offer_autoreject.py
git commit -m "feat(backend): auto-reject crawler offers from blocked source host"
```

---

### Task 3: Auto-learn blocklist on rejection (`set_status`)

**Files:**
- Modify: `backend/app/crud/offer.py`
- Test: `backend/tests/test_offer_autoreject.py` (append)

**Interfaces:**
- Consumes: `bare_host`, `list_approved_hosts`, `auto_block` (Tasks 1); `_host_blocked` (Task 2).
- Produces: `_AUTOBLOCK_MIN_REJECTS = 2`; `_maybe_autoblock_hosts(db, offer)` called from `set_status` when transitioning to `rejected`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_offer_autoreject.py`:
```python
def _mk(db, status, **kw):
    from app.models.offer import Offer
    from app.models.enums import OfferType
    o = Offer(type=OfferType.discount, title="T", description="", provider=kw.get("provider", "P"),
              status=status, created_by=CreatedBy.crawler,
              site_url=kw.get("site_url"), article_url=kw.get("article_url"))
    db.add(o); db.commit(); db.refresh(o)
    return o


def test_learn_blocks_host_after_second_reject_zero_published(db_session):
    _mk(db_session, OfferStatus.rejected, article_url="https://ogo.ua/a")
    o2 = _mk(db_session, OfferStatus.pending_review, article_url="https://ogo.ua/b")
    offer_crud.set_status(db_session, o2.id, OfferStatus.rejected, reviewed_by=1)
    assert "ogo.ua" in bh.list_approved_hosts(db_session)


def test_learn_does_not_block_host_with_a_published_offer(db_session):
    _mk(db_session, OfferStatus.published, site_url="https://reima.ua/x")
    _mk(db_session, OfferStatus.rejected, site_url="https://reima.ua/y")
    o = _mk(db_session, OfferStatus.pending_review, site_url="https://reima.ua/z")
    offer_crud.set_status(db_session, o.id, OfferStatus.rejected, reviewed_by=1)
    assert "reima.ua" not in bh.list_approved_hosts(db_session)


def test_learn_requires_two_rejections(db_session):
    o = _mk(db_session, OfferStatus.pending_review, article_url="https://izum.ua/a")
    offer_crud.set_status(db_session, o.id, OfferStatus.rejected, reviewed_by=1)
    assert "izum.ua" not in bh.list_approved_hosts(db_session)   # only 1 rejected so far
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_offer_autoreject.py -k learn`
Expected: FAIL — no auto-learn yet.

- [ ] **Step 3: Implement in `offer.py`**

Add module constant and helper:
```python
_AUTOBLOCK_MIN_REJECTS = 2


def _offer_host_candidates(offer) -> set[str]:
    return {h for h in (bare_host(offer.site_url or ""), bare_host(offer.article_url or ""),
                        bare_host(offer.provider or "")) if h}


def _maybe_autoblock_hosts(db: Session, offer) -> None:
    """After an offer is rejected, auto-block any source host with >=2 rejected and 0
    published offers (guard protects dual-status business hosts)."""
    from app.crud.blocked_host import auto_block
    approved = set(list_approved_hosts(db))
    for h in _offer_host_candidates(offer):
        if _host_blocked(h, approved):
            continue
        like = f"%{h}%"
        rows = (db.query(Offer)
                .filter((Offer.site_url.like(like)) | (Offer.article_url.like(like))
                        | (Offer.provider.like(like)))
                .all())
        rejected = published = 0
        for r in rows:
            if not any(_host_blocked(fh, {h}) for fh in _offer_host_candidates(r)):
                continue   # LIKE false-positive; exact/suffix host must match
            if r.status == OfferStatus.published:
                published += 1
            elif r.status == OfferStatus.rejected:
                rejected += 1
        if published == 0 and rejected >= _AUTOBLOCK_MIN_REJECTS:
            auto_block(db, h)
```

In `set_status`, after `obj.status = status` / before/around the commit, add (best-effort, must not break the reject):
```python
    if status == OfferStatus.rejected:
        try:
            _maybe_autoblock_hosts(db, obj)
        except Exception:  # noqa: BLE001 — learning is best-effort
            pass
```
Place this before `db.commit()` so the auto_block writes commit together; `auto_block` itself commits, which also persists the status change — acceptable (single logical rejection). Ensure `obj.status` is already set to rejected before counting (it is).

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_offer_autoreject.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/crud/offer.py backend/tests/test_offer_autoreject.py
git commit -m "feat(backend): learn blocklist from rejections (>=2 rejected, 0 published)"
```

---

### Task 4: Seed migration — curated media/social hosts

**Files:**
- Create: `backend/alembic/versions/d4e6f8a0b2c4_seed_media_blocklist.py`
- Test: `backend/tests/test_migration_blocked_hosts_seed.py` (create)

**Interfaces:**
- Produces: migration module with `SEED_HOSTS: list[str]` and `_seed(conn)` (idempotent insert of approved hosts), plus standard `upgrade()`/`downgrade()`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_migration_blocked_hosts_seed.py` (mirrors `test_migration_offer_locations.py`):
```python
import importlib.util
import pathlib

from app.crud import blocked_host as bh


def _load():
    path = (pathlib.Path(__file__).resolve().parents[1]
            / "alembic" / "versions" / "d4e6f8a0b2c4_seed_media_blocklist.py")
    spec = importlib.util.spec_from_file_location("mig_seed_blocklist", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_seed_inserts_approved_hosts_idempotently(db_session):
    mod = _load()
    conn = db_session.connection()
    mod._seed(conn)
    db_session.commit()
    approved = bh.list_approved_hosts(db_session)
    for h in ("fraza.ua", "znaj.ua", "google.com", "api.whatsapp.com"):
        assert h in approved
    # idempotent: second run does not duplicate
    conn = db_session.connection()
    mod._seed(conn)
    db_session.commit()
    approved2 = bh.list_approved_hosts(db_session)
    assert approved2.count("fraza.ua") == 1
    assert set(mod.SEED_HOSTS).issubset(set(approved2))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_migration_blocked_hosts_seed.py`
Expected: FAIL — migration file does not exist yet.

- [ ] **Step 3: Create the migration**

Create `backend/alembic/versions/d4e6f8a0b2c4_seed_media_blocklist.py`:
```python
"""seed media/social host blocklist

Revision ID: d4e6f8a0b2c4
Revises: c3d5e7f9a1b2
Create Date: 2026-08-05
"""
from alembic import op
from sqlalchemy import text

revision = "d4e6f8a0b2c4"
down_revision = "c3d5e7f9a1b2"
branch_labels = None
depends_on = None

SEED_HOSTS = [
    "fraza.ua", "znaj.ua", "epravda.com.ua", "focus.ua", "kosht.media", "24tv.ua",
    "unn.ua", "parlament.ua", "rubryka.com", "ogo.ua", "izum.ua", "nefterynok.info",
    "uc.kr.ua", "pravdahub.com.ua", "ukrainianwall.com", "dtkt.ua",
    "api.whatsapp.com", "news.google.com", "google.com", "linkedin.com",
    "linktr.ee", "addtoany.com",
]


def _seed(conn):
    for h in SEED_HOSTS:
        conn.execute(text(
            "INSERT INTO blocked_hosts (host, status, media_ratio, aggregator_ratio, support, "
            "created_at) VALUES (:h, 'approved', 0, 0, 0, NOW()) "
            "ON DUPLICATE KEY UPDATE status='approved'"), {"h": h})


def upgrade():
    _seed(op.get_bind())


def downgrade():
    conn = op.get_bind()
    for h in SEED_HOSTS:
        conn.execute(text("DELETE FROM blocked_hosts WHERE host = :h AND reviewed_by IS NULL"),
                     {"h": h})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_migration_blocked_hosts_seed.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/d4e6f8a0b2c4_seed_media_blocklist.py backend/tests/test_migration_blocked_hosts_seed.py
git commit -m "feat(backend): seed curated media/social host blocklist (migration)"
```

---

### Task 5: Full suite + deploy verification

**Files:** none (verification/deploy).

- [ ] **Step 1: Full backend suite green**

Run (from `backend/`, `docker start mysql-container` first): `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS, 0 failures.

- [ ] **Step 2: Apply the migration to the live compose DB + rebuild backend**

```bash
docker compose up -d --build backend
docker compose exec backend alembic upgrade head
```
Expected: migration `d4e6f8a0b2c4` applied; `SELECT COUNT(*) FROM blocked_hosts WHERE status='approved'` includes the seed hosts.

- [ ] **Step 3: Live check — the offer-365 class is now auto-rejected**

Confirm via DB that a fresh crawler submission from a seeded host (e.g. `fraza.ua`) lands as `rejected`, and that existing published offers are untouched. Report counts.

---

## Self-Review notes
- **Spec coverage:** Component 1 (gate) → Task 2; Component 2 (seed) → Task 4; Component 3 (learn) → Task 3; `auto_block`/`bare_host` groundwork → Task 1; verification → Task 5.
- **Refinement vs spec:** membership is exact-OR-suffix (`_host_blocked`) so a seeded registrable domain (znaj.ua) covers subdomains (breaking.znaj.ua) — matches the crawler's blocklist semantics; noted in Global Constraints.
- **Type consistency:** `bare_host`, `auto_block(db, host)`, `_host_blocked(h, approved)`, `_blocked_source_host(db, data)`, `_maybe_autoblock_hosts(db, offer)`, `_AUTOBLOCK_MIN_REJECTS` used consistently across tasks.
- **No placeholders:** every code/edit step shows exact content and exact dedup-branch guard edits.
