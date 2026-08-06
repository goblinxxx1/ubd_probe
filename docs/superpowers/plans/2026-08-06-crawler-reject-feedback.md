# Reject навчає рейтинг доменів (soft down-rank) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close backlog #9. Feed moderator **rejections** back into the crawler's `DomainRegistry` as a soft **down-rank**, so a domain whose offers keep getting rejected loses score and drops out of `DomainFeed.top()` / `site:` targeting. Mirrors the existing snowball (approved-offers) channel. Complements — does not duplicate — the #34 hard-block.

**Architecture:** Backend adds one read-only endpoint `GET /api/internal/rejected-offers?since=` (mirror of `approved-offers`). Crawler gains: `DomainRegistry.record_rejections(host, n)` (soft down-rank, `reject_weight=1.0`), a `RejectionIngestor` poller (cursor in JSON, mirror of `SnowballIngestor`), an `api_client.list_rejected_offers`, config knobs, wiring under `domain_rating_enabled AND rejection_feedback_enabled`, and a best-effort `ingest()` call at the top of `Runner.run_active()`.

**Tech Stack:** Python, FastAPI/SQLAlchemy (backend), httpx (crawler), pytest. Backend tests need MySQL at :3306 — `docker start mysql-container` first.

## Global Constraints

- Test cmds: backend (from `backend/`) `./.venv/Scripts/python.exe -m pytest -q` (needs mysql-container:3306); crawler (from `crawler/`) `./.venv/Scripts/python.exe -m pytest -q`.
- **Down-rank decision:** `reject_weight = 1.0` (cancels one offer's `offer_weight`). **Unknown host = Skip** — `record_rejections` no-ops for a host absent from the registry (nothing to re-feed; repeat noise is handled by #34/#36). Never create a registry entry from a rejection.
- **Host key:** `_host(o.site_url or o.article_url)` on the backend (same `_host` used by `approved-offers`); the crawler aggregates by that host and passes it to `record_rejections` (which re-normalizes via `brand_feed._host`, idempotent).
- **OFF-equivalence:** with `rejection_feedback_enabled=False` OR `domain_rating_enabled=False`, no ingestor is built and `run_active` is byte-identical to pre-track. The backend endpoint is inert (read-only, uncalled).
- **Cursor:** `since` = `updated_at` (ISO string round-trip, exactly like approved-offers). The ingestor advances the cursor even when every host is Skipped, so the same rejected rows are not re-read next pass.
- Do NOT change `search_pass` (it never reads the registry), attribution, extractor, admin, public. No DB migration.

---

### Task 1: Backend — `list_rejected_since` + `/rejected-offers` endpoint

**Files:**
- Modify: `backend/app/crud/offer.py`, `backend/app/routers/internal.py`
- Test: `backend/tests/test_internal.py` (append)

**Interfaces:**
- Produces: `offer_crud.list_rejected_since(db, since: datetime | None) -> list[Offer]` (crawler-origin rejected offers, `updated_at > since`, asc); endpoint `GET /api/internal/rejected-offers` → `list[RejectedOfferOut(host: str, rejected_at: datetime | None)]`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_internal.py`:
```python
def test_rejected_offers_returns_crawler_rejected(client, db_session):
    from app.models import Offer
    from app.models.enums import CreatedBy, OfferStatus, OfferType
    db_session.add_all([
        Offer(type=OfferType.discount, title="R1", provider="P",
              site_url="https://news.ua/a", article_url="https://news.ua/a",
              status=OfferStatus.rejected, created_by=CreatedBy.crawler),
        Offer(type=OfferType.discount, title="P1", provider="P",
              site_url="https://shop.ua/x", status=OfferStatus.published,
              created_by=CreatedBy.crawler),
        Offer(type=OfferType.discount, title="Pend", provider="P",
              site_url="https://pend.ua/x", status=OfferStatus.pending_review,
              created_by=CreatedBy.crawler),
        Offer(type=OfferType.discount, title="AdminR", provider="P",
              site_url="https://man.ua/x", status=OfferStatus.rejected,
              created_by=CreatedBy.admin),
    ])
    db_session.commit()
    r = client.get("/api/internal/rejected-offers",
                   headers={"X-API-Key": settings.crawler_api_key})
    assert r.status_code == 200
    hosts = [row["host"] for row in r.json()]
    assert "news.ua" in hosts              # crawler+rejected
    assert "shop.ua" not in hosts          # published excluded
    assert "pend.ua" not in hosts          # pending excluded
    assert "man.ua" not in hosts           # admin-rejected excluded


def test_rejected_offers_host_falls_back_to_article_url(client, db_session):
    from app.models import Offer
    from app.models.enums import CreatedBy, OfferStatus, OfferType
    db_session.add(Offer(type=OfferType.discount, title="R", provider="P",
                         site_url=None, article_url="https://blog.ua/p",
                         status=OfferStatus.rejected, created_by=CreatedBy.crawler))
    db_session.commit()
    r = client.get("/api/internal/rejected-offers",
                   headers={"X-API-Key": settings.crawler_api_key})
    assert any(row["host"] == "blog.ua" for row in r.json())


def test_rejected_offers_respects_since(client, db_session):
    from datetime import datetime, timedelta
    from app.models import Offer
    from app.models.enums import CreatedBy, OfferStatus, OfferType
    old = Offer(type=OfferType.discount, title="old", provider="P",
                site_url="https://old.ua/x", status=OfferStatus.rejected,
                created_by=CreatedBy.crawler)
    db_session.add(old); db_session.commit()
    cutoff = datetime.utcnow() + timedelta(seconds=1)
    r = client.get("/api/internal/rejected-offers", params={"since": cutoff.isoformat()},
                   headers={"X-API-Key": settings.crawler_api_key})
    assert r.status_code == 200
    assert all(row["host"] != "old.ua" for row in r.json())


def test_rejected_offers_requires_api_key(client):
    assert client.get("/api/internal/rejected-offers").status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_internal.py -k rejected`
Expected: FAIL — endpoint 404 / `list_rejected_since` undefined.

- [ ] **Step 3: Implement**

In `backend/app/crud/offer.py`, next to `list_published_since` (≈ line 399):
```python
def list_rejected_since(db: Session, since: datetime | None = None):
    q = db.query(Offer).filter(Offer.status == OfferStatus.rejected,
                               Offer.created_by == CreatedBy.crawler)
    if since is not None:
        q = q.filter(Offer.updated_at > since)
    return q.order_by(Offer.updated_at.asc()).all()
```
(`datetime`, `CreatedBy`, `OfferStatus` are already imported in this module.)

In `backend/app/routers/internal.py`, after the approved-offers block (≈ line 124):
```python
class RejectedOfferOut(BaseModel):
    host: str
    rejected_at: datetime | None = None


@router.get("/rejected-offers", response_model=list[RejectedOfferOut])
def list_rejected_offers(since: datetime | None = None, db: Session = Depends(get_db)):
    rows = offer_crud.list_rejected_since(db, since)
    out = []
    for o in rows:
        host = _host(o.site_url or o.article_url)
        if host:
            out.append(RejectedOfferOut(host=host, rejected_at=o.updated_at))
    return out
```
(`_host`, `datetime`, `BaseModel` already present in the module.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_internal.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/crud/offer.py backend/app/routers/internal.py backend/tests/test_internal.py
git commit -m "feat(backend): GET /api/internal/rejected-offers (crawler rejections feed)"
```

---

### Task 2: Crawler — `DomainRegistry.record_rejections` + `reject_weight`

**Files:**
- Modify: `crawler/crawler/discovery/domain_registry.py`
- Test: `crawler/tests/test_domain_registry.py` (append)

**Interfaces:**
- Produces: `DomainRegistry(..., reject_weight=1.0)`; `record_rejections(host, n) -> None` — soft down-rank of an **existing** entry only.

- [ ] **Step 1: Write the failing tests**

Append to `crawler/tests/test_domain_registry.py`:
```python
def test_record_rejections_downranks_existing_host():
    from crawler.discovery.domain_registry import DomainRegistry
    reg = DomainRegistry("x.json", data={"version": 1, "domains": {}},
                         clock=lambda: 1000.0, reject_weight=1.0)
    reg.record("shop.ua", offers=3, errors=0)   # score 3.0
    reg.record_rejections("shop.ua", 2)          # -2.0 -> 1.0
    assert reg.score("shop.ua") == 1.0
    e = reg._data["domains"]["shop.ua"]
    assert e["rejects"] == 2
    assert e["offers"] == 3 and e["errors"] == 0 and e["passes"] == 1  # untouched


def test_record_rejections_clamps_at_zero():
    from crawler.discovery.domain_registry import DomainRegistry
    reg = DomainRegistry("x.json", data={"version": 1, "domains": {}},
                         clock=lambda: 1.0, reject_weight=1.0)
    reg.record("noisy.ua", offers=1, errors=0)   # 1.0
    reg.record_rejections("noisy.ua", 5)         # would be -4 -> clamp 0
    assert reg.score("noisy.ua") == 0.0


def test_record_rejections_skips_unknown_host():
    from crawler.discovery.domain_registry import DomainRegistry
    reg = DomainRegistry("x.json", data={"version": 1, "domains": {}},
                         clock=lambda: 1.0, reject_weight=1.0)
    reg.record_rejections("ghost.ua", 3)
    assert "ghost.ua" not in reg._data["domains"]
    assert reg.score("ghost.ua") == 0.0


def test_record_rejections_ignores_empty_host():
    from crawler.discovery.domain_registry import DomainRegistry
    reg = DomainRegistry("x.json", data={"version": 1, "domains": {}}, clock=lambda: 1.0)
    reg.record_rejections("", 2)   # no crash, no entry
    assert reg._data["domains"] == {}


def test_record_rejections_does_not_move_last_seen():
    from crawler.discovery.domain_registry import DomainRegistry
    clk = [100.0]
    reg = DomainRegistry("x.json", data={"version": 1, "domains": {}},
                         clock=lambda: clk[0], reject_weight=1.0)
    reg.record("a.ua", offers=2, errors=0)
    seen_before = reg._data["domains"]["a.ua"]["last_seen"]
    clk[0] = 900.0
    reg.record_rejections("a.ua", 1)
    assert reg._data["domains"]["a.ua"]["last_seen"] == seen_before   # cooldown/prune unaffected
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_domain_registry.py -k rejection`
Expected: FAIL — `reject_weight` kwarg / `record_rejections` undefined.

- [ ] **Step 3: Implement in `domain_registry.py`**

Add `reject_weight` to `__init__` (after `promote_min_score`):
```python
    def __init__(self, path, data=None, clock=time.time, *,
                 decay=0.9, offer_weight=1.0, error_weight=0.5, promote_min_score=0.5,
                 reject_weight=1.0):
        ...
        self._promote = promote_min_score
        self._reject_w = reject_weight
```
In `record`, add `"rejects": 0` to the new-entry dict (keeps shape stable):
```python
            e = {"score": 0.0, "offers": 0, "errors": 0, "rejects": 0, "passes": 0,
                 "empty_passes": 0, "first_seen": now, "last_seen": now, "last_offer": 0.0}
```
Add the method (after `record`):
```python
    def record_rejections(self, host, n):
        """Soft down-rank an EXISTING domain by n rejections (score -= n*reject_weight,
        clamped >=0). No-op for an unknown/empty host — nothing to re-feed. Does not touch
        offers/errors/passes/last_seen (a rejection is not a crawl pass)."""
        host = _host(host)
        e = self._data["domains"].get(host)
        if not host or e is None or n <= 0:
            return
        e["score"] = max(0.0, e["score"] - n * self._reject_w)
        e["rejects"] = e.get("rejects", 0) + int(n)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_domain_registry.py`
Expected: PASS (existing registry tests still green — `rejects` key addition is additive; reads use `.get`).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/domain_registry.py crawler/tests/test_domain_registry.py
git commit -m "feat(crawler): DomainRegistry.record_rejections soft down-rank (skip unknown)"
```

---

### Task 3: Crawler — `RejectionIngestor` + `api_client.list_rejected_offers`

**Files:**
- Create: `crawler/crawler/learn/reject_feedback.py`
- Modify: `crawler/crawler/api_client.py`
- Test: `crawler/tests/test_reject_feedback.py` (create), `crawler/tests/test_api_client.py` (append)

**Interfaces:**
- Produces: `ApiClient.list_rejected_offers(since=None) -> list[dict]`; `RejectionIngestor(api, registry, state_path)` with `ingest() -> int` (rows applied).

- [ ] **Step 1: Write the failing tests**

Create `crawler/tests/test_reject_feedback.py`:
```python
import json

from crawler.discovery.domain_registry import DomainRegistry
from crawler.learn.reject_feedback import RejectionIngestor


class _Api:
    def __init__(self, rows):
        self._rows = rows
        self.since_seen = "UNSET"

    def list_rejected_offers(self, since=None):
        self.since_seen = since
        return self._rows


def _reg():
    reg = DomainRegistry("x.json", data={"version": 1, "domains": {}},
                         clock=lambda: 1.0, reject_weight=1.0)
    reg.record("shop.ua", offers=3, errors=0)   # 3.0
    reg.record("news.ua", offers=2, errors=0)   # 2.0
    return reg


def test_ingest_aggregates_per_host_and_downranks(tmp_path):
    reg = _reg()
    api = _Api([
        {"host": "shop.ua", "rejected_at": "2026-08-06T10:00:00"},
        {"host": "shop.ua", "rejected_at": "2026-08-06T11:00:00"},
        {"host": "news.ua", "rejected_at": "2026-08-06T09:00:00"},
    ])
    n = RejectionIngestor(api, reg, str(tmp_path / "since.json")).ingest()
    assert n == 3
    assert reg.score("shop.ua") == 1.0    # 3 - 2*1.0
    assert reg.score("news.ua") == 1.0    # 2 - 1*1.0


def test_ingest_saves_newest_cursor(tmp_path):
    reg = _reg()
    state = str(tmp_path / "since.json")
    api = _Api([
        {"host": "shop.ua", "rejected_at": "2026-08-06T10:00:00"},
        {"host": "news.ua", "rejected_at": "2026-08-06T12:30:00"},
    ])
    RejectionIngestor(api, reg, state).ingest()
    assert json.load(open(state, encoding="utf-8"))["since"] == "2026-08-06T12:30:00"


def test_ingest_passes_saved_since_next_time(tmp_path):
    reg = _reg()
    state = str(tmp_path / "since.json")
    json.dump({"since": "2026-08-01T00:00:00"}, open(state, "w"))
    api = _Api([])
    RejectionIngestor(api, reg, state).ingest()
    assert api.since_seen == "2026-08-01T00:00:00"


def test_ingest_skips_unknown_hosts_but_advances_cursor(tmp_path):
    reg = _reg()
    state = str(tmp_path / "since.json")
    api = _Api([{"host": "ghost.ua", "rejected_at": "2026-08-06T08:00:00"}])
    n = RejectionIngestor(api, reg, state).ingest()
    assert n == 1                                   # row processed
    assert "ghost.ua" not in reg._data["domains"]   # skipped
    assert json.load(open(state, encoding="utf-8"))["since"] == "2026-08-06T08:00:00"


def test_ingest_ignores_empty_host_rows(tmp_path):
    reg = _reg()
    api = _Api([{"host": "", "rejected_at": "2026-08-06T08:00:00"}])
    RejectionIngestor(api, reg, str(tmp_path / "since.json")).ingest()
    assert reg.score("shop.ua") == 3.0   # untouched
```

Append to `crawler/tests/test_api_client.py` (mirror the existing `list_approved_offers` test — use the same transport/mock pattern already in that file):
```python
def test_list_rejected_offers_calls_endpoint():
    import httpx
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json=[{"host": "news.ua", "rejected_at": None}])

    from crawler.api_client import ApiClient
    with ApiClient("http://x", "k", 5.0, transport=httpx.MockTransport(handler)) as api:
        rows = api.list_rejected_offers("2026-08-01T00:00:00")
    assert rows == [{"host": "news.ua", "rejected_at": None}]
    assert "/api/internal/rejected-offers" in seen["url"]
    assert "since=2026-08-01" in seen["url"]
