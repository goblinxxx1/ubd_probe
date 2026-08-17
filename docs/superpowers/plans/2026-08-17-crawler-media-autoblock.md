# Media Host Auto-Block Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-block a media host from all future crawling after K crawls that produced offers but never carried Offer/LocalBusiness schema (structural provider-evidence).

**Architecture:** The website fetcher already computes `has_offer_schema`/`has_business_schema` per page. Thread a per-host-per-crawl `structural_provider` flag up through `_process_page` → `_harvest_one` → `harvest()`, feed it to `DomainRegistry.record`, which maintains a `media_streak`; when the streak crosses K with no provider evidence ever, POST the host to the backend `blocked_hosts` table (approved, system) via a new internal endpoint, and add it to the crawler runtime blocklist so it drops immediately. `is_article` is NOT used.

**Tech Stack:** Python 3.12, FastAPI + SQLAlchemy (backend), httpx (crawler), pytest.

## Global Constraints

- Crawler venv: `/d/ubd_probe/crawler/.venv/Scripts/python.exe`. Backend venv: `/d/ubd_probe/backend/.venv/Scripts/python.exe`. Never call bare `python`/`pytest`.
- Backend tests need the MySQL `ubd_test` container running (`docker ps`; `docker start mysql-container` if needed).
- `is_article` MUST NOT influence the media-block decision (it fires on legit discount sites too).
- Provider-evidence = STRUCTURAL schema only (`has_offer_schema` OR `has_business_schema`), never the text-heuristic first-party attribution.
- All new config defaults: `media_autoblock_enabled=True`, `media_autoblock_crawls=2` (block on the 2nd offer-only crawl).
- Work on branch `track-media-autoblock` (already created). Conventional-commit messages; end each with the `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` trailer.
- Ukrainian for user-facing prose; code/comments follow the file's existing language.

## File Structure

- `backend/app/schemas/blocked_host.py` — add `AutoBlockCreate` schema.
- `backend/app/crud/blocked_host.py` — extend `auto_block` with optional `sample_url`.
- `backend/app/routers/internal.py` — add `POST /api/internal/blocked-hosts`.
- `backend/tests/test_internal.py` — endpoint tests.
- `crawler/crawler/api_client.py` — add `auto_block_host`.
- `crawler/tests/test_api_client.py` — client test.
- `crawler/crawler/discovery/blocklist.py` — add `add_learned`.
- `crawler/tests/test_blocklist.py` — test.
- `crawler/crawler/discovery/domain_registry.py` — media-streak state + `media_block_due`.
- `crawler/tests/test_domain_registry.py` — tests.
- `crawler/crawler/discovery/media_autoblock.py` — new `MediaAutoBlocker` (create).
- `crawler/tests/test_media_autoblock.py` — new test (create).
- `crawler/crawler/discovery/harvest.py` — thread `structural_provider`, call blocker.
- `crawler/tests/test_active_harvest.py` — integration test.
- `crawler/crawler/config.py` — 2 new config fields (3 sites).
- `crawler/crawler/wiring.py` — construct `MediaAutoBlocker`, wire into `ActiveHarvester`.

---

### Task 1: Backend auto-block endpoint

**Files:**
- Modify: `backend/app/schemas/blocked_host.py`
- Modify: `backend/app/crud/blocked_host.py:95-110` (`auto_block`)
- Modify: `backend/app/routers/internal.py` (add route + import)
- Test: `backend/tests/test_internal.py`

