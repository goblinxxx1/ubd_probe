# UX черги модерації (превʼю + confidence + bulk-reject) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Close backlog #10. Give the moderation queue (1) a "Превʼю ↗" that opens the real source page in a new window + compact inline extracted data, (2) a backend-computed **confidence** assist (host reputation + completeness → tier + signal chips) for sort/highlight, and (3) **bulk reject** (no bulk publish). Human always confirms; never auto-publish.

**Architecture:** Backend adds a confidence service (`app/services/confidence.py`), an admin-only `OfferAdminOut(OfferOut)` schema carrying optional `confidence`, and a `POST /admin/offers/bulk-reject` endpoint. Public `OfferOut` untouched. Admin Vue adds inline badges, a preview link, confidence rendering + client-side sort, and row selection + bulk-reject.

**Tech Stack:** FastAPI/SQLAlchemy + pytest (backend, mysql-container:3306); Vue3 + Vitest + `npm run build` (admin). 

## Global Constraints
- Test cmds: backend (from `backend/`) `./.venv/Scripts/python.exe -m pytest -q`; admin (from `admin/`) `npm test` AND `npm run build` (Vitest does NOT compile scoped-Less — always build).
- **Confidence is assist-only** — sort/highlight; publish stays single + human-confirmed. No auto-publish.
- **Bulk = reject only** (reversible soft-trash #12). No bulk publish.
- Do NOT add `confidence` to `OfferOut` (shared with public `public.py:31`). Use `OfferAdminOut(OfferOut)`.
- Preview = `window.open(article_url || site_url, "_blank")` — no iframe.
- Reuse #34 host-history counting (`_offer_host_candidates`, `_host_blocked` in `crud/offer.py`).
- Tier rule: **high** = host published≥1 AND rejected==0 AND has_discount; **low** = (host rejected≥1 AND published==0) OR not has_discount; **medium** = otherwise.

---

### Task 1: Backend — confidence service + schemas

**Files:**
- Create: `backend/app/services/confidence.py`, `backend/tests/test_confidence.py`
- Modify: `backend/app/schemas/offer.py` (add `ConfidenceOut`, `OfferAdminOut`)
- Modify: `backend/app/crud/offer.py` (expose reusable `host_reputation`)

**Interfaces:**
- Produces: `ConfidenceOut{tier:str, host:str, host_published:int, host_rejected:int, signals:list[str]}`; `OfferAdminOut(OfferOut)` adds `confidence: ConfidenceOut | None = None`; `confidence.score_offer(db, offer, memo) -> ConfidenceOut`; `confidence.enrich_pending(db, offers) -> None`; `offer_crud.host_reputation(db, host, memo) -> tuple[int,int]`.

- [ ] **Step 1: Write failing tests** — `backend/tests/test_confidence.py`:
```python
from app.services import confidence
from app.models import Offer
from app.models.enums import CreatedBy, OfferStatus, OfferType


def _mk(db, status, **kw):
    o = Offer(type=OfferType.discount, title=kw.pop("title", "T"), description=kw.pop("description", ""),
              provider=kw.pop("provider", "P"), status=status, created_by=CreatedBy.crawler, **kw)
    db.add(o); db.commit(); db.refresh(o)
    return o


def test_high_tier_proven_host_with_discount(db_session):
    _mk(db_session, OfferStatus.published, site_url="https://good.ua/a")
    o = _mk(db_session, OfferStatus.pending_review, site_url="https://good.ua/b",
            discount_type="percent", discount_value=20)
    c = confidence.score_offer(db_session, o, {})
    assert c.tier == "high"
    assert c.host == "good.ua" and c.host_published == 1 and c.host_rejected == 0
    assert "proven_host" in c.signals


def test_low_tier_noisy_host(db_session):
    _mk(db_session, OfferStatus.rejected, site_url="https://noisy.ua/a")
    o = _mk(db_session, OfferStatus.pending_review, site_url="https://noisy.ua/b",
            discount_type="percent", discount_value=10)
    c = confidence.score_offer(db_session, o, {})
    assert c.tier == "low" and "noisy_host" in c.signals


def test_low_tier_missing_discount(db_session):
    _mk(db_session, OfferStatus.published, site_url="https://good.ua/x")
    o = _mk(db_session, OfferStatus.pending_review, site_url="https://good.ua/y")  # no discount
    c = confidence.score_offer(db_session, o, {})
    assert c.tier == "low" and "no_discount" in c.signals


def test_medium_tier_new_host(db_session):
    o = _mk(db_session, OfferStatus.pending_review, site_url="https://fresh.ua/a",
            discount_type="percent", discount_value=15)
    c = confidence.score_offer(db_session, o, {})
    assert c.tier == "medium" and "new_host" in c.signals


def test_primary_host_falls_back_to_article_url(db_session):
    o = _mk(db_session, OfferStatus.pending_review, site_url=None,
            article_url="https://blog.ua/p", discount_type="percent", discount_value=5)
    assert confidence.score_offer(db_session, o, {}).host == "blog.ua"


def test_completeness_signals(db_session):
    o = _mk(db_session, OfferStatus.pending_review, site_url="https://x.ua/a")
    c = confidence.score_offer(db_session, o, {})
    assert {"no_discount", "no_location", "no_category"} <= set(c.signals)


def test_host_reputation_memo_counts_once(db_session):
    from app.crud.offer import host_reputation
    _mk(db_session, OfferStatus.published, site_url="https://h.ua/a")
    memo = {}
    assert host_reputation(db_session, "h.ua", memo) == (1, 0)
    assert "h.ua" in memo
    assert host_reputation(db_session, "h.ua", memo) == (1, 0)   # served from memo
```

- [ ] **Step 2: Run** `./.venv/Scripts/python.exe -m pytest -q tests/test_confidence.py` → FAIL (module missing).

- [ ] **Step 3: Implement**

In `crud/offer.py`, add reusable reputation (near `_maybe_autoblock_hosts`):
```python
def host_reputation(db: Session, host: str, memo: dict) -> tuple[int, int]:
    """(published, rejected) count of offers whose bare source host matches `host`
    (exact-or-suffix on site_url/article_url/provider). Memoized per call-batch."""
    if host in memo:
        return memo[host]
    pub = rej = 0
    if host:
        like = f"%{host}%"
        rows = (db.query(Offer)
                .filter((Offer.site_url.like(like)) | (Offer.article_url.like(like))
                        | (Offer.provider.like(like))).all())
        for r in rows:
            if not any(_host_blocked(fh, {host}) for fh in _offer_host_candidates(r)):
                continue
            if r.status == OfferStatus.published:
                pub += 1
            elif r.status == OfferStatus.rejected:
                rej += 1
    memo[host] = (pub, rej)
    return memo[host]
```

Add to `schemas/offer.py`:
```python
class ConfidenceOut(BaseModel):
    tier: str
    host: str = ""
    host_published: int = 0
    host_rejected: int = 0
    signals: list[str] = []


class OfferAdminOut(OfferOut):
    confidence: ConfidenceOut | None = None
```

Create `app/services/confidence.py`:
```python
from app.crud.offer import _source_host, host_reputation
from app.models.enums import OfferStatus
from app.schemas.offer import ConfidenceOut


def _primary_host(offer) -> str:
    for v in (offer.site_url, offer.article_url, offer.provider):
        h = _source_host(v)   # bare host only if it has a dot (provider free-text safe)
        if h:
            return h
    return ""


def score_offer(db, offer, memo: dict) -> ConfidenceOut:
    host = _primary_host(offer)
    pub, rej = host_reputation(db, host, memo) if host else (0, 0)
    has_discount = offer.discount_type is not None or bool(getattr(offer, "discounts", []))
    has_location = bool(getattr(offer, "locations", []))
    has_category = bool(getattr(offer, "offer_categories", []))
    signals = []
    if pub >= 1 and rej == 0:
        signals.append("proven_host")
    elif rej >= 1 and pub == 0:
        signals.append("noisy_host")
    elif pub == 0 and rej == 0:
        signals.append("new_host")
    if not has_discount:
        signals.append("no_discount")
    if not has_location:
        signals.append("no_location")
    if not has_category:
        signals.append("no_category")
    if pub >= 1 and rej == 0 and has_discount:
        tier = "high"
    elif (rej >= 1 and pub == 0) or not has_discount:
        tier = "low"
    else:
        tier = "medium"
    return ConfidenceOut(tier=tier, host=host, host_published=pub,
                         host_rejected=rej, signals=signals)


def enrich_pending(db, offers) -> None:
    memo: dict = {}
    for o in offers:
        o.confidence = score_offer(db, o, memo)
```
(`_source_host` already exists in `crud/offer.py` from #34 — bare host only when the value has a dot. Verify its name; if it's `_source_host(value)`, import as above.)

- [ ] **Step 4: Run** `tests/test_confidence.py` → PASS.
- [ ] **Step 5: Commit** `feat(backend): offer confidence service (host reputation + completeness)`

---

### Task 2: Backend — wire confidence into admin list + bulk-reject endpoint

**Files:**
- Modify: `backend/app/routers/admin.py`
- Test: `backend/tests/test_admin_offers.py` (or the file holding admin offer tests; else create `test_admin_moderation.py`)

**Interfaces:**
- `GET /admin/offers` → `Page[OfferAdminOut]`; pending items carry `confidence`, others None. Public unaffected.
- `POST /admin/offers/bulk-reject` body `BulkRejectIn{ids: list[int]}` → `BulkRejectOut{rejected: list[int], failed: list[BulkRejectFail]}`.

- [ ] **Step 1: Write failing tests** (mirror existing admin-offer test idioms — client fixture + admin token). Cover:
```python
def test_pending_list_has_confidence(client, admin_headers, db_session):
    # seed a published offer on host + a pending offer same host with discount
    ... # GET /admin/offers?status=pending_review -> items[0]["confidence"]["tier"] == "high"

def test_published_list_confidence_is_null(client, admin_headers, db_session):
    ... # GET /admin/offers?status=published -> items[0]["confidence"] is None

def test_public_offers_have_no_confidence_field(client, db_session):
    ... # publish an offer; GET /api/offers -> "confidence" not in items[0]

def test_bulk_reject_rejects_all_given(client, admin_headers, db_session):
    # 3 pending -> POST bulk-reject {ids:[...]} -> all rejected, body["rejected"] has 3 ids

def test_bulk_reject_reports_missing_id_in_failed(client, admin_headers, db_session):
    # ids=[real, 99999] -> real rejected, 99999 in failed

def test_bulk_reject_empty_ids_422(client, admin_headers):
    ...

def test_bulk_reject_requires_admin(client):
    # no token -> 401
```
(Use the auth-header helper already in the admin test suite. If none exists, reuse the login flow other admin tests use.)

- [ ] **Step 2: Run** → FAIL (endpoint 404 / confidence absent).

- [ ] **Step 3: Implement** in `admin.py`:
- Change `list_offers` response_model to `Page[OfferAdminOut]`; after `items, total = ...`, add:
```python
    if status == OfferStatus.pending_review:
        from app.services.confidence import enrich_pending
        enrich_pending(db, items)
```
- Add near the reject endpoint:
```python
class BulkRejectIn(BaseModel):
    ids: list[int] = Field(min_length=1)


class BulkRejectFail(BaseModel):
    id: int
    error: str


class BulkRejectOut(BaseModel):
    rejected: list[int] = []
    failed: list[BulkRejectFail] = []


@router.post("/offers/bulk-reject", response_model=BulkRejectOut)
def bulk_reject_offers(data: BulkRejectIn, db: Session = Depends(get_db),
                       admin=Depends(get_current_admin)):
    rejected, failed = [], []
    for oid in data.ids:
        try:
            offer_crud.set_status(db, oid, OfferStatus.rejected, admin.id)
            rejected.append(oid)
        except Exception as exc:  # noqa: BLE001 — isolate per id, report the rest
            failed.append(BulkRejectFail(id=oid, error=str(getattr(exc, "detail", exc))))
    return BulkRejectOut(rejected=rejected, failed=failed)
```
Add imports: `from pydantic import BaseModel, Field` (Field if not present), `OfferAdminOut`.
**Route order:** define `/offers/bulk-reject` BEFORE `/offers/{offer_id}`-style dynamic routes so "bulk-reject" is not captured as an offer_id (FastAPI matches in declaration order — place it above `get_offer`/other `/offers/{...}` if a collision is possible; a literal path segment vs `{offer_id}:int` won't collide on type, but keep it tidy).

- [ ] **Step 4: Run** admin offer tests + `tests/test_confidence.py` → PASS.
- [ ] **Step 5: Commit** `feat(backend): admin queue confidence + POST /admin/offers/bulk-reject`

---

### Task 3: Admin — ResponsiveTable opt-in selection

**Files:**
- Modify: `admin/src/components/ResponsiveTable.vue`
- Test: `admin/src/components/__tests__/ResponsiveTable.spec.js` (create/append per existing test layout)

**Interfaces:**
- New prop `selectable: Boolean = false`; new event `selection-change(rows)`. Desktop: leading `el-table-column type="selection"`. Mobile: a checkbox per card; emits the selected row array.

- [ ] **Step 1: Write failing test** — render with `selectable`, simulate selection, assert `selection-change` emitted with rows. (Match the existing admin component-test idiom — mount + Element Plus stubs. Check an existing `*.spec.js` for the mount helper.)
- [ ] **Step 2: Run** `npm test -- ResponsiveTable` → FAIL.
- [ ] **Step 3: Implement**: add `selectable` prop + `defineEmits(["selection-change"])`. Desktop: `<el-table ... @selection-change="$emit('selection-change', $event)"><el-table-column v-if="selectable" type="selection" width="46" />...`. Mobile: track a local `Set`/array, render `<el-checkbox>` per card, emit the selected rows on change. Keep non-selectable path byte-identical (prop default false → no selection column, no behavior change).
- [ ] **Step 4: Run** `npm test` → PASS.
- [ ] **Step 5: Commit** `feat(admin): ResponsiveTable opt-in row selection`

---

### Task 4: Admin — inline extracted badges + "Превʼю ↗" + confidence rendering

**Files:**
- Modify: `admin/src/views/OffersListView.vue`
- Modify: `admin/src/utils/format.js` (confidence tier/signal → label + tag type; discount summary helper)
- Test: `admin/src/views/__tests__/OffersListView.spec.js` (append)

**Interfaces:**
- `format.js`: `confidenceTagType(tier)`, `confidenceLabel(tier)`, `signalLabel(slug)`, `discountSummary(offer)`.
- View: compact tags (discount/cities/categories) in a new "Деталі" column; a "Превʼю ↗" action opening `article_url || site_url`; a confidence column (pending only) with tier tag + signal chips + host counts.

- [ ] **Step 1: Write failing tests** (append to OffersListView spec; mock `offers.list` to return items incl. `confidence`, `locations`, `offer_categories`, `discounts`). Assert:
  - a "Превʼю" control exists and, when clicked, calls `window.open` with article_url (spy on `window.open`).
  - preview control is disabled when neither url is http.
  - confidence tag renders tier label for a pending item; signal chips render.
  - inline city/category/discount tags render.
- [ ] **Step 2: Run** `npm test -- OffersListView` → FAIL.
- [ ] **Step 3: Implement**:
  - `format.js`: add helpers. `confidenceTagType`: high→"success", medium→"warning"|"info", low→"danger". `signalLabel`: map slugs → UA labels (`proven_host`→«надійний хост», `noisy_host`→«шумний хост», `new_host`→«новий хост», `no_discount`→«без знижки», `no_location`→«без міста», `no_category`→«без тематики»). `discountSummary(offer)` → e.g. «−20%» / «−100 грн» / «N знижок» / «—».
  - View: add a "Превʼю" button in `#actions` (before Редагувати): `@click="preview(row)"`, `:disabled="!isHttpUrl(row.article_url) && !isHttpUrl(row.site_url)"`; `function preview(row){ window.open(row.article_url || row.site_url, "_blank", "noopener"); }`.
  - Add a "Деталі" column slot: discount tag + up to ~3 city tags (`row.locations`) + category tags (`row.offer_categories.map(c=>c.name)`), compact.
  - Add a "Довіра" column slot, shown only when `props.fixedStatus === 'pending_review'` (or when `row.confidence`): `<el-tag :type="confidenceTagType(row.confidence.tier)">{{ confidenceLabel(...) }}</el-tag>` + host counts «✓{host_published} ✕{host_rejected}» + signal chips.
- [ ] **Step 4: Run** `npm test` → PASS.
- [ ] **Step 5: Commit** `feat(admin): queue preview link + inline badges + confidence signals`

---

### Task 5: Admin — bulk-reject selection UI + client-side confidence sort

**Files:**
- Modify: `admin/src/views/OffersListView.vue`, `admin/src/api/offers.js`
- Test: `admin/src/views/__tests__/OffersListView.spec.js` (append)

**Interfaces:**
- `offers.js`: `bulkReject(ids)` → `POST /admin/offers/bulk-reject {ids}`.
- View (pending only): selection via `ResponsiveTable selectable`; «Відхилити вибрані (N)» button → confirm → `bulkReject` → reload + `moderation.refresh()`. A confidence sort control reorders loaded items client-side.

- [ ] **Step 1: Write failing tests**: select 2 rows → click bulk-reject → confirm auto-resolves → `offers.bulkReject` called with the 2 ids → `load` re-called. Sort control toggles item order by tier.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**:
  - `offers.js`: `export const bulkReject = (ids) => client.post("/admin/offers/bulk-reject", { ids }).then(r=>r.data);`
  - View: `const selected = ref([]);` bind `<ResponsiveTable :selectable="!!fixedStatus" @selection-change="selected = $event">`. Button (v-if fixedStatus && selected.length): «Відхилити вибрані ({{ selected.length }})» → `confirmAction(...)` → `offers.bulkReject(selected.map(r=>r.id))` → ElMessage + `load()` + `moderation.refresh()` + clear selection. Handle `res.failed` (warn if any).
  - Confidence sort: `const sortByConfidence = ref(false)`; a computed `displayItems` that, when on, sorts `items` by tier rank (low=0<medium=1<high=2 or reverse) — expose a toggle/select. Feed `displayItems` to the table. Document: sorts within the loaded page only.
- [ ] **Step 4: Run** `npm test` → PASS.
- [ ] **Step 5: Commit** `feat(admin): bulk-reject selected + client-side confidence sort`

---

### Task 6: Full suites + build + deploy

- [ ] **Step 1:** backend `pytest -q` (mysql-container up) → all green (record 187 → +N).
- [ ] **Step 2:** admin `npm test` AND `npm run build` → both green (build MANDATORY — scoped-Less).
- [ ] **Step 3:** Deploy — `docker compose build backend admin && docker compose up -d`. No migration.
- [ ] **Step 4:** Live check: log into admin, open «Черга модерації» — confidence tags + preview link + inline badges visible; select rows → bulk-reject works; a rejected offer appears under «Відхилені» (restorable). Confirm public `/api/offers` has no `confidence`.
- [ ] **Step 5: Report** counts + screenshot/observation.

---

## Self-Review notes
- **Spec coverage:** A (preview + inline) → Task 4; B (confidence) → Tasks 1–2 (+render 4, sort 5); C (bulk reject) → Task 2 (backend) + Tasks 3,5 (UI).
- **Public isolation:** `OfferAdminOut` only on admin `list_offers`; public `OfferOut` untouched (test asserts no `confidence`).
- **Assist-only:** confidence never gates publish; bulk is reject-only + confirmed.
- **Reuse:** `host_reputation` factors #34's counting; `set_status` reused for bulk (incl. auto-block learning).
- **Known limitation (documented):** confidence sort is within-page (post-SQL enrichment); global sort deferred.
- **Frontend rigor:** every admin task ends with `npm test`; Task 6 additionally runs `npm run build`.
