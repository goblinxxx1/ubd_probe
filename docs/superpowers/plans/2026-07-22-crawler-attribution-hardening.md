# Crawler attribution hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Catch media/aggregator pages structurally in the live attribution gate (beyond the static blocklist), salvage real offers via outbound links, and grow the media-host blocklist automatically via an offline miner + backend-backed Vue audit — while preserving all existing crawler automation.

**Architecture:** 3 layers. **A (crawler live gate, ON):** `RawItem.is_article`/`has_business_schema` from schema.org; `attribute()` treats article/aggregator pages as never-first-party with outbound salvage; `is_blocked_host` = SEED + fetched LEARNED. **B (offline, crawler):** extend the shared corpus additively; `host_miner` aggregates per-host media/aggregator evidence; vetoes; submits candidates to backend. **C (backend + admin):** `blocked_host` table + internal/admin endpoints (mirror suggested-sources) + `HostCandidatesView.vue`.

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy / Alembic (backend), Python crawler, Vue 3 + Element Plus (admin), pytest, vitest.

## Global Constraints

- Crawler tests from `crawler/`: `./.venv/Scripts/python.exe -m pytest -q` (baseline **324**).
- Backend tests from `backend/`: `./.venv/Scripts/python.exe -m pytest -q` (needs `docker start mysql-container`; baseline **84**).
- Admin tests from `admin/`: `npm test` (baseline **84**); and `npm run build` must pass (Vitest does not compile scoped Less).
- **Live gate deterministic; learning offline.** No auto-publish: miner output → human approve → only then live.
- **Best-effort:** learned-host fetch / miner never crash a pass (fail → SEED only).
- **Byte-safe default:** empty/unfetched LEARNED ⇒ `is_blocked_host` = SEED only = today's behaviour.
- **Preserve existing automation:** promo-lexicon pipeline (term miner, CLI audit `learn/audit.py`, snowball), auto-category, domain-rating — NOT modified or migrated. Host pipeline is added in parallel. The shared corpus is extended **additively** (existing term miner ignores new keys).
- **Single bare-host function** in crawler attribution/blocklist stays `urlsplit(...).netloc.lower().removeprefix("www.")` as already used in `attribution._host` / `labeler._host` / `blocklist`.
- **Do not fight domain-rating:** the host miner vetoes hosts that are active sources or domain-rating-productive (`protected_hosts`).

---

### Task 1: RawItem article/business schema flags

**Files:**
- Modify: `crawler/crawler/models.py`
- Modify: `crawler/crawler/fetchers/website.py`
- Test: `crawler/tests/test_website_fetcher.py` (append)