```
(If `test_api_client.py` uses a different mock idiom for `list_approved_offers`, copy THAT idiom instead — keep it consistent with the file.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_reject_feedback.py tests/test_api_client.py -k "reject or rejected"`
Expected: FAIL — module/method undefined.

- [ ] **Step 3: Implement**

Add to `crawler/crawler/api_client.py` (after `list_approved_offers`):
```python
    def list_rejected_offers(self, since: str | None = None) -> list[dict]:
        params = {"since": since} if since else {}
        r = self._client.get("/api/internal/rejected-offers", params=params)
        r.raise_for_status()
        return r.json()
```

Create `crawler/crawler/learn/reject_feedback.py`:
```python
"""Reject feedback: moderator-rejected crawler offers → soft down-rank in DomainRegistry.
Mirrors SnowballIngestor (approved-offers), with a JSON `since` cursor."""

import json
import os


class RejectionIngestor:
    def __init__(self, api, registry, state_path: str):
        self._api = api
        self._reg = registry
        self._state_path = state_path

    def _since(self):
        try:
            return json.load(open(self._state_path, encoding="utf-8")).get("since")
        except (OSError, ValueError):
            return None

    def _save_since(self, since):
        os.makedirs(os.path.dirname(self._state_path) or ".", exist_ok=True)
        json.dump({"since": since}, open(self._state_path, "w", encoding="utf-8"))

    def ingest(self) -> int:
        rows = self._api.list_rejected_offers(self._since()) or []
        counts: dict[str, int] = {}
        newest = None
        n = 0
        for row in rows:
            host = (row.get("host") or "").strip()
            if host:
                counts[host] = counts.get(host, 0) + 1
            ts = row.get("rejected_at")
            if ts and (newest is None or ts > newest):
                newest = ts
            n += 1
        for host, cnt in counts.items():
            self._reg.record_rejections(host, cnt)
        if newest:
            self._save_since(newest)
        return n
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_reject_feedback.py tests/test_api_client.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/learn/reject_feedback.py crawler/crawler/api_client.py crawler/tests/test_reject_feedback.py crawler/tests/test_api_client.py
git commit -m "feat(crawler): RejectionIngestor + api_client.list_rejected_offers"
```

