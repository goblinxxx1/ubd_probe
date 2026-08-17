# Russian-site geo-gate for gTLD hosts — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Reject Russian sites on gTLDs — via a Russian-city subdomain heuristic in the geo-gate + a durable seed of known Russian apex domains in the blocklist — without over-blocking Ukrainian sites.

**Architecture:** Extend `crawler/util/hosts.py::is_foreign_host` with a curated Russian-city subdomain set (subdomain-only, `.ua` allowed first). Add an Alembic migration seeding known Russian apex domains into `blocked_hosts` (mirrors the #34 news seed). Both signals gate the existing crawler fetch path with no new call sites.

**Tech Stack:** Python 3.12, pytest, Alembic, MySQL.

## Global Constraints

- Crawler tests from `crawler/`: `./.venv/Scripts/python.exe -m pytest -q`. Backend from `backend/`: same (needs `mysql-container` on :3306).
- TDD: failing test first, minimal impl, green, commit.
- Heuristic fires on **subdomains only** (`len(labels) >= 3`), `.ua` allowed first — no apex/UA over-block. City list = unambiguous Russian codes only.
- Migration idempotent (`ON DUPLICATE KEY UPDATE`), mirrors `d4e6f8a0b2c4`; down_revision = current head `a7c1e9d3b5f2`. No new deps.

---

### Task 1: Russian-city subdomain heuristic in `is_foreign_host`

**Files:**
- Modify: `crawler/crawler/util/hosts.py`
- Test: `crawler/tests/test_hosts.py`

**Interfaces:**
- Produces: `is_foreign_host(value)` additionally returns `True` when the host is a subdomain (`>=3` labels) whose leading label is a Russian city code. Adds module constant `_RU_CITY_SUBDOMAINS: frozenset[str]`.

- [ ] **Step 1: Write the failing tests**

Append to `crawler/tests/test_hosts.py`:

```python
def test_russian_city_subdomain_on_gtld_is_foreign():
    assert is_foreign_host("https://spb.boombate.com/zdorove/fitnes-kluby") is True
    assert is_foreign_host("msk.example.net") is True
    assert is_foreign_host("https://www.spb.foo.com/x") is True   # www stripped, spb kept
    assert is_foreign_host("ekb.shop.org") is True


def test_russian_heuristic_does_not_overblock():
    assert is_foreign_host("edclinic.com.ua") is False            # .ua host
    assert is_foreign_host("spb.example.com.ua") is False         # .ua wins even with spb
    assert is_foreign_host("shop.com") is False                   # legit gTLD, no ru subdomain
    assert is_foreign_host("mate.academy") is False
    assert is_foreign_host("sub.mate.academy") is False           # non-ru subdomain
    assert is_foreign_host("boombate.com") is False               # apex -> blocklist's job, not geo-gate
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_hosts.py -q -k russian`
Expected: FAIL — `spb.boombate.com` currently returns False (gTLD allowed).

- [ ] **Step 3: Add the city set + the heuristic**

In `crawler/crawler/util/hosts.py`, add the constant next to `_GENERIC_CCTLDS`:

```python
# Однозначні коди російських міст як leading-субдомен — російський сайт на gTLD
# (spb.boombate.com). Лише безсумнівні (без коротких/двозначних, що колізять з UA).
_RU_CITY_SUBDOMAINS = frozenset({
    "spb", "msk", "mow", "ekb", "nsk", "kzn", "rostov", "sochi", "samara", "perm",
    "omsk", "ufa", "krasnodar", "volgograd", "voronezh", "tyumen", "irkutsk",
    "vladivostok", "khabarovsk", "chelyabinsk", "kaliningrad", "saratov",
    "barnaul", "tomsk", "kemerovo",
})
```

In `is_foreign_host`, insert the check immediately after the `.ua` allow line
(`if host == "ua" or host.endswith(".ua"): return False`), before the TLD logic:

```python
    labels = host.split(".")
    if len(labels) >= 3 and labels[0] in _RU_CITY_SUBDOMAINS:
        return True                          # російський місто-субдомен на gTLD
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_hosts.py -q`
Expected: PASS — new Russian tests green; existing ccTLD/UA tests unaffected.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/util/hosts.py crawler/tests/test_hosts.py
git commit -m "feat(crawler): reject Russian-city subdomains on gTLD in is_foreign_host"
```

---

### Task 2: Seed migration for known Russian apex domains

**Files:**
- Create: `backend/alembic/versions/<rev>_seed_russian_apex_blocklist.py`
- Test: `backend/tests/test_migration_russian_apex_seed.py`

**Interfaces:**
- Produces: migration module with `SEED_HOSTS: list[str]` and `_seed(conn)`; upgrade seeds them into `blocked_hosts` as `approved` (idempotent), downgrade removes the system-seeded rows.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_migration_russian_apex_seed.py`:

```python
import importlib.util
import pathlib

from app.crud import blocked_host as bh


def _load():
    versions = (pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions")
    path = next(versions.glob("*seed_russian_apex_blocklist.py"))
    spec = importlib.util.spec_from_file_location("mig_seed_ru_apex", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_ru_apex_seed_inserts_approved_idempotently(db_session):
    mod = _load()
    conn = db_session.connection()
    mod._seed(conn)
    db_session.commit()
    approved = bh.list_approved_hosts(db_session)
    assert "boombate.com" in approved
    assert set(mod.SEED_HOSTS).issubset(set(approved))
    # idempotent: a second run does not duplicate
    conn = db_session.connection()
    mod._seed(conn)
    db_session.commit()
    assert bh.list_approved_hosts(db_session).count("boombate.com") == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `backend/`): `./.venv/Scripts/python.exe -m pytest tests/test_migration_russian_apex_seed.py -q`
Expected: FAIL — `StopIteration` (migration file does not exist yet).

- [ ] **Step 3: Create the migration**

Create `backend/alembic/versions/b3e7d1c9f4a2_seed_russian_apex_blocklist.py`:

```python
"""seed russian apex blocklist

Revision ID: b3e7d1c9f4a2
Revises: a7c1e9d3b5f2
Create Date: 2026-08-11

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = 'b3e7d1c9f4a2'
down_revision: Union[str, Sequence[str], None] = 'a7c1e9d3b5f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Known Russian sites on gTLDs — apex domains the subdomain heuristic can't catch.
SEED_HOSTS = [
    "boombate.com",
]


def _seed(conn):
    for h in SEED_HOSTS:
        conn.execute(text(
            "INSERT INTO blocked_hosts (host, status, media_ratio, aggregator_ratio, support, "
            "created_at) VALUES (:h, 'approved', 0, 0, 0, NOW()) "
            "ON DUPLICATE KEY UPDATE status='approved'"), {"h": h})


def upgrade() -> None:
    _seed(op.get_bind())


def downgrade() -> None:
    conn = op.get_bind()
    for h in SEED_HOSTS:
        conn.execute(text("DELETE FROM blocked_hosts WHERE host = :h AND reviewed_by IS NULL"),
                     {"h": h})
```

- [ ] **Step 4: Run test + full backend suite**

Run (from `backend/`): `./.venv/Scripts/python.exe -m pytest tests/test_migration_russian_apex_seed.py -q`
Expected: PASS. Then confirm the migration chain is linear: `./.venv/Scripts/python.exe -m alembic heads` → single head `b3e7d1c9f4a2`.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/b3e7d1c9f4a2_seed_russian_apex_blocklist.py backend/tests/test_migration_russian_apex_seed.py
git commit -m "feat(backend): seed known Russian apex domains into blocked_hosts"
```

---

### Task 3: Deploy + live verification

**Files:** none (Docker rebuild + migration + live checks).

- [ ] **Step 1: Merge (after review) + rebuild**

```bash
git checkout main && git merge --ff-only feat/russian-gtld-geo-gate
docker compose build backend crawler && docker compose up -d backend
```

- [ ] **Step 2: Apply the migration on the live DB**

```bash
docker compose exec backend alembic upgrade head
docker exec ubd_probe-db-1 mysql -uroot -pmy-secret-pw -N ubd -e "SELECT host,status FROM blocked_hosts WHERE host='boombate.com';"
```
Expected: `boombate.com approved`.

- [ ] **Step 3: Live-verify the heuristic in the crawler image**

```bash
docker compose --profile crawler up -d crawler
docker exec -i ubd_probe-crawler-1 python -c "from crawler.util.hosts import is_foreign_host; print('spb.boombate.com', is_foreign_host('https://spb.boombate.com/x')); print('edclinic.com.ua', is_foreign_host('edclinic.com.ua')); print('shop.com', is_foreign_host('shop.com'))"
```
Expected: `spb.boombate.com True`, `edclinic.com.ua False`, `shop.com False`.