**Interfaces:**
- Produces: `RawItem.is_article: bool = False`, `RawItem.has_business_schema: bool = False`;
  WebsiteFetcher sets both on every emitted item (page-level, shared across the page's blocks).

- [ ] **Step 1: Write the failing test**

```python
# append to crawler/tests/test_website_fetcher.py
def test_news_article_schema_sets_is_article(monkeypatch):
    html = ('<html><head>'
            '<script type="application/ld+json">'
            '{"@context":"https://schema.org","@type":"NewsArticle","headline":"Знижки для ветеранів"}'
            '</script></head><body>'
            '<article>Знижка 20% для ветеранів у місті детально розписана тут</article>'
            '</body></html>')
    f = _fetcher_returning(html)   # existing helper in this test module
    items, _ = f.fetch({"id": 1, "url_or_handle": "https://news.example/a"}, None)
    assert items and items[0].is_article is True
    assert items[0].has_business_schema is False


def test_localbusiness_schema_sets_business_not_article(monkeypatch):
    html = ('<html><head>'
            '<script type="application/ld+json">'
            '{"@context":"https://schema.org","@type":"LocalBusiness","name":"Кафе"}'
            '</script></head><body>'
            '<p>Знижка 20% для ветеранів у нас щодня протягом місяця</p>'
            '</body></html>')
    f = _fetcher_returning(html)
    items, _ = f.fetch({"id": 1, "url_or_handle": "https://cafe.example"}, None)
    assert items and items[0].is_article is False
    assert items[0].has_business_schema is True
```

If `_fetcher_returning(html)` does not already exist in the test module, add this helper near the top of the file (after imports), reusing the module's existing fake-client pattern:

```python
def _fetcher_returning(html):
    import httpx
    from crawler.fetchers.website import WebsiteFetcher
    def handler(request):
        return httpx.Response(200, text=html)
    return WebsiteFetcher(httpx.Client(transport=httpx.MockTransport(handler)))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_website_fetcher.py -q`
Expected: FAIL — `AttributeError: 'RawItem' object has no attribute 'is_article'`.

- [ ] **Step 3: Implement**

In `crawler/crawler/models.py`, add two fields to `RawItem` (after `has_offer_schema`):

```python
    is_article: bool = False
    has_business_schema: bool = False
```

In `crawler/crawler/fetchers/website.py`, add the detectors next to `_has_offer_schema` (after the `_OFFER_TYPE` block):

```python
_ARTICLE_TYPE = re.compile(
    r'"@type"\s*:\s*"[^"]*(?:NewsArticle|BlogPosting|LiveBlogPosting|\bArticle\b)',
    re.IGNORECASE)
# physical-business types only — NOT generic "Organization" (a news site is a
# NewsMediaOrganization, which must not count as a business signal).
_BUSINESS_TYPE = re.compile(
    r'"@type"\s*:\s*"[^"]*(?:LocalBusiness|Store|Restaurant|CafeOrCoffeeShop)',
    re.IGNORECASE)


def _has_article_schema(tree) -> bool:
    for node in tree.css('script[type="application/ld+json"]'):
        if _ARTICLE_TYPE.search(node.text() or ""):
            return True
    return False


def _has_business_schema(tree) -> bool:
    for node in tree.css('script[type="application/ld+json"]'):
        if _BUSINESS_TYPE.search(node.text() or ""):
            return True
    return False
```

In `WebsiteFetcher.fetch`, compute once per page (next to `has_offer = _has_offer_schema(tree)`):

```python
            is_article = _has_article_schema(tree)
            has_business = _has_business_schema(tree)
```

and set them on the constructed `RawItem(...)` (add the two kwargs alongside `has_offer_schema=has_offer`):

```python
                                     has_offer_schema=has_offer,
                                     is_article=is_article,
                                     has_business_schema=has_business))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_website_fetcher.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/models.py crawler/crawler/fetchers/website.py crawler/tests/test_website_fetcher.py
git commit -m "feat(crawler): detect article/business schema.org type on RawItem"
```

---

### Task 2: Attribution — article/aggregator veto + outbound salvage

**Files:**
- Modify: `crawler/crawler/discovery/attribution.py`
- Test: `crawler/tests/test_attribution.py` (append)

**Interfaces:**
- Consumes: `RawItem.is_article`/`has_business_schema` (Task 1); `is_blocked_host` (unchanged here).
- Produces: `PageCtx.outbound_host_count: int`; `build_page_ctx` computes it;
  `attribute(item, ctx, aggregator_min_outbound=3)` — media/aggregator pages are never
  first-party and salvage via a clean outbound business link, else return None; non-media pages
  keep the exact prior order.

- [ ] **Step 1: Write the failing test**

```python
# append to crawler/tests/test_attribution.py
from crawler.models import RawItem, SourceCandidate
from crawler.discovery.attribution import attribute, build_page_ctx, PageCtx


def _ctx(host="cafe.example", brand="Cafe", blocks=1, outbound=0):
    return PageCtx(cand_type="website", cand_name=brand,
                   cand_url_or_handle=f"https://{host}", brand=brand, host=host,
                   offer_block_count=blocks, outbound_host_count=outbound)


def _item(text, url="https://cafe.example/p", links=None, is_article=False, business=False):
    return RawItem(source_id=None, platform="website", key="k", text=text, url=url,
                   links=links or [], is_article=is_article, has_business_schema=business)


def test_article_page_never_first_party_drops_without_outbound():
    it = _item("Ми зібрали знижки для ветеранів", is_article=True)
    assert attribute(it, _ctx(host="blog.example", brand="Blog")) is None


def test_article_page_salvages_via_outbound_business_link():
    it = _item("Знижка 20% для ветеранів", links=["https://realshop.ua/sale"], is_article=True)
    attr = attribute(it, _ctx(host="blog.example", brand="Blog"))
    assert attr is not None and attr.is_first_party is False
    assert attr.provider == "realshop.ua"


def test_business_landing_with_blogposting_and_business_schema_stays_first_party():
    it = _item("Ми даємо знижку 20% для ветеранів", is_article=True, business=True)
    attr = attribute(it, _ctx(host="cafe.example", brand="Cafe"))
    assert attr is not None and attr.is_first_party is True


def test_aggregator_many_outbound_never_first_party():
    it = _item("Ми зібрали знижки для ветеранів", links=["https://realshop.ua/sale"])
    attr = attribute(it, _ctx(host="portal.example", brand="Portal", outbound=5))
    assert attr is not None and attr.is_first_party is False and attr.provider == "realshop.ua"


def test_non_media_first_person_still_first_party():
    it = _item("У нас знижка 20% для ветеранів", links=["https://ig.example/x"])
    attr = attribute(it, _ctx())
    assert attr is not None and attr.is_first_party is True   # outbound must NOT win here
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_attribution.py -q`
Expected: FAIL — `PageCtx.__init__() missing 'outbound_host_count'` / behaviour mismatches.

- [ ] **Step 3: Implement**

In `crawler/crawler/discovery/attribution.py`:

Add `outbound_host_count` to `PageCtx` (after `offer_block_count`):

```python
    outbound_host_count: int = 0
```

Add an outbound-host counter and use it in `build_page_ctx`. Replace `build_page_ctx` with:

```python
def _outbound_hosts(passing_items) -> set[str]:
    hosts = set()
    for it in passing_items:
        src_host = _host(getattr(it, "url", None) or "")
        for raw in getattr(it, "links", None) or []:
            h = _host(raw)
            if h and h != src_host and not is_blocked_host(h):
                hosts.add(h)
    return hosts


def build_page_ctx(cand, passing_items) -> PageCtx:
    brand = next((it.site_name for it in passing_items
                  if getattr(it, "site_name", None)), None)
    host = next((_host(it.url) for it in passing_items if it.url), None)
    return PageCtx(
        cand_type=cand.type, cand_name=cand.name, cand_url_or_handle=cand.url_or_handle,
        brand=brand, host=host, offer_block_count=len(passing_items),
        outbound_host_count=len(_outbound_hosts(passing_items)),
    )
```

Replace the website branch of `attribute` (everything after the telegram block) with:

```python
    # --- website ---
    is_media = (
        is_blocked_host(ctx.host)
        or (getattr(item, "is_article", False)
            and not getattr(item, "has_business_schema", False))
        or ctx.outbound_host_count >= aggregator_min_outbound
    )
    ext = _pick_target(getattr(item, "links", None), item.url or "")
    clean_ext = ext if (ext and not is_blocked_host(_host(ext))) else None

    if is_media:
        # media/aggregator page is never a provider — salvage via outbound, else drop
        if clean_ext:
            host = _host(clean_ext) or clean_ext
            return Attribution(provider=host, is_first_party=False,
                               suggest_type="website", suggest_url_or_handle=_origin(clean_ext),
                               suggest_name=host)
        return None

    low = (item.text or "").lower()
    # 1. first-party via first-person marker (wins over an outbound link)
    if _FIRST_PERSON.search(low) and ctx.brand:
        return _first_party(ctx)
    # 2. third-party via an external business link
    if clean_ext:
        host = _host(clean_ext) or clean_ext
        return Attribution(provider=host, is_first_party=False,
                           suggest_type="website", suggest_url_or_handle=_origin(clean_ext),
                           suggest_name=host)
    # 3. first-party via a single-business page
    if ctx.offer_block_count <= 1 and ctx.brand:
        return _first_party(ctx)
    # 4. generic info -> no attributable provider
    return None
```

Change the `attribute` signature to accept the threshold:

```python
def attribute(item, ctx: PageCtx, aggregator_min_outbound: int = 3) -> Attribution | None:
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_attribution.py -q`
Expected: PASS (new + existing; existing media-host tests now salvage-or-drop consistently).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/attribution.py crawler/tests/test_attribution.py
git commit -m "feat(crawler): article/aggregator never-first-party + outbound salvage in attribution"
```

---

### Task 3: blocklist LEARNED set + reload_learned

**Files:**
- Modify: `crawler/crawler/discovery/blocklist.py`
- Test: `crawler/tests/test_blocklist.py` (append)

**Interfaces:**
- Produces: module-level LEARNED set; `reload_learned(hosts: list[str] | None) -> None`;
  `is_blocked_host` returns True for SEED or LEARNED. Empty/None ⇒ SEED-only (byte-safe).

- [ ] **Step 1: Write the failing test**

```python
# append to crawler/tests/test_blocklist.py
from crawler.discovery import blocklist


def test_reload_learned_extends_then_clears():
    assert blocklist.is_blocked_host("randomshop.ua") is False
    blocklist.reload_learned(["randomshop.ua", "www.other.ua"])
    try:
        assert blocklist.is_blocked_host("randomshop.ua") is True
        assert blocklist.is_blocked_host("other.ua") is True          # www-normalised
        assert blocklist.is_blocked_host("sub.randomshop.ua") is True  # subdomain suffix
    finally:
        blocklist.reload_learned(None)
    assert blocklist.is_blocked_host("randomshop.ua") is False        # cleared → SEED only


def test_reload_learned_none_is_seed_only():
    blocklist.reload_learned(None)
    assert blocklist.is_blocked_host("nv.ua") is True                 # SEED intact
    assert blocklist.is_blocked_host("randomshop.ua") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_blocklist.py -q`
Expected: FAIL — `module 'crawler.discovery.blocklist' has no attribute 'reload_learned'`.

- [ ] **Step 3: Implement**

In `crawler/crawler/discovery/blocklist.py`, add after `_BLOCKED = _MEDIA | _STOCK | _SOCIAL`:

```python
_LEARNED: frozenset[str] = frozenset()


def reload_learned(hosts) -> None:
    """Replace the learned media/aggregator host set (approved via the Vue audit).
    None/empty ⇒ SEED-only, byte-equivalent to prior behaviour."""
    global _LEARNED
    if not hosts:
        _LEARNED = frozenset()
        return
    norm = {h.strip().lower().removeprefix("www.") for h in hosts if h and h.strip()}
    _LEARNED = frozenset(n for n in norm if n)
```

Extend `is_blocked_host` — replace its final `return` line with a check that also consults LEARNED:

```python
    if host == "gov.ua" or host.endswith(".gov.ua"):
        return True
    if any(host == d or host.endswith("." + d) for d in _BLOCKED):
        return True
    return any(host == d or host.endswith("." + d) for d in _LEARNED)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_blocklist.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/blocklist.py crawler/tests/test_blocklist.py
git commit -m "feat(crawler): learned media/aggregator host set + reload_learned"
```

---

### Task 4: Corpus row — additive is_article + outbound_hosts

**Files:**
- Modify: `crawler/crawler/learn/labeler.py`
- Modify: `crawler/crawler/learn/corpus.py`
- Test: `crawler/tests/test_corpus.py` (append), `crawler/tests/test_labeler.py` (append)

**Interfaces:**
- Produces: `LabelRecord.is_article: bool`; corpus JSONL row gains `is_article` (bool) and
  `outbound_hosts` (int). Existing keys unchanged; term miner ignores the new keys.

- [ ] **Step 1: Write the failing test**

```python
# append to crawler/tests/test_labeler.py
from crawler.learn.labeler import label_item
from crawler.models import RawItem


def test_label_carries_is_article():
    it = RawItem(source_id=None, platform="website", key="k",
                 text="Знижка", url="https://blog.example/a", is_article=True)
    rec = label_item(it, extracted_is_offer=False)
    assert rec.is_article is True
```

```python
# append to crawler/tests/test_corpus.py
import json

from crawler.learn.corpus import CorpusRecorder, read_corpus
from crawler.models import RawItem


def test_corpus_row_has_article_and_outbound(tmp_path):
    p = str(tmp_path / "c.jsonl")
    it = RawItem(source_id=None, platform="website", key="k", text="Знижка 20%",
                 url="https://blog.example/a", links=["https://shop.ua/x", "https://blog.example/y"],
                 is_article=True)
    CorpusRecorder(p, max_mb=50).record(it, extracted_is_offer=True)
    rows = read_corpus(p)
    assert rows[0]["is_article"] is True
    assert rows[0]["outbound_hosts"] == 1        # shop.ua external; blog.example internal
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_labeler.py tests/test_corpus.py -q`
Expected: FAIL — `LabelRecord` has no `is_article` / row missing keys.

- [ ] **Step 3: Implement**

In `crawler/crawler/learn/labeler.py`, add `is_article` to `LabelRecord` (after `pos_anchor`):

```python
    is_article: bool = False
```

and set it in `label_item`'s returned record:

```python
        pos_anchor=bool(getattr(item, "has_offer_schema", False)),
        is_article=bool(getattr(item, "is_article", False)),
```

In `crawler/crawler/learn/corpus.py`, add an outbound-host counter and two row fields. Add at module level:

```python
from urllib.parse import urlsplit


def _outbound_count(item) -> int:
    src = urlsplit(getattr(item, "url", None) or "").netloc.lower().removeprefix("www.")
    hosts = set()
    for raw in getattr(item, "links", None) or []:
        h = urlsplit(raw or "").netloc.lower().removeprefix("www.")
        if h and h != src:
            hosts.add(h)
    return len(hosts)
```

In `CorpusRecorder.record`, extend the `row` dict (add the two keys before `"snowball"`):

```python
            "is_article": rec.is_article, "outbound_hosts": _outbound_count(item),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_labeler.py tests/test_corpus.py tests/test_miner.py -q`
Expected: PASS (term miner tests still green — new keys ignored).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/learn/labeler.py crawler/crawler/learn/corpus.py crawler/tests/test_labeler.py crawler/tests/test_corpus.py
git commit -m "feat(crawler): corpus records is_article + outbound_hosts (additive)"
```

---

### Task 5: Backend — BlockedHost model + enum + migration

**Files:**
- Modify: `backend/app/models/enums.py`
- Create: `backend/app/models/blocked_host.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/<newrev>_blocked_hosts.py`
- Test: `backend/tests/test_blocked_hosts.py` (create)

**Interfaces:**
- Produces: `BlockedHostStatus` enum (pending/approved/rejected); `BlockedHost` ORM model
  (`id, host unique, status, media_ratio, aggregator_ratio, support, sample_urls JSON,
  reviewed_by, created_at, reviewed_at`).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_blocked_hosts.py
from app.models import BlockedHost
from app.models.enums import BlockedHostStatus


def test_blocked_host_model_defaults(db_session):
    obj = BlockedHost(host="nv.example", media_ratio=0.9, aggregator_ratio=0.1, support=4)
    db_session.add(obj)
    db_session.commit()
    db_session.refresh(obj)
    assert obj.id is not None
    assert obj.status == BlockedHostStatus.pending
    assert obj.created_at is not None
```

(Use the same `db_session` fixture the other backend tests use — check `backend/tests/conftest.py`.)

- [ ] **Step 2: Run tests to verify they fail**

Run (needs DB): `docker start mysql-container` then from `backend/`
`./.venv/Scripts/python.exe -m pytest tests/test_blocked_hosts.py -q`
Expected: FAIL — cannot import `BlockedHost`.

- [ ] **Step 3: Implement**

In `backend/app/models/enums.py`, add:

```python
class BlockedHostStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
```

Create `backend/app/models/blocked_host.py`:

```python
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.enums import BlockedHostStatus


class BlockedHost(Base):
    __tablename__ = "blocked_hosts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    host: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    status: Mapped[BlockedHostStatus] = mapped_column(
        Enum(BlockedHostStatus), default=BlockedHostStatus.pending, nullable=False)
    media_ratio: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    aggregator_ratio: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    support: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sample_urls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