---

### Task 4: Crawler — config knobs, wiring, Runner injection

**Files:**
- Modify: `crawler/crawler/config.py`, `crawler/crawler/wiring.py`, `crawler/crawler/runner.py`
- Test: `crawler/tests/test_config.py`, `crawler/tests/test_wiring.py`, `crawler/tests/test_runner.py` (append to whichever exist)

**Interfaces:**
- Config: `rejection_feedback_enabled: bool = True`, `domain_reject_weight: float = 1.0`, `reject_since_state_path: str` (default mirrors `snowball_state_path` dir, e.g. `/data/reject_since.json`).
- `Runner(..., reject_ingestor=None)`; `run_active` calls `reject_ingestor.ingest()` (best-effort) right after the `harvester is None` early-return, before feeds.
- Wiring builds `RejectionIngestor` only when `domain_rating_enabled AND rejection_feedback_enabled`, reusing the same `domain_registry`; passes `reject_weight=config.domain_reject_weight` into `DomainRegistry.load`.

- [ ] **Step 1: Write the failing tests**

Config test (append to `crawler/tests/test_config.py`):
```python
def test_reject_feedback_config_defaults():
    from crawler.config import CrawlerConfig
    import inspect
    sig = inspect.signature(CrawlerConfig)
    assert "rejection_feedback_enabled" in sig.parameters
    assert "domain_reject_weight" in sig.parameters
    assert "reject_since_state_path" in sig.parameters
```
(If `CrawlerConfig` is a dataclass, assert on fields/defaults using the file's existing idiom instead.)

Wiring test (append to `crawler/tests/test_wiring.py`, mirror an existing gated-build test):
```python
def test_reject_ingestor_built_when_enabled(monkeypatch, tmp_path):
    # Use the file's existing build_runner harness/fixture. Assert:
    #  - config(domain_rating_enabled=True, rejection_feedback_enabled=True) -> runner._reject_ingestor is not None
    #  - it reuses the same registry object as domain_feed
    ...


def test_reject_ingestor_absent_when_disabled(...):
    # rejection_feedback_enabled=False OR domain_rating_enabled=False -> runner._reject_ingestor is None
    ...
```
(Fill these in using the concrete `build_runner` test pattern already in `test_wiring.py`; keep the same fixtures/mocks. If the harness makes reuse-identity awkward, at minimum assert presence/absence under the two flag combinations.)

Runner test (append to `crawler/tests/test_runner.py`):
```python
def test_run_active_ingests_rejections_before_feeds():
    # Build a Runner with a stub reject_ingestor whose ingest() records call order,
    # and a stub domain_feed.candidates() that also records order; assert ingest ran first.
    ...


def test_run_active_survives_reject_ingest_error():
    # reject_ingestor.ingest() raises -> run_active still completes, summary returned,
    # error counted/logged, feeds still run.
    ...
```
(Use the existing Runner unit-test stubs in `test_runner.py`; a minimal `harvester` stub is required so `run_active` does not early-return.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_config.py tests/test_wiring.py tests/test_runner.py -k "reject"`
Expected: FAIL — knobs/param/call not present.

- [ ] **Step 3: Implement**

`config.py` — add the three knobs to `CrawlerConfig` (both the dataclass/defaults block ≈ lines 26–34 pattern AND the `Settings` env block ≈ lines 122–130) and thread them through `from_settings` (≈ lines 241–249), mirroring `snowball_state_path` / `domain_offer_weight`:
```python
    rejection_feedback_enabled: bool = True
    domain_reject_weight: float = 1.0
    reject_since_state_path: str = "/data/reject_since.json"
```

`runner.py` — add `reject_ingestor=None` to `__init__`, store `self._reject_ingestor`. In `run_active`, immediately after `if self._harvester is None: return summary`:
```python
        if self._reject_ingestor is not None:
            try:
                self._reject_ingestor.ingest()
            except Exception as exc:  # noqa: BLE001 — feedback must not crash the pass
                summary["errors"] += 1
                log.warning("reject feedback ingest failed: %s", exc)
```

`wiring.py` — in the `if config.domain_rating_enabled:` block, pass `reject_weight=config.domain_reject_weight` into `DomainRegistry.load(...)`. After the registry/feed build, add:
```python
    reject_ingestor = None
    if config.domain_rating_enabled and config.rejection_feedback_enabled:
        from crawler.learn.reject_feedback import RejectionIngestor
        reject_ingestor = RejectionIngestor(api, domain_registry, config.reject_since_state_path)
```
Pass `reject_ingestor=reject_ingestor` into the `Runner(...)` constructor.

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest -q tests/test_config.py tests/test_wiring.py tests/test_runner.py`
Expected: PASS.

- [ ] **Step 5: Update env/docs + commit**

Add to `crawler/.env.example` (mirror the domain-rating block):
```
# Reject feedback (soft down-rank of rejected domains; needs DOMAIN_RATING_ENABLED)
REJECTION_FEEDBACK_ENABLED=true
DOMAIN_REJECT_WEIGHT=1.0
REJECT_SINCE_STATE_PATH=/data/reject_since.json
```
Add a short note to `RUN.md` under the domain-rating block. Then:
```bash
git add crawler/crawler/config.py crawler/crawler/wiring.py crawler/crawler/runner.py crawler/tests/ crawler/.env.example RUN.md
git commit -m "feat(crawler): wire reject feedback into run_active (gated, OFF byte-eq)"
```

---

### Task 5: Full suites + deploy verification

**Files:** none (verification/deploy).

- [ ] **Step 1: Full suites green**

Backend (from `backend/`, `docker start mysql-container` first): `./.venv/Scripts/python.exe -m pytest -q`
Crawler (from `crawler/`): `./.venv/Scripts/python.exe -m pytest -q`
Expected: both PASS, 0 failures. Record counts (crawler baseline 553 → +new; backend 183 → +4).

- [ ] **Step 2: OFF byte-equivalence sanity**

Confirm that with `rejection_feedback_enabled=False`, `build_runner` yields `runner._reject_ingestor is None` and no reject endpoint is called (covered by Task 4 test; re-affirm in review).

- [ ] **Step 3: Deploy (canonical rebuild)**

```bash
docker compose build backend crawler && docker compose up -d
```
Backend endpoint is live (no migration). Crawler picks up the ingestor next pass. Verify:
- `GET /api/internal/rejected-offers` returns rejected crawler-offer hosts (curl with X-API-Key).
- After a crawl pass, `/data/reject_since.json` exists and `domain_registry.json` shows a down-ranked `rejects` counter on any host that had a rejection.

- [ ] **Step 4: Report** counts + a live before/after score for one rejected host.

---

## Self-Review notes
- **Spec coverage:** Component 1 (endpoint) → Task 1; Component 2 (`record_rejections`) → Task 2; Component 3 (`RejectionIngestor`) + Component 4 (api_client) → Task 3; Component 5 (config/wiring/runner) → Task 4; verification → Task 5.
- **Decisions honored:** `reject_weight=1.0` (Task 2/4); unknown-host **Skip** (Task 2 `record_rejections` early-return, Task 3 cursor still advances).
- **OFF-equivalence:** gated build (Task 4) → `run_active` unchanged when disabled; endpoint inert.
- **Placement rationale:** `main()` runs `run()` once per process (external loop), so ingest must be per-pass inside `run_active` (not wiring-time) and paired with the existing `finally` registry-save. Documented in Global Constraints.
- **Type consistency:** `list_rejected_since(db, since)`, `RejectedOfferOut(host, rejected_at)`, `record_rejections(host, n)`, `list_rejected_offers(since)`, `RejectionIngestor(api, registry, state_path).ingest()`, `Runner(..., reject_ingestor=)` used consistently.
- **No new migration; no change to search_pass/attribution/extractor/admin/public.**