**Interfaces:**
- Produces: `POST /api/internal/blocked-hosts` body `{host: str, sample_url: str | None}` → `BlockedHostOut`; `blocked_host_crud.auto_block(db, host, sample_url=None) -> BlockedHost`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_internal.py` (uses the file's existing `client` fixture and `settings` import — same `X-API-Key` pattern as the other `/api/internal/*` tests):

```python
def test_auto_block_host_creates_approved_row(client):
    h = {"X-API-Key": settings.crawler_api_key}
    r = client.post("/api/internal/blocked-hosts",
                    json={"host": "dumka.media", "sample_url": "https://dumka.media/ukr/x"},
                    headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["host"] == "dumka.media"
    assert body["status"] == "approved"
    assert body["sample_urls"] == ["https://dumka.media/ukr/x"]

    # idempotent: second call keeps it approved, no duplicate
    r2 = client.post("/api/internal/blocked-hosts", json={"host": "dumka.media"}, headers=h)
    assert r2.status_code == 200 and r2.json()["status"] == "approved"

    listed = client.get("/api/internal/blocked-hosts", headers=h).json()
    assert listed.count("dumka.media") == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/d/ubd_probe/backend/.venv/Scripts/python.exe -m pytest tests/test_internal.py::test_auto_block_host_creates_approved_row -v` (from `backend/`)
Expected: FAIL — 404 (route missing).

- [ ] **Step 3: Add the schema**

In `backend/app/schemas/blocked_host.py`, after `BlockedHostCreate`:

```python
class AutoBlockCreate(BaseModel):
    host: str
    sample_url: str | None = None
```

- [ ] **Step 4: Extend `auto_block` with `sample_url`**

In `backend/app/crud/blocked_host.py`, replace the `auto_block` function body:

```python
def auto_block(db: Session, host: str, sample_url: str | None = None) -> BlockedHost:
    """System (non-human) block: upsert host to approved with reviewed_by=None.
    Idempotent — an existing row is promoted to approved. `sample_url`, if given,
    is stored as evidence on first creation (existing rows keep their samples)."""
    h = bare_host(host)
    if not h:
        raise validation_error("host is required")
    obj = db.query(BlockedHost).filter(BlockedHost.host == h).first()
    if obj is None:
        obj = BlockedHost(host=h, status=BlockedHostStatus.approved, reviewed_by=None,
                          reviewed_at=datetime.now(timezone.utc),
                          sample_urls=[sample_url] if sample_url else None)
        db.add(obj)
    else:
        obj.status = BlockedHostStatus.approved
    db.commit()
    db.refresh(obj)
    return obj
```

- [ ] **Step 5: Add the route**

In `backend/app/routers/internal.py`: add `AutoBlockCreate` to the `from app.schemas.blocked_host import ...` line, then add below the existing `list_blocked_hosts`:

```python
@router.post("/blocked-hosts", response_model=BlockedHostOut)
def auto_block_host(data: AutoBlockCreate, db: Session = Depends(get_db)):
    return blocked_host_crud.auto_block(db, data.host, data.sample_url)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `/d/ubd_probe/backend/.venv/Scripts/python.exe -m pytest tests/test_internal.py::test_auto_block_host_creates_approved_row -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/blocked_host.py backend/app/crud/blocked_host.py backend/app/routers/internal.py backend/tests/test_internal.py
git commit -m "feat(backend): internal POST /blocked-hosts for system media auto-block

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Crawler `api_client.auto_block_host`

**Files:**
- Modify: `crawler/crawler/api_client.py:97-100` (after `list_blocked_hosts`)
- Test: `crawler/tests/test_api_client.py`

**Interfaces:**
- Consumes: `POST /api/internal/blocked-hosts` (Task 1).
- Produces: `ApiClient.auto_block_host(host: str, sample_url: str | None = None) -> dict`.

- [ ] **Step 1: Write the failing test**

Add to `crawler/tests/test_api_client.py` (extend the `_handler` `captured` pattern):

```python
def test_auto_block_host_posts_host():
    captured = []
    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.url.path == "/api/internal/blocked-hosts" and request.method == "POST":
            return httpx.Response(200, json={"id": 1, "host": "dumka.media",
                "status": "approved", "media_ratio": 0.0, "aggregator_ratio": 0.0,
                "support": 0, "sample_urls": None, "reviewed_at": None,
                "created_at": "2026-08-17T00:00:00"})
        return httpx.Response(404, json={"code": "not_found", "detail": "x"})
    client = ApiClient("http://api", "secret", 10.0,
                       transport=httpx.MockTransport(handle))
    out = client.auto_block_host("dumka.media", "https://dumka.media/x")
    assert out["host"] == "dumka.media"
    sent = json.loads(captured[0].content)
    assert sent == {"host": "dumka.media", "sample_url": "https://dumka.media/x"}
    assert captured[0].headers["X-API-Key"] == "secret"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/d/ubd_probe/crawler/.venv/Scripts/python.exe -m pytest tests/test_api_client.py::test_auto_block_host_posts_host -v` (from `crawler/`)
Expected: FAIL — `AttributeError: 'ApiClient' object has no attribute 'auto_block_host'`.

- [ ] **Step 3: Implement the method**

In `crawler/crawler/api_client.py`, after `list_blocked_hosts`:

```python
    def auto_block_host(self, host: str, sample_url: str | None = None) -> dict:
        r = self._client.post("/api/internal/blocked-hosts",
                              json={"host": host, "sample_url": sample_url})
        r.raise_for_status()
        return r.json()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/d/ubd_probe/crawler/.venv/Scripts/python.exe -m pytest tests/test_api_client.py::test_auto_block_host_posts_host -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/api_client.py crawler/tests/test_api_client.py
git commit -m "feat(crawler): ApiClient.auto_block_host posts to internal blocked-hosts

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: `blocklist.add_learned` (immediate runtime block)

**Files:**
- Modify: `crawler/crawler/discovery/blocklist.py:38-46` (near `reload_learned`)
- Test: `crawler/tests/test_blocklist.py`

**Interfaces:**
- Produces: `blocklist.add_learned(host: str | None) -> None` — unions one host into the runtime `_LEARNED` set so `is_blocked_host` drops it immediately this run.

- [ ] **Step 1: Write the failing test**

Add to `crawler/tests/test_blocklist.py`:

```python
def test_add_learned_blocks_host_immediately():
    blocklist.reload_learned(None)                       # SEED-only
    assert blocklist.is_blocked_host("newmedia.example") is False
    blocklist.add_learned("https://www.newmedia.example/ukr/x")
    assert blocklist.is_blocked_host("newmedia.example") is True
    assert blocklist.is_blocked_host("sub.newmedia.example") is True
    blocklist.add_learned("")                            # no-op, no crash
    blocklist.add_learned(None)                          # no-op, no crash
    blocklist.reload_learned(None)                       # cleanup for other tests
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/d/ubd_probe/crawler/.venv/Scripts/python.exe -m pytest tests/test_blocklist.py::test_add_learned_blocks_host_immediately -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'add_learned'`.

- [ ] **Step 3: Implement `add_learned`**

In `crawler/crawler/discovery/blocklist.py`, after `reload_learned`:

```python
def add_learned(host) -> None:
    """Incrementally union one host into the runtime learned set, so is_blocked_host
    drops it immediately within the current run (persistence is backend-side)."""
    global _LEARNED
    h = bare_host(host) if host and host.strip() else ""
    if h:
        _LEARNED = _LEARNED | frozenset({h})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/d/ubd_probe/crawler/.venv/Scripts/python.exe -m pytest tests/test_blocklist.py::test_add_learned_blocks_host_immediately -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/blocklist.py crawler/tests/test_blocklist.py
git commit -m "feat(crawler): blocklist.add_learned for immediate runtime host block

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: `DomainRegistry` media-streak

**Files:**
- Modify: `crawler/crawler/discovery/domain_registry.py:46-68` (`record` + new-entry dict), add `media_block_due`
- Test: `crawler/tests/test_domain_registry.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `record(host, offers, errors, structural_provider=False)`; `media_block_due(host, k) -> bool`. Entry gains `media_streak: int`, `provider_ever: bool`, `media_blocked: bool`.

- [ ] **Step 1: Write the failing tests**

Add to `crawler/tests/test_domain_registry.py`:

```python
def test_media_streak_blocks_after_k_offer_only_crawls(tmp_path):
    r = _reg(tmp_path)
    for _ in range(3):
        r.record("dumka.media", offers=1, errors=0, structural_provider=False)
    assert r.media_block_due("dumka.media", k=3) is True
    # flag set → not due again (no re-post)
    assert r.media_block_due("dumka.media", k=3) is False

def test_structural_provider_resets_and_vetoes(tmp_path):
    r = _reg(tmp_path)
    r.record("shop.ua", offers=1, errors=0, structural_provider=False)
    r.record("shop.ua", offers=1, errors=0, structural_provider=True)   # business schema seen
    r.record("shop.ua", offers=1, errors=0, structural_provider=False)
    r.record("shop.ua", offers=1, errors=0, structural_provider=False)
    assert r.media_block_due("shop.ua", k=3) is False                   # provider_ever vetoes

def test_empty_crawls_do_not_grow_media_streak(tmp_path):
    r = _reg(tmp_path)
    for _ in range(5):
        r.record("quiet.ua", offers=0, errors=0, structural_provider=False)
    assert r.media_block_due("quiet.ua", k=3) is False

def test_media_block_due_unknown_host_false(tmp_path):
    r = _reg(tmp_path)
    assert r.media_block_due("nope.ua", k=3) is False

def test_record_back_compat_positional(tmp_path):
    r = _reg(tmp_path)
    r.record("x.ua", 1, 0)                       # old 3-arg call still works
    assert r.score("x.ua") == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/d/ubd_probe/crawler/.venv/Scripts/python.exe -m pytest tests/test_domain_registry.py -k "media_streak or structural_provider or empty_crawls or media_block_due or back_compat" -v`
Expected: FAIL — `TypeError: record() got an unexpected keyword argument 'structural_provider'` / `AttributeError: media_block_due`.

- [ ] **Step 3: Implement the streak**

In `crawler/crawler/discovery/domain_registry.py`, change the `record` signature and new-entry dict, and add streak logic at the end of `record`; then add `media_block_due`:

```python
    def record(self, host, offers, errors, structural_provider=False):
        host = _host(host)
        if not host:
            return
        now = self._clock()
        e = self._data["domains"].get(host)
        if e is None:
            e = {"score": 0.0, "offers": 0, "errors": 0, "rejects": 0, "passes": 0,
                 "empty_passes": 0, "skip_left": 0, "first_seen": now, "last_seen": now,
                 "last_offer": 0.0, "media_streak": 0, "provider_ever": False,
                 "media_blocked": False}
            self._data["domains"][host] = e
        e["score"] = max(0.0, e["score"] * self._decay
                         + offers * self._offer_w - errors * self._error_w)
        e["offers"] += int(offers)
        e["errors"] += int(errors)
        e["passes"] += 1
        if offers == 0:
            e["empty_passes"] += 1
            e["skip_left"] = self._empty_skip   # empty pass → skip the host's next N crawls
        else:
            e["last_offer"] = now
            e["skip_left"] = 0                   # productive again → resume normal cadence
        # media-streak: a host that keeps producing offers but never declares itself a
        # business (no Offer/LocalBusiness schema) behaves like media/aggregator.
        if structural_provider:
            e["provider_ever"] = True
            e["media_streak"] = 0
        elif offers > 0:
            e["media_streak"] = e.get("media_streak", 0) + 1
        e["last_seen"] = now

    def media_block_due(self, host, k) -> bool:
        """True exactly once, when the host has produced offers in >= k crawls without
        ever showing structural provider-evidence. Sets media_blocked so it never re-fires."""
        e = self._data["domains"].get(_host(host))
        if not e or e.get("provider_ever") or e.get("media_blocked"):
            return False
        if e.get("media_streak", 0) >= int(k):
            e["media_blocked"] = True
            return True
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/d/ubd_probe/crawler/.venv/Scripts/python.exe -m pytest tests/test_domain_registry.py -v`
Expected: PASS (all, including pre-existing ones).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/domain_registry.py crawler/tests/test_domain_registry.py
git commit -m "feat(crawler): DomainRegistry media-streak + media_block_due

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: `MediaAutoBlocker`

**Files:**
- Create: `crawler/crawler/discovery/media_autoblock.py`
- Test: `crawler/tests/test_media_autoblock.py` (create)

**Interfaces:**
- Consumes: `ApiClient.auto_block_host` (Task 2); `blocklist.add_learned` (Task 3).
- Produces: `MediaAutoBlocker(api).block(host: str, sample_url: str | None = None) -> None`.

- [ ] **Step 1: Write the failing test**

Create `crawler/tests/test_media_autoblock.py`:

```python
from crawler.discovery import blocklist
from crawler.discovery.media_autoblock import MediaAutoBlocker


class FakeApi:
    def __init__(self, boom=False):
        self.calls = []
        self._boom = boom
    def auto_block_host(self, host, sample_url=None):
        self.calls.append((host, sample_url))
        if self._boom:
            raise RuntimeError("network down")
        return {"host": host, "status": "approved"}


def test_block_calls_api_and_runtime_blocklist():
    blocklist.reload_learned(None)
    api = FakeApi()
    MediaAutoBlocker(api).block("dumka.media", "https://dumka.media/x")
    assert api.calls == [("dumka.media", "https://dumka.media/x")]
    assert blocklist.is_blocked_host("dumka.media") is True
    blocklist.reload_learned(None)


def test_block_swallows_api_error_and_skips_runtime_add():
    blocklist.reload_learned(None)
    api = FakeApi(boom=True)
    MediaAutoBlocker(api).block("flaky.example")     # must not raise
    assert blocklist.is_blocked_host("flaky.example") is False
    blocklist.reload_learned(None)


def test_block_ignores_empty_host():
    api = FakeApi()
    MediaAutoBlocker(api).block("")
    assert api.calls == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/d/ubd_probe/crawler/.venv/Scripts/python.exe -m pytest tests/test_media_autoblock.py -v`
Expected: FAIL — `ModuleNotFoundError: crawler.discovery.media_autoblock`.

- [ ] **Step 3: Implement `MediaAutoBlocker`**

Create `crawler/crawler/discovery/media_autoblock.py`:

```python
"""Escalate a per-host media signal to a persistent no-fetch block: push the host to
the backend blocked_hosts table (approved, system) and add it to the runtime blocklist
so it drops immediately this run. Best-effort: a failed backend call is logged, not raised,
and the runtime add is skipped so the next crawl retries the block."""

import logging

from crawler.discovery import blocklist

log = logging.getLogger(__name__)


class MediaAutoBlocker:
    def __init__(self, api):
        self._api = api

    def block(self, host, sample_url=None) -> None:
        if not host:
            return
        try:
            self._api.auto_block_host(host, sample_url)
        except Exception as exc:  # noqa: BLE001 — block must never sink the run
            log.warning("media auto-block failed for %s: %s", host, exc)
            return
        blocklist.add_learned(host)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/d/ubd_probe/crawler/.venv/Scripts/python.exe -m pytest tests/test_media_autoblock.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/media_autoblock.py crawler/tests/test_media_autoblock.py
git commit -m "feat(crawler): MediaAutoBlocker — persist + runtime-block a media host

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Harvest wiring — detect + block

**Files:**
- Modify: `crawler/crawler/discovery/harvest.py` (`__init__` 20-40, `harvest` 82-96, `_harvest_one` 114-124, `_process_page` 126-148)
- Test: `crawler/tests/test_active_harvest.py`

**Interfaces:**
- Consumes: `DomainRegistry.record(..., structural_provider=)` and `media_block_due` (Task 4); `MediaAutoBlocker.block` (Task 5).
- Produces: `ActiveHarvester(..., media_blocker=None, media_autoblock_crawls=3)`; `_process_page(...) -> bool` (structural_provider seen); `_harvest_one(...) -> bool`.

- [ ] **Step 1: Write the failing integration test**

Add to `crawler/tests/test_active_harvest.py`. Extend the `_item` helper usage with schema flags (RawItem already has `has_offer_schema`/`has_business_schema` fields):

```python
from crawler.discovery import blocklist
from crawler.discovery.domain_registry import DomainRegistry


class FakeBlocker:
    def __init__(self): self.blocked = []
    def block(self, host, sample_url=None): self.blocked.append(host)


def _schema_item(text, url, business=False, offer_schema=False):
    return RawItem(source_id=None, platform="website", key=text[:8], text=text,
                   url=url, links=[], has_business_schema=business,
                   has_offer_schema=offer_schema)


def _reg(tmp_path):
    return DomainRegistry(str(tmp_path / "reg.json"))


def test_media_host_blocked_after_k_crawls(tmp_path):
    blocklist.reload_learned(None)
    api = FakeApi()
    reg = _reg(tmp_path)
    blocker = FakeBlocker()
    # produces an offer ('%'), zero business/offer schema → media behaviour
    fetcher = FakeFetcher([_schema_item("Знижка 20% для військових",
                                        "https://dumka.media/ukr/a")])
    h = ActiveHarvester(api, {"website": fetcher}, GateExtractor(), rate_limiter=None,
                        fetch_budget=5, domain_registry=reg, media_blocker=blocker,
                        media_autoblock_crawls=3)
    for _ in range(3):
        h.harvest([_cand(url="https://dumka.media")], cats=None, known=set(),
                  summary=_summary())
    assert blocker.blocked == ["dumka.media"]
    blocklist.reload_learned(None)


def test_business_with_schema_never_blocked(tmp_path):
    blocklist.reload_learned(None)
    api = FakeApi()
    reg = _reg(tmp_path)
    blocker = FakeBlocker()
    fetcher = FakeFetcher([_schema_item("Знижка 20% для військових",
                                        "https://shop.ua/sale", business=True)])
    h = ActiveHarvester(api, {"website": fetcher}, GateExtractor(), rate_limiter=None,
                        fetch_budget=5, domain_registry=reg, media_blocker=blocker,
                        media_autoblock_crawls=3)
    for _ in range(5):
        h.harvest([_cand(url="https://shop.ua")], cats=None, known=set(), summary=_summary())
    assert blocker.blocked == []
    blocklist.reload_learned(None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/d/ubd_probe/crawler/.venv/Scripts/python.exe -m pytest tests/test_active_harvest.py -k "media_host_blocked or business_with_schema" -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'media_blocker'`.

- [ ] **Step 3: Add constructor params**

In `crawler/crawler/discovery/harvest.py`, extend `ActiveHarvester.__init__` params and assignments (add after `geo_block_store=None` param / `self._geo_block_store` line):

```python
                 geo_block_store=None, media_blocker=None, media_autoblock_crawls=3):
```
```python
        self._geo_block_store = geo_block_store
        self._media_blocker = media_blocker
        self._media_autoblock_crawls = media_autoblock_crawls
```

- [ ] **Step 4: Make `_process_page` return structural_provider**

In `_process_page`, compute the flag at the top from the raw `items` and return it at every exit:

```python
    def _process_page(self, cand, items, cats, known, summary) -> bool:
        structural_provider = any(
            getattr(it, "has_offer_schema", False) or getattr(it, "has_business_schema", False)
            for it in items)
        passing = []
        for it in items:
            is_offer = self._extractor.extract(it, "", cats) is not None
            if self._corpus is not None:
                self._corpus.record(it, is_offer)
            if is_offer:
                passing.append(it)
        ctx = build_page_ctx(cand, passing)
        if self._aggregator_store is not None and is_blocked_host(ctx.host):
            hosts = _outbound_hosts(passing)
            if hosts:
                self._aggregator_store.add(hosts, self._aggregator_max_domains)
        collected = []
        for item in passing:
            attr = attribute(item, ctx, hardening_enabled=self._hardening_enabled,
                             aggregator_min_outbound=self._aggregator_min_outbound)
            if attr is None:
                continue
            offer = self._extractor.extract(item, attr.provider, cats)
            collected.append((offer, attr))
        if not collected:
            return structural_provider
        # ... (existing grouping / submit / suggestion loop UNCHANGED) ...
```

At the **end** of `_process_page` (after the existing suggestion loop), add `return structural_provider`. Do not change any submit/grouping logic in between.

- [ ] **Step 5: Make `_harvest_one` aggregate and return the flag**

Replace `_harvest_one`:

```python
    def _harvest_one(self, cand, fetcher, cats, known, summary) -> bool:
        urls, domain, delay = self._plan(cand)
        structural = False
        for url in urls:
            self._wait(cand.type, domain, delay)
            src = {"id": None, "type": cand.type, "url_or_handle": url, "name": cand.name}
            try:
                items, _ = fetcher.fetch(src, None)
                if self._process_page(cand, items, cats, known, summary):
                    structural = True
            except Exception as exc:  # noqa: BLE001 — one page must not sink the domain
                summary["errors"] += 1
                log.warning("harvest page failed for %s: %s", url, exc)
        return structural
```

- [ ] **Step 6: Thread the flag into `record` and fire the blocker**

In `harvest()`, replace the harvest-one call + record block (lines ~86-95):

```python
            before_o, before_e = summary["offers"], summary["errors"]
            structural = False
            try:
                structural = self._harvest_one(cand, fetcher, cats, known, summary)
            except Exception as exc:  # noqa: BLE001 — isolate per candidate
                summary["errors"] += 1
                log.warning("active harvest failed for %s: %s", cand.url_or_handle, exc)
            if self._registry is not None and cand.type == "website":
                host = _host(cand.url_or_handle)
                self._registry.record(host, summary["offers"] - before_o,
                                      summary["errors"] - before_e,
                                      structural_provider=structural)
                if (self._media_blocker is not None
                        and self._registry.media_block_due(host, self._media_autoblock_crawls)):
                    self._media_blocker.block(host, cand.url_or_handle)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `/d/ubd_probe/crawler/.venv/Scripts/python.exe -m pytest tests/test_active_harvest.py -v`
Expected: PASS (new + all pre-existing harvest tests).

- [ ] **Step 8: Commit**

```bash
git add crawler/crawler/discovery/harvest.py crawler/tests/test_active_harvest.py
git commit -m "feat(crawler): harvest detects media host and fires auto-block

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: Config + wiring

**Files:**
- Modify: `crawler/crawler/config.py` (3 sites: `_RawSettings` ~106, dataclass `Config` ~212, `from_settings` mapping ~341)
- Modify: `crawler/crawler/wiring.py:164-221`

**Interfaces:**
- Consumes: `MediaAutoBlocker` (Task 5); `ActiveHarvester(media_blocker=, media_autoblock_crawls=)` (Task 6).
- Produces: config `media_autoblock_enabled: bool = True`, `media_autoblock_crawls: int = 2`.

- [ ] **Step 1: Add config fields (all three sites)**

In `crawler/crawler/config.py`, add after the `host_miner_media_min` line in **`_RawSettings`** (~line 106):

```python
    media_autoblock_enabled: bool = True
    media_autoblock_crawls: int = 2
```

Add the identical two lines after `host_miner_media_min` in the dataclass **`Config`** (~line 212).

In the **`from_settings`** mapping (~after `host_miner_media_min=s.host_miner_media_min,`):

```python
        media_autoblock_enabled=s.media_autoblock_enabled,
        media_autoblock_crawls=s.media_autoblock_crawls,
```

- [ ] **Step 2: Construct the blocker and wire it in**

In `crawler/crawler/wiring.py`, immediately before the `if (... and config.active_fetch_budget):` harvester block (~line 207), add:

```python
    media_blocker = None
    if domain_registry is not None and config.media_autoblock_enabled:
        from crawler.discovery.media_autoblock import MediaAutoBlocker
        media_blocker = MediaAutoBlocker(api)
```

Then in the `ActiveHarvester(...)` call, add two kwargs after `geo_block_store=geo_block_store`:

```python
                                    geo_block_store=geo_block_store,
                                    media_blocker=media_blocker,
                                    media_autoblock_crawls=config.media_autoblock_crawls)
```

- [ ] **Step 2b: Align the ActiveHarvester default to 2**

Task 6 left the `ActiveHarvester.__init__` fallback default as `media_autoblock_crawls=3`. Change that single default to `2` so the never-overridden fallback matches the config default (production always passes `config.media_autoblock_crawls`, so this is a consistency fix, not a behaviour change):

In `crawler/crawler/discovery/harvest.py`, in `ActiveHarvester.__init__`, change `media_autoblock_crawls=3` → `media_autoblock_crawls=2`. Do NOT change the Task-6 integration test that passes `media_autoblock_crawls=3` explicitly and loops 3× — that is a valid explicit-K mechanism test and stays as-is.

- [ ] **Step 3: Run the full crawler suite (no regressions, wiring imports resolve)**

Run: `/d/ubd_probe/crawler/.venv/Scripts/python.exe -m pytest -q` (from `crawler/`)
Expected: PASS — full suite green.

- [ ] **Step 4: Sanity-check wiring builds**

Run: `/d/ubd_probe/crawler/.venv/Scripts/python.exe -c "import crawler.wiring, crawler.config; print('wiring import ok')"` (from `crawler/`)
Expected: prints `wiring import ok` with no ImportError.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/config.py crawler/crawler/wiring.py crawler/crawler/discovery/harvest.py
git commit -m "feat(crawler): wire MediaAutoBlocker + media_autoblock config (K=2)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: Full-suite verification + docs

**Files:**
- Modify: `crawler/.env.example` (document new toggles)

- [ ] **Step 1: Document the toggles**

In `crawler/.env.example`, add near the other tuning knobs:

```
# Media host auto-block: after this many crawls that produced offers but never carried
# Offer/LocalBusiness schema, block the whole host from further crawling. 0/false to disable.
MEDIA_AUTOBLOCK_ENABLED=true
MEDIA_AUTOBLOCK_CRAWLS=2
```

- [ ] **Step 2: Run both full suites**

Run (from `crawler/`): `/d/ubd_probe/crawler/.venv/Scripts/python.exe -m pytest -q`
Run (from `backend/`): `/d/ubd_probe/backend/.venv/Scripts/python.exe -m pytest -q`
Expected: both green (backend may show the one known `StarletteDeprecationWarning`).

- [ ] **Step 3: Commit**

```bash
git add crawler/.env.example
git commit -m "docs(crawler): document MEDIA_AUTOBLOCK_* env toggles

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Notes for the executor

- **Deploy:** crawler changes require a crawler container rebuild to take effect (same as prior tracks). Not part of this plan's commits.
- **Existing queue:** offers already discovered from a media host are not removed by this work — admin removes them (bulk-reject). Future crawls of that host stop once blocked.
- **Merge:** when all tasks pass, follow `superpowers:finishing-a-development-branch` to merge `track-media-autoblock` back into `main`.