In `backend/app/models/__init__.py`, add `BlockedHost` to the imports and `__all__` (mirror how `Source`/`SuggestedSource` are exported).

Create the migration. First find the current head: from `backend/` run
`./.venv/Scripts/python.exe -m alembic heads`. Use that revision as `down_revision`.
Create `backend/alembic/versions/<newrev>_blocked_hosts.py`:

```python
"""blocked_hosts

Revision ID: <newrev>
Revises: <current_head>
"""
import sqlalchemy as sa
from alembic import op

revision = "<newrev>"
down_revision = "<current_head>"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "blocked_hosts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("status", sa.Enum("pending", "approved", "rejected",
                                    name="blockedhoststatus"), nullable=False),
        sa.Column("media_ratio", sa.Float(), nullable=False),
        sa.Column("aggregator_ratio", sa.Float(), nullable=False),
        sa.Column("support", sa.Integer(), nullable=False),
        sa.Column("sample_urls", sa.JSON(), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("host", name="uq_blocked_hosts_host"),
    )


def downgrade():
    op.drop_table("blocked_hosts")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_blocked_hosts.py -q`
Expected: PASS. (The test DB is created from models by the fixture; if the suite runs Alembic, also run `./.venv/Scripts/python.exe -m alembic upgrade head` to confirm the migration applies.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/enums.py backend/app/models/blocked_host.py backend/app/models/__init__.py backend/alembic/versions backend/tests/test_blocked_hosts.py
git commit -m "feat(backend): BlockedHost model + status enum + migration"
```

---

### Task 6: Backend — BlockedHost schema + crud

**Files:**
- Create: `backend/app/schemas/blocked_host.py`
- Create: `backend/app/crud/blocked_host.py`
- Test: `backend/tests/test_blocked_hosts.py` (append)

**Interfaces:**
- Produces:
  - `HostCandidateCreate` (host, media_ratio, aggregator_ratio, support, sample_urls),
    `BlockedHostOut` (from_attributes).
  - crud: `upsert_candidate(db, data) -> BlockedHost` (idempotent on host: updates signals if
    still pending; leaves approved/rejected untouched), `list_hosts(db, status=None)`,
    `approve(db, id, reviewed_by)`, `reject(db, id, reviewed_by)`,
    `list_approved_hosts(db) -> list[str]`.

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_blocked_hosts.py
from app.crud import blocked_host as bh_crud
from app.schemas.blocked_host import HostCandidateCreate


def _cand(host="nv.example"):
    return HostCandidateCreate(host=host, media_ratio=0.9, aggregator_ratio=0.1,
                               support=4, sample_urls=["https://nv.example/a"])


def test_upsert_is_idempotent_on_host(db_session):
    a = bh_crud.upsert_candidate(db_session, _cand())
    b = bh_crud.upsert_candidate(db_session, _cand())
    assert a.id == b.id
    assert len(bh_crud.list_hosts(db_session)) == 1


def test_approve_puts_host_in_approved_list(db_session):
    c = bh_crud.upsert_candidate(db_session, _cand("media.example"))
    bh_crud.approve(db_session, c.id, reviewed_by=1)
    assert "media.example" in bh_crud.list_approved_hosts(db_session)


def test_reject_excludes_from_approved(db_session):
    c = bh_crud.upsert_candidate(db_session, _cand("ok.example"))
    bh_crud.reject(db_session, c.id, reviewed_by=1)
    assert "ok.example" not in bh_crud.list_approved_hosts(db_session)
    # re-submitting a rejected host does not resurrect it to pending
    bh_crud.upsert_candidate(db_session, _cand("ok.example"))
    assert bh_crud.get(db_session, c.id).status.value == "rejected"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_blocked_hosts.py -q`
Expected: FAIL — cannot import schema/crud.

- [ ] **Step 3: Implement**

Create `backend/app/schemas/blocked_host.py`:

```python
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import BlockedHostStatus


class HostCandidateCreate(BaseModel):
    host: str
    media_ratio: float = 0.0
    aggregator_ratio: float = 0.0
    support: int = 0
    sample_urls: list[str] | None = None


class BlockedHostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    host: str
    status: BlockedHostStatus
    media_ratio: float
    aggregator_ratio: float
    support: int
    sample_urls: list[str] | None
    reviewed_at: datetime | None
    created_at: datetime
```

Create `backend/app/crud/blocked_host.py`:

```python
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.errors import not_found
from app.models import BlockedHost
from app.models.enums import BlockedHostStatus
from app.schemas.blocked_host import HostCandidateCreate


def upsert_candidate(db: Session, data: HostCandidateCreate) -> BlockedHost:
    host = data.host.strip().lower().removeprefix("www.")
    obj = db.query(BlockedHost).filter(BlockedHost.host == host).first()
    if obj is not None:
        if obj.status == BlockedHostStatus.pending:   # refresh signals while pending
            obj.media_ratio = data.media_ratio
            obj.aggregator_ratio = data.aggregator_ratio
            obj.support = data.support
            obj.sample_urls = data.sample_urls
            db.commit()
            db.refresh(obj)
        return obj                                    # approved/rejected untouched
    obj = BlockedHost(host=host, media_ratio=data.media_ratio,
                      aggregator_ratio=data.aggregator_ratio, support=data.support,
                      sample_urls=data.sample_urls, status=BlockedHostStatus.pending)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get(db: Session, host_id: int) -> BlockedHost:
    obj = db.get(BlockedHost, host_id)
    if obj is None:
        raise not_found(f"BlockedHost {host_id} not found")
    return obj


def list_hosts(db: Session, status: BlockedHostStatus | None = None):
    q = db.query(BlockedHost)
    if status is not None:
        q = q.filter(BlockedHost.status == status)
    return q.order_by(BlockedHost.created_at.desc()).all()


def _review(db: Session, host_id: int, status: BlockedHostStatus, reviewed_by: int) -> BlockedHost:
    obj = get(db, host_id)
    obj.status = status
    obj.reviewed_by = reviewed_by
    obj.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(obj)
    return obj


def approve(db: Session, host_id: int, reviewed_by: int) -> BlockedHost:
    return _review(db, host_id, BlockedHostStatus.approved, reviewed_by)


def reject(db: Session, host_id: int, reviewed_by: int) -> BlockedHost:
    return _review(db, host_id, BlockedHostStatus.rejected, reviewed_by)


def list_approved_hosts(db: Session) -> list[str]:
    rows = (db.query(BlockedHost)
            .filter(BlockedHost.status == BlockedHostStatus.approved).all())
    return [r.host for r in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_blocked_hosts.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/blocked_host.py backend/app/crud/blocked_host.py backend/tests/test_blocked_hosts.py
git commit -m "feat(backend): BlockedHost schema + crud (idempotent upsert, approve/reject)"
```

---

### Task 7: Backend — internal endpoints (submit candidate, list approved)

**Files:**
- Modify: `backend/app/routers/internal.py`
- Test: `backend/tests/test_internal.py` (append)

**Interfaces:**
- Produces: `POST /api/internal/host-candidates` (body `HostCandidateCreate` → `BlockedHostOut`);
  `GET /api/internal/blocked-hosts` → `list[str]` (approved hosts). Both under existing X-API-Key.

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_internal.py
def test_submit_host_candidate_and_list_approved(client, db_session, api_headers):
    r = client.post("/api/internal/host-candidates",
                    json={"host": "media.example", "media_ratio": 0.9,
                          "aggregator_ratio": 0.0, "support": 4,
                          "sample_urls": ["https://media.example/a"]},
                    headers=api_headers)
    assert r.status_code == 200 and r.json()["status"] == "pending"
    # not approved yet → not in the crawler-facing list
    assert client.get("/api/internal/blocked-hosts", headers=api_headers).json() == []


def test_host_candidates_requires_api_key(client):
    r = client.post("/api/internal/host-candidates", json={"host": "x.example"})
    assert r.status_code == 401
```

(Use whatever `client` / `api_headers` fixtures `test_internal.py` already uses.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_internal.py -q`
Expected: FAIL — 404 for the new routes.

- [ ] **Step 3: Implement**

In `backend/app/routers/internal.py`, add imports:

```python
from app.crud import blocked_host as blocked_host_crud
from app.schemas.blocked_host import BlockedHostOut, HostCandidateCreate
```

Add the routes (anywhere among the internal routes):

```python
@router.post("/host-candidates", response_model=BlockedHostOut)
def submit_host_candidate(data: HostCandidateCreate, db: Session = Depends(get_db)):
    return blocked_host_crud.upsert_candidate(db, data)


@router.get("/blocked-hosts", response_model=list[str])
def list_blocked_hosts(db: Session = Depends(get_db)):
    return blocked_host_crud.list_approved_hosts(db)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_internal.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/internal.py backend/tests/test_internal.py
git commit -m "feat(backend): internal host-candidate submit + approved blocked-hosts list"
```

---

### Task 8: Backend — admin endpoints (list/approve/reject)

**Files:**
- Modify: `backend/app/routers/admin.py`
- Test: `backend/tests/test_offers_admin.py` (append) or a new `backend/tests/test_blocked_hosts_admin.py`

**Interfaces:**
- Produces: `GET /api/admin/host-candidates?status=` → `list[BlockedHostOut]`;
  `POST /api/admin/host-candidates/{id}/approve` → `BlockedHostOut`;
  `POST /api/admin/host-candidates/{id}/reject` → `BlockedHostOut`. All under `get_current_admin`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_blocked_hosts_admin.py
from app.crud import blocked_host as bh_crud
from app.schemas.blocked_host import HostCandidateCreate


def test_admin_lists_and_approves(client, db_session, admin_headers):
    c = bh_crud.upsert_candidate(db_session, HostCandidateCreate(host="media.example", support=4))
    lst = client.get("/api/admin/host-candidates?status=pending", headers=admin_headers)
    assert lst.status_code == 200 and any(r["host"] == "media.example" for r in lst.json())
    ap = client.post(f"/api/admin/host-candidates/{c.id}/approve", headers=admin_headers)
    assert ap.status_code == 200 and ap.json()["status"] == "approved"


def test_admin_requires_auth(client, db_session):
    c = bh_crud.upsert_candidate(db_session, HostCandidateCreate(host="x.example"))
    assert client.post(f"/api/admin/host-candidates/{c.id}/reject").status_code == 401
```

(Use the `admin_headers` fixture the other admin tests use.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_blocked_hosts_admin.py -q`
Expected: FAIL — routes 404.

- [ ] **Step 3: Implement**

In `backend/app/routers/admin.py`, add imports:

```python
from app.crud import blocked_host as blocked_host_crud
from app.models.enums import BlockedHostStatus
from app.schemas.blocked_host import BlockedHostOut
```

Add the routes (near the suggested-sources block):

```python
@router.get("/host-candidates", response_model=list[BlockedHostOut])
def list_host_candidates(status: BlockedHostStatus | None = None,
                         db: Session = Depends(get_db), _=Depends(get_current_admin)):
    return blocked_host_crud.list_hosts(db, status)


@router.post("/host-candidates/{host_id}/approve", response_model=BlockedHostOut)
def approve_host_candidate(host_id: int, db: Session = Depends(get_db),
                           admin=Depends(get_current_admin)):
    return blocked_host_crud.approve(db, host_id, admin.id)


@router.post("/host-candidates/{host_id}/reject", response_model=BlockedHostOut)
def reject_host_candidate(host_id: int, db: Session = Depends(get_db),
                          admin=Depends(get_current_admin)):
    return blocked_host_crud.reject(db, host_id, admin.id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_blocked_hosts_admin.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/admin.py backend/tests/test_blocked_hosts_admin.py
git commit -m "feat(backend): admin host-candidate list/approve/reject"
```

---

### Task 9: Crawler — host_miner (per-host aggregation + contrast)

**Files:**
- Create: `crawler/crawler/learn/host_miner.py`
- Test: `crawler/tests/test_host_miner.py`

**Interfaces:**
- Consumes: corpus rows (Task 4 shape: `host`, `label`, `is_article`, `outbound_hosts`,
  `neg_anchor`, `pos_anchor`).
- Produces: `HostScore(host, media_ratio, aggregator_ratio, support, sample_urls, provider_evidence)`;
  `mine_hosts(rows, aggregator_min_outbound=3) -> list[HostScore]` sorted deterministically
  `(-media_ratio-aggregator_ratio, host)`.

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_host_miner.py
from crawler.learn.host_miner import mine_hosts


def _row(host, is_article=False, outbound=0, pos=False, url="u"):
    return {"host": host, "label": "pass", "is_article": is_article,
            "outbound_hosts": outbound, "neg_anchor": False, "pos_anchor": pos, "text": url}


def test_article_heavy_host_scores_high_media():
    rows = [_row("blog.ua", is_article=True) for _ in range(4)]
    scores = {s.host: s for s in mine_hosts(rows)}
    assert scores["blog.ua"].media_ratio == 1.0
    assert scores["blog.ua"].support == 4
    assert scores["blog.ua"].provider_evidence is False


def test_aggregator_host_scores_high_aggregator():
    rows = [_row("portal.ua", outbound=5) for _ in range(3)]
    s = {x.host: x for x in mine_hosts(rows)}["portal.ua"]
    assert s.aggregator_ratio == 1.0


def test_provider_like_host_has_evidence_and_low_ratios():
    rows = [_row("shop.ua", pos=True, outbound=0) for _ in range(3)]
    s = {x.host: x for x in mine_hosts(rows)}["shop.ua"]
    assert s.provider_evidence is True
    assert s.media_ratio == 0.0 and s.aggregator_ratio == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_host_miner.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `crawler/crawler/learn/host_miner.py`:

```python
"""Офлайн per-host агрегація корпусу: оцінити, наскільки host поводиться як
медіа/агрегатор (article-частка, outbound-spread) проти provider-evidence
(Offer-schema / single-business). Детерміновано; вихід → аудит-черга backend."""

from dataclasses import dataclass, field


@dataclass
class HostScore:
    host: str
    media_ratio: float
    aggregator_ratio: float
    support: int
    provider_evidence: bool
    sample_urls: list = field(default_factory=list)


def mine_hosts(rows, aggregator_min_outbound: int = 3) -> list[HostScore]:
    agg: dict[str, dict] = {}
    for r in rows:
        host = (r.get("host") or "").strip().lower()
        if not host:
            continue
        a = agg.setdefault(host, {"n": 0, "article": 0, "aggr": 0, "provider": 0, "samples": []})
        a["n"] += 1
        if r.get("is_article"):
            a["article"] += 1
        if int(r.get("outbound_hosts", 0)) >= aggregator_min_outbound:
            a["aggr"] += 1
        if r.get("pos_anchor") and int(r.get("outbound_hosts", 0)) == 0:
            a["provider"] += 1
        if len(a["samples"]) < 3 and r.get("text"):
            a["samples"].append(r["text"])
    out = []
    for host, a in agg.items():
        n = a["n"]
        out.append(HostScore(
            host=host,
            media_ratio=a["article"] / n,
            aggregator_ratio=a["aggr"] / n,
            support=n,
            provider_evidence=a["provider"] > 0,
            sample_urls=list(a["samples"]),
        ))
    out.sort(key=lambda s: (-(s.media_ratio + s.aggregator_ratio), s.host))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_host_miner.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/learn/host_miner.py crawler/tests/test_host_miner.py
git commit -m "feat(crawler): host_miner per-host media/aggregator aggregation"
```

---

### Task 10: Crawler — host_vetoes

**Files:**
- Create: `crawler/crawler/learn/host_vetoes.py`
- Test: `crawler/tests/test_host_vetoes.py`

**Interfaces:**
- Consumes: `HostScore` (Task 9); `is_blocked_host` (SEED/LEARNED).
- Produces: `survivors(scores, *, protected_hosts, min_support=3, media_min=0.5,
  aggregator_min=0.5, max_candidates=50) -> list[HostScore]` — keep hosts with
  `support>=min_support`, `(media_ratio>=media_min or aggregator_ratio>=aggregator_min)`,
  NOT `provider_evidence`, NOT in `protected_hosts`, NOT already `is_blocked_host`.

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_host_vetoes.py
from crawler.learn.host_miner import HostScore
from crawler.learn.host_vetoes import survivors


def _s(host, media=0.9, aggr=0.0, support=4, provider=False):
    return HostScore(host=host, media_ratio=media, aggregator_ratio=aggr,
                     support=support, provider_evidence=provider)


def test_keeps_media_host():
    assert [s.host for s in survivors([_s("blog.ua")], protected_hosts=set())] == ["blog.ua"]


def test_vetoes_low_support_and_provider_and_protected():
    scores = [_s("a.ua", support=1), _s("b.ua", provider=True),
              _s("c.ua"), _s("d.ua", media=0.1, aggr=0.1)]
    keep = survivors(scores, protected_hosts={"c.ua"})
    assert [s.host for s in keep] == []          # a low-support, b provider, c protected, d below thresholds


def test_vetoes_already_blocked(monkeypatch):
    import crawler.learn.host_vetoes as hv
    monkeypatch.setattr(hv, "is_blocked_host", lambda h: h == "nv.ua")
    assert [s.host for s in survivors([_s("nv.ua"), _s("new.ua")], protected_hosts=set())] == ["new.ua"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_host_vetoes.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `crawler/crawler/learn/host_vetoes.py`:

```python
"""Запобіжники перед аудит-чергою host-кандидатів: мін support; must look media/aggregator;
не provider-evidence; не protected (активні sources / domain-rating-productive); не вже-blocked."""

from crawler.discovery.blocklist import is_blocked_host


def survivors(scores, *, protected_hosts, min_support: int = 3, media_min: float = 0.5,
              aggregator_min: float = 0.5, max_candidates: int = 50):
    protected = {h.strip().lower().removeprefix("www.") for h in (protected_hosts or set())}
    out = []
    for s in scores:
        if s.support < min_support:
            continue
        if s.provider_evidence:
            continue
        if s.media_ratio < media_min and s.aggregator_ratio < aggregator_min:
            continue
        if s.host in protected or is_blocked_host(s.host):
            continue
        out.append(s)
        if len(out) >= max_candidates:
            break
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_host_vetoes.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/learn/host_vetoes.py crawler/tests/test_host_vetoes.py
git commit -m "feat(crawler): host_vetoes (support/provider/protected/already-blocked)"
```

---

### Task 11: Crawler — run_host_miner orchestrator + api_client.submit_host_candidate

**Files:**
- Modify: `crawler/crawler/api_client.py`
- Create: `crawler/crawler/learn/run_host_miner.py`
- Test: `crawler/tests/test_run_host_miner.py`

**Interfaces:**
- Consumes: `read_corpus`, `mine_hosts`, `survivors`, `ApiClient.submit_host_candidate`.
- Produces: `ApiClient.submit_host_candidate(payload: dict) -> dict`;
  `run_host_miner(config, api, protected_hosts) -> int` (mines → vetoes → submits each survivor;
  returns count submitted). `protected_hosts` supplied by caller.

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_run_host_miner.py
from crawler.learn.run_host_miner import run_host_miner


class _Cfg:
    corpus_path = None
    host_miner_min_support = 3
    host_miner_media_min = 0.5
    host_miner_aggregator_min = 0.5
    aggregator_min_outbound = 3
    host_miner_max_candidates = 50


class _Api:
    def __init__(self): self.sent = []
    def submit_host_candidate(self, payload): self.sent.append(payload); return {}


def test_run_host_miner_submits_survivors(tmp_path, monkeypatch):
    import crawler.learn.run_host_miner as m
    rows = [{"host": "blog.ua", "label": "pass", "is_article": True,
             "outbound_hosts": 0, "pos_anchor": False, "text": "https://blog.ua/a"}
            for _ in range(4)]
    monkeypatch.setattr(m, "read_corpus", lambda p: rows)
    api = _Api()
    n = run_host_miner(_Cfg(), api, protected_hosts=set())
    assert n == 1
    assert api.sent[0]["host"] == "blog.ua" and api.sent[0]["support"] == 4


def test_run_host_miner_respects_protected(tmp_path, monkeypatch):
    import crawler.learn.run_host_miner as m
    rows = [{"host": "blog.ua", "label": "pass", "is_article": True,
             "outbound_hosts": 0, "pos_anchor": False, "text": "u"} for _ in range(4)]
    monkeypatch.setattr(m, "read_corpus", lambda p: rows)
    api = _Api()
    assert run_host_miner(_Cfg(), api, protected_hosts={"blog.ua"}) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_run_host_miner.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

In `crawler/crawler/api_client.py`, add (in the internal section):

```python
    def submit_host_candidate(self, payload: dict) -> dict:
        r = self._client.post("/api/internal/host-candidates", json=payload)
        r.raise_for_status()
        return r.json()

    def list_blocked_hosts(self) -> list[str]:
        r = self._client.get("/api/internal/blocked-hosts")
        r.raise_for_status()
        return r.json()
```

Create `crawler/crawler/learn/run_host_miner.py`:

```python
"""Офлайн-оркестратор host-blocklist: корпус → host_miner → host_vetoes → сабміт кандидатів
у backend (audit-черга). Дзеркало run_miner.py. protected_hosts подає викликач."""

from crawler.learn.corpus import read_corpus
from crawler.learn.host_miner import mine_hosts
from crawler.learn.host_vetoes import survivors


def run_host_miner(config, api, protected_hosts) -> int:
    rows = read_corpus(config.corpus_path)
    scores = mine_hosts(rows, aggregator_min_outbound=config.aggregator_min_outbound)
    keep = survivors(scores, protected_hosts=protected_hosts,
                     min_support=config.host_miner_min_support,
                     media_min=config.host_miner_media_min,
                     aggregator_min=config.host_miner_aggregator_min,
                     max_candidates=config.host_miner_max_candidates)
    for s in keep:
        api.submit_host_candidate({
            "host": s.host, "media_ratio": s.media_ratio,
            "aggregator_ratio": s.aggregator_ratio, "support": s.support,
            "sample_urls": s.sample_urls,
        })
    return len(keep)


if __name__ == "__main__":  # pragma: no cover — CLI entry point
    import logging

    from crawler.api_client import ApiClient
    from crawler.config import load_config

    logging.basicConfig(level=logging.INFO)
    cfg = load_config()
    with ApiClient(cfg.internal_api_url, cfg.crawler_api_key, cfg.request_timeout) as api:
        protected = {s["url_or_handle"] for s in api.list_sources(is_active=True)}
        n = run_host_miner(cfg, api, protected)
    print(f"host candidates submitted: {n}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_run_host_miner.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/api_client.py crawler/crawler/learn/run_host_miner.py crawler/tests/test_run_host_miner.py
git commit -m "feat(crawler): run_host_miner orchestrator + submit_host_candidate client"
```

---

### Task 12: Crawler — wiring fetch+reload_learned + config knobs

**Files:**
- Modify: `crawler/crawler/config.py`
- Modify: `crawler/crawler/wiring.py`
- Test: `crawler/tests/test_config.py` (append), `crawler/tests/test_wiring.py` (append)

**Interfaces:**
- Produces: config knobs `attribution_hardening_enabled=True`, `blocked_hosts_fetch_enabled=True`,
  `aggregator_min_outbound=3`, `host_miner_min_support=3`, `host_miner_media_min=0.5`,
  `host_miner_aggregator_min=0.5`, `host_miner_max_candidates=50`. `build_runner` fetches approved
  blocked-hosts once and calls `blocklist.reload_learned(...)` (best-effort) when
  `blocked_hosts_fetch_enabled`.

- [ ] **Step 1: Write the failing test**

```python
# append to crawler/tests/test_config.py
def test_attribution_hardening_defaults():
    from crawler.config import _RawSettings
    s = _RawSettings()
    assert s.attribution_hardening_enabled is True
    assert s.blocked_hosts_fetch_enabled is True
    assert s.aggregator_min_outbound == 3
    assert s.host_miner_min_support == 3
    assert s.host_miner_media_min == 0.5
    assert s.host_miner_aggregator_min == 0.5
    assert s.host_miner_max_candidates == 50
```

```python
# append to crawler/tests/test_wiring.py
def test_build_runner_reloads_blocked_hosts(monkeypatch, tmp_path):
    import crawler.wiring as w
    from crawler.discovery import blocklist
    captured = {}
    monkeypatch.setattr(blocklist, "reload_learned",
                        lambda hosts: captured.setdefault("hosts", hosts))
    # make ApiClient.list_blocked_hosts return a fixed set without network
    monkeypatch.setattr(w.ApiClient, "list_blocked_hosts",
                        lambda self: ["learned.example"], raising=False)
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=False, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={},
        brand_feed_enabled=False, sitemap_depth_enabled=False, domain_rating_enabled=False,
        blocked_hosts_fetch_enabled=True,
    )
    w.build_runner(cfg)
    assert captured["hosts"] == ["learned.example"]


def test_build_runner_blocked_hosts_fetch_best_effort(monkeypatch):
    import crawler.wiring as w
    def boom(self): raise RuntimeError("net down")
    monkeypatch.setattr(w.ApiClient, "list_blocked_hosts", boom, raising=False)
    cfg = Config(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=False, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={},
        brand_feed_enabled=False, sitemap_depth_enabled=False, domain_rating_enabled=False,
        blocked_hosts_fetch_enabled=True,
    )
    w.build_runner(cfg)   # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_config.py tests/test_wiring.py -q`
Expected: FAIL — unknown settings / reload not called.

- [ ] **Step 3: Implement**

In `crawler/crawler/config.py`, add the 7 fields to `_RawSettings`, the `Config` dataclass, and the
`load_config()` construction (all three spots, mirroring the existing knobs):

```python
    attribution_hardening_enabled: bool = True
    blocked_hosts_fetch_enabled: bool = True
    aggregator_min_outbound: int = 3
    host_miner_min_support: int = 3
    host_miner_media_min: float = 0.5
    host_miner_aggregator_min: float = 0.5
    host_miner_max_candidates: int = 50
```

(and the matching `field=s.field,` lines in `load_config`).

In `crawler/crawler/wiring.py`, add import:

```python
from crawler.discovery import blocklist
```

Near the start of `build_runner` (after `api = ApiClient(...)`), add the best-effort fetch:

```python
    if config.blocked_hosts_fetch_enabled:
        try:
            blocklist.reload_learned(api.list_blocked_hosts())
        except Exception as exc:  # noqa: BLE001 — learned-host fetch is best-effort
            log.warning("blocked-hosts fetch failed: %s", exc)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_config.py tests/test_wiring.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/config.py crawler/crawler/wiring.py crawler/tests/test_config.py crawler/tests/test_wiring.py
git commit -m "feat(crawler): fetch approved blocked-hosts into live gate + config knobs"
```

---

### Task 13: Admin — HostCandidatesView + api + route + tests

**Files:**
- Create: `admin/src/api/hostCandidates.js`
- Create: `admin/src/views/HostCandidatesView.vue`
- Modify: `admin/src/router/index.js`
- Modify: `admin/src/constants/enums.js` (reuse SUGGESTION_STATUSES or add HOST_STATUSES)
- Modify: nav (wherever `suggested-sources` link lives, e.g. `AdminLayout.vue`)
- Test: `admin/src/views/__tests__/HostCandidatesView.spec.js` (create; mirror the suggested-sources spec if one exists)

**Interfaces:**
- Produces: a moderation view listing pending host candidates (host + media/aggregator/support +
  sample_urls) with approve/reject, backed by `/admin/host-candidates`.

- [ ] **Step 1: Write the failing test**

```javascript
// admin/src/views/__tests__/HostCandidatesView.spec.js
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import HostCandidatesView from "@/views/HostCandidatesView.vue";
import * as api from "@/api/hostCandidates";

vi.mock("@/api/hostCandidates");

describe("HostCandidatesView", () => {
  beforeEach(() => {
    api.list.mockResolvedValue([
      { id: 1, host: "media.example", status: "pending", media_ratio: 0.9,
        aggregator_ratio: 0.1, support: 4, sample_urls: ["https://media.example/a"] },
    ]);
    api.approve.mockResolvedValue({});
    api.reject.mockResolvedValue({});
  });

  it("loads candidates and approves", async () => {
    const wrapper = mount(HostCandidatesView, {
      global: { stubs: { "el-select": true, "el-option": true, "el-button": true,
                         "el-link": true, ResponsiveTable: true } },
    });
    await flushPromises();
    expect(api.list).toHaveBeenCalled();
    await wrapper.vm.onApprove(1);
    expect(api.approve).toHaveBeenCalledWith(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `admin/`): `npm test -- HostCandidatesView`
Expected: FAIL — view/api missing.

- [ ] **Step 3: Implement**

Create `admin/src/api/hostCandidates.js`:

```javascript
import client from "./client";

export const list = (params) => client.get("/admin/host-candidates", { params }).then((r) => r.data);
export const approve = (id) => client.post(`/admin/host-candidates/${id}/approve`).then((r) => r.data);
export const reject = (id) => client.post(`/admin/host-candidates/${id}/reject`).then((r) => r.data);
```

Create `admin/src/views/HostCandidatesView.vue` (mirror `SuggestedSourcesView.vue`):

```vue
<script setup>
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import * as hosts from "@/api/hostCandidates";
import { extractError } from "@/utils/errors";
import ResponsiveTable from "@/components/ResponsiveTable.vue";

const items = ref([]);
const loading = ref(false);
const status = ref("pending");

const columns = [
  { prop: "host", label: "Хост" },
  { label: "Медіа", slot: "media" },
  { label: "Агрегатор", slot: "aggr" },
  { prop: "support", label: "Support" },
];

async function load() {
  loading.value = true;
  try {
    items.value = await hosts.list({ status: status.value });
  } catch (e) {
    ElMessage.error(extractError(e));
  } finally {
    loading.value = false;
  }
}
onMounted(load);

async function onApprove(id) {
  try {
    await hosts.approve(id);
    ElMessage.success("Заблоковано (додано у медіа/агрегатор-список)");
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}
async function onReject(id) {
  try {
    await hosts.reject(id);
    ElMessage.success("Відхилено");
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

defineExpose({ items, load, onApprove, onReject, status });
</script>

<template>
  <div class="host-candidates-view">
    <div class="header">
      <h2>Кандидати в медіа/агрегатор-блоклист</h2>
      <el-select v-model="status" style="width: 160px" @change="load">
        <el-option label="Очікують" value="pending" />
        <el-option label="Схвалені" value="approved" />
        <el-option label="Відхилені" value="rejected" />
      </el-select>
    </div>

    <ResponsiveTable :columns="columns" :rows="items" :loading="loading" :actions-width="220">
      <template #col-media="{ row }">{{ (row.media_ratio * 100).toFixed(0) }}%</template>
      <template #col-aggr="{ row }">{{ (row.aggregator_ratio * 100).toFixed(0) }}%</template>
      <template #actions="{ row }">
        <template v-if="row.status === 'pending'">
          <el-button size="small" type="success" @click="onApprove(row.id)">Заблокувати</el-button>
          <el-button size="small" type="danger" @click="onReject(row.id)">Відхилити</el-button>
        </template>
        <span v-else>{{ row.status }}</span>
      </template>
    </ResponsiveTable>
  </div>
</template>

<style scoped lang="less">
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
</style>
```

In `admin/src/router/index.js`, import the view and add a route inside the `AdminLayout` children (mirroring the `suggested-sources` entry):

```javascript
import HostCandidatesView from "@/views/HostCandidatesView.vue";
// ...
      { path: "host-candidates", name: "host-candidates", component: HostCandidatesView },
```

Add a nav link next to the "Запропоновані джерела" link (find it in the layout component that renders the menu; mirror its `router-link`/menu item to `{ name: "host-candidates" }`, label "Медіа-блоклист").

- [ ] **Step 4: Run test + build**

Run (from `admin/`): `npm test -- HostCandidatesView` then `npm run build`
Expected: test PASS; build succeeds.

- [ ] **Step 5: Commit**

```bash
git add admin/src/api/hostCandidates.js admin/src/views/HostCandidatesView.vue admin/src/router/index.js admin/src/views/__tests__/HostCandidatesView.spec.js
git commit -m "feat(admin): host-candidate moderation view (media/aggregator blocklist)"
```

---

### Task 14: Docs + full-suite gate

**Files:**
- Modify: `crawler/.env.example`
- Modify: `RUN.md`
- Test: run all three suites.

- [ ] **Step 1: Update `crawler/.env.example`** — append:

```dotenv
# --- Attribution hardening (self-growing media/aggregator host-blocklist) ---
ATTRIBUTION_HARDENING_ENABLED=true
BLOCKED_HOSTS_FETCH_ENABLED=true
AGGREGATOR_MIN_OUTBOUND=3
HOST_MINER_MIN_SUPPORT=3
HOST_MINER_MEDIA_MIN=0.5
HOST_MINER_AGGREGATOR_MIN=0.5
HOST_MINER_MAX_CANDIDATES=50
```

- [ ] **Step 2: Update `RUN.md`** — add a "Блок 6 — Посилення атрибуції (медіа/агрегатор-блоклист)"
section describing: live gate now catches article/aggregator pages structurally + salvages via
outbound; offline `python -m crawler.learn.run_host_miner` submits host candidates; moderator
approves in admin → "Медіа-блоклист" view → crawler fetches approved hosts each pass. Note the
term-audit stays CLI (unchanged); host-audit is the new Vue surface. Keep the style of "Блок 4/5".

- [ ] **Step 3: Run all suites**

```bash
# crawler
cd crawler && ./.venv/Scripts/python.exe -m pytest -q
# backend (needs DB)
docker start mysql-container && cd ../backend && ./.venv/Scripts/python.exe -m pytest -q
# admin
cd ../admin && npm test && npm run build
```
Expected: crawler all green (324 + new), backend all green (84 + new), admin all green (84 + new) + build OK.

- [ ] **Step 4: Commit**

```bash
git add crawler/.env.example RUN.md
git commit -m "docs(crawler): attribution-hardening env knobs + run instructions"
```

---

## Self-Review

**Spec coverage:**
- §3 Layer A → Tasks 1 (schema flags), 2 (attribution veto+salvage), 3 (LEARNED+reload), 12 (fetch into gate).
- §3 Layer B → Tasks 4 (corpus additive), 9 (host_miner), 10 (host_vetoes), 11 (run_host_miner+submit).
- §3 Layer C → Tasks 5 (model/migration), 6 (schema/crud), 7 (internal endpoints), 8 (admin endpoints), 13 (Vue).
- §6 preservation → additive corpus (Task 4, verified by re-running term miner tests), is_blocked_host byte-safe (Task 3), no term-pipeline files touched.
- §7 risks → Task 1/2 business-schema guard for is_article over-block; aggregator counts external hosts only.
- §8 config → Task 12; docs → Task 14. §9 testing → each task + Task 14 gate.
- §2 don't-fight-domain-rating → Task 10/11 `protected_hosts`.

**Placeholder scan:** `<newrev>`/`<current_head>` in Task 5 are intentional — the implementer runs `alembic heads` to fill them. RUN.md prose (Task 14) is documentation. No code placeholders.

**Type consistency:** `HostScore(host, media_ratio, aggregator_ratio, support, provider_evidence, sample_urls)` consistent across Tasks 9/10/11. `HostCandidateCreate`/`BlockedHostOut` consistent across Tasks 6/7/8/11. `reload_learned(hosts)` consistent across Tasks 3/12. `attribute(item, ctx, aggregator_min_outbound=3)` — the harvester calls `attribute(item, ctx)` today (default applies); Task 2 keeps the default so `harvest.py` is untouched.

## Deferred / out of scope (spec §10)
Term-audit migration to Vue; LLM media detection; retroactive purge of already-submitted offers; telegram/IG/FB structural media detection.
