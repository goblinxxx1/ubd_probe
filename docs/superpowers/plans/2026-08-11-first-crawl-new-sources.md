# Prompt First-Crawl of New Sources — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Crawl never-crawled active website sources promptly (within one active pass, DDG-independent) instead of waiting up to the 96h passive cadence, so a newly-approved source's discount reaches moderation fast.

**Architecture:** A read-only backend endpoint lists active website sources with `last_crawled_at IS NULL`. The crawler's `run_active` calls a new bounded `Runner.run_first_crawl(budget)` that crawls up to `budget` of them through the existing passive deep-walk path; each crawled source gets a crawl-state row and drops out (self-draining). A per-source failure is marked attempted so it can't loop the budget.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, pytest, httpx.

## Global Constraints

- Backend tests run from `backend/` with the Windows venv: `./.venv/Scripts/python.exe -m pytest -q` (needs `mysql-container` on :3306 — `docker start mysql-container`).
- Crawler tests run from `crawler/`: `./.venv/Scripts/python.exe -m pytest -q`.
- TDD: failing test first, minimal impl, green, commit.
- `first_crawl_budget` default **10** in config (live); the **Runner constructor default is 0** (disabled) so existing runner tests are byte-unaffected. `0` disables the trigger.
- First-crawl is **DDG-independent** — `run_active` invokes it regardless of `ddg_allowed` (fires during backoff too).
- Scope: **website sources only**. No DB migration (`Source.last_crawled_at` already exists). Mark-attempted (`set_crawl_state(id, None)`) happens **only on the exception path** — never overwrite a successful crawl's real key. No new dependencies.

---

### Task 1: Backend `uncrawled` sources endpoint

**Files:**
- Modify: `backend/app/crud/source.py`
- Modify: `backend/app/routers/internal.py:30-32` (add route beside `list_sources`)
- Test: `backend/tests/test_crawl_state.py`

**Interfaces:**
- Produces: `GET /api/internal/sources/uncrawled?limit=N` → `list[SourceOut]` — active `type=website` sources with `last_crawled_at IS NULL`, ordered by `id`, capped at `limit`. `source_crud.list_uncrawled_website_sources(db, limit) -> list[Source]`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_crawl_state.py`:

```python
def test_uncrawled_lists_active_website_never_crawled(client, db_session):
    from datetime import datetime, timezone
    from app.models.enums import CreatedBy, SourceType

    def mk(name, url, active=True, type=SourceType.website, crawled=False):
        s = Source(name=name, type=type, url_or_handle=url, is_active=active,
                   created_by=CreatedBy.admin)
        if crawled:
            s.last_crawled_at = datetime.now(timezone.utc)
        db_session.add(s); db_session.commit(); db_session.refresh(s)
        return s

    a = mk("A", "http://a")                       # active website, never crawled -> IN
    mk("B", "http://b", crawled=True)             # already crawled -> OUT
    mk("C", "http://c", active=False)             # inactive -> OUT
    mk("D", "tg://d", type=SourceType.telegram)   # non-website -> OUT
    e = mk("E", "http://e")                       # active website, never crawled -> IN

    h = {"X-API-Key": settings.crawler_api_key}
    r = client.get("/api/internal/sources/uncrawled?limit=10", headers=h)
    assert r.status_code == 200
    assert [s["id"] for s in r.json()] == [a.id, e.id]   # only uncrawled active website, id order


def test_uncrawled_respects_limit(client, db_session):
    from app.models.enums import CreatedBy, SourceType
    ids = []
    for i in range(3):
        s = Source(name=f"S{i}", type=SourceType.website, url_or_handle=f"http://s{i}",
                   is_active=True, created_by=CreatedBy.admin)
        db_session.add(s); db_session.commit(); db_session.refresh(s)
        ids.append(s.id)
    h = {"X-API-Key": settings.crawler_api_key}
    r = client.get("/api/internal/sources/uncrawled?limit=2", headers=h)
    assert [s["id"] for s in r.json()] == ids[:2]        # first two by id


def test_uncrawled_requires_api_key(client, db_session):
    assert client.get("/api/internal/sources/uncrawled").status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`): `./.venv/Scripts/python.exe -m pytest tests/test_crawl_state.py -q -k uncrawled`
Expected: FAIL — 404 (route not defined) so `[s["id"] ...]` assertion errors / status 404.

- [ ] **Step 3: Add the crud query**

In `backend/app/crud/source.py`, add (after `list_sources`):

```python
def list_uncrawled_website_sources(db: Session, limit: int):
    return (db.query(Source)
            .filter(Source.is_active.is_(True),
                    Source.type == SourceType.website,
                    Source.last_crawled_at.is_(None))
            .order_by(Source.id)
            .limit(limit)
            .all())
```

- [ ] **Step 4: Add the route**

In `backend/app/routers/internal.py`, add immediately after the `list_sources` route (after line 32):

```python
@router.get("/sources/uncrawled", response_model=list[SourceOut])
def list_uncrawled_sources(limit: int = 10, db: Session = Depends(get_db)):
    return source_crud.list_uncrawled_website_sources(db, limit)
```

- [ ] **Step 5: Run tests to verify they pass**

Run (from `backend/`): `./.venv/Scripts/python.exe -m pytest tests/test_crawl_state.py -q`
Expected: PASS — all crawl-state tests green (new uncrawled tests + existing roundtrip).

- [ ] **Step 6: Commit**

```bash
git add backend/app/crud/source.py backend/app/routers/internal.py backend/tests/test_crawl_state.py
git commit -m "feat(backend): GET /internal/sources/uncrawled — active website sources never crawled"
```

---

### Task 2: Crawler client `list_uncrawled_sources`

**Files:**
- Modify: `crawler/crawler/api_client.py`
- Test: `crawler/tests/test_api_client.py`

**Interfaces:**
- Consumes: `GET /api/internal/sources/uncrawled?limit=N` (Task 1).
- Produces: `ApiClient.list_uncrawled_sources(limit: int) -> list[dict]`.

- [ ] **Step 1: Write the failing test**

In `crawler/tests/test_api_client.py`, add a handler branch inside `_handler`'s `handle` (before the final `return httpx.Response(404, ...)`):

```python
        if request.url.path == "/api/internal/sources/uncrawled":
            return httpx.Response(200, json=[{"id": 2, "type": "website",
                                              "url_or_handle": "http://y", "name": "Y"}])
```

and add the test:

```python
def test_list_uncrawled_sources_sends_limit_and_key():
    captured = []
    client = ApiClient("http://api", "secret", 10.0,
                       transport=httpx.MockTransport(_handler(captured)))
    out = client.list_uncrawled_sources(7)
    assert out[0]["id"] == 2
    assert captured[0].headers["X-API-Key"] == "secret"
    assert captured[0].url.params.get("limit") == "7"
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `crawler/`): `./.venv/Scripts/python.exe -m pytest tests/test_api_client.py -q -k uncrawled`
Expected: FAIL — `AttributeError: 'ApiClient' object has no attribute 'list_uncrawled_sources'`.

- [ ] **Step 3: Add the client method**

In `crawler/crawler/api_client.py`, add after `list_sources` (near line 27):

```python
    def list_uncrawled_sources(self, limit: int) -> list[dict]:
        r = self._client.get("/api/internal/sources/uncrawled", params={"limit": limit})
        r.raise_for_status()
        return r.json()
```

- [ ] **Step 4: Run test to verify it passes**

Run (from `crawler/`): `./.venv/Scripts/python.exe -m pytest tests/test_api_client.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/api_client.py crawler/tests/test_api_client.py
git commit -m "feat(crawler): ApiClient.list_uncrawled_sources(limit)"
```

---

### Task 3: `Runner.run_first_crawl` + `run_active` integration

**Files:**
- Modify: `crawler/crawler/runner.py` (constructor + `run_active` + new method)
- Test: `crawler/tests/test_first_crawl.py` (new)

**Interfaces:**
- Consumes: `ApiClient.list_uncrawled_sources(limit)` (Task 2); existing `Runner._crawl_source(source, cats, known, summary)`.
- Produces: `Runner.__init__(..., first_crawl_budget: int = 0)`; `Runner.run_first_crawl(budget) -> dict`; `run_active` folds `run_first_crawl` output into its summary when `first_crawl_budget > 0`.

- [ ] **Step 1: Write the failing tests**

Create `crawler/tests/test_first_crawl.py`:

```python
from crawler.runner import Runner


def _src(i, type="website"):
    return {"id": i, "type": type, "name": f"S{i}", "url_or_handle": f"https://s{i}.example"}


class FakeApi:
    def __init__(self, uncrawled):
        self._uncrawled = list(uncrawled)
        self.uncrawled_limit = None
        self.uncrawled_called = False
        self.set_crawl_state_calls = []
    def list_uncrawled_sources(self, limit):
        self.uncrawled_called = True
        self.uncrawled_limit = limit
        return list(self._uncrawled)
    def list_target_categories(self): return []
    def list_offer_categories(self): return []
    def list_sources(self, is_active=True): return []
    def set_crawl_state(self, source_id, last_seen_key):
        self.set_crawl_state_calls.append((source_id, last_seen_key)); return {}


class _Harv:
    def harvest(self, *a, **k): return 0


class _RecordingRunner(Runner):
    """Overrides the real deep-walk with a recorder so run_first_crawl orchestration is
    tested in isolation from the walker/fetcher machinery."""
    def __init__(self, *a, fail_ids=(), **k):
        super().__init__(*a, **k)
        self.crawled = []
        self._fail_ids = set(fail_ids)
    def _crawl_source(self, source, cats, known, summary):
        self.crawled.append(source["id"])
        if source["id"] in self._fail_ids:
            raise RuntimeError("boom")
        summary["offers"] += 1


def test_first_crawl_crawls_up_to_budget():
    api = FakeApi([_src(1), _src(2)])
    r = _RecordingRunner(api, {}, None, None, harvester=_Harv())
    s = r.run_first_crawl(5)
    assert r.crawled == [1, 2]
    assert api.uncrawled_limit == 5
    assert s["offers"] == 2 and s["sources"] == 2


def test_first_crawl_marks_attempted_on_failure_and_isolates():
    api = FakeApi([_src(1), _src(2), _src(3)])
    r = _RecordingRunner(api, {}, None, None, harvester=_Harv(), fail_ids={2})
    s = r.run_first_crawl(5)
    assert r.crawled == [1, 2, 3]                     # all attempted; #2 failure isolated
    assert api.set_crawl_state_calls == [(2, None)]   # only the failed one marked attempted
    assert s["errors"] == 1 and s["offers"] == 2


def test_first_crawl_budget_zero_is_noop():
    api = FakeApi([_src(1)])
    r = _RecordingRunner(api, {}, None, None, harvester=_Harv())
    assert r.run_first_crawl(0) == r._empty_summary()
    assert r.crawled == [] and api.uncrawled_called is False


def test_first_crawl_empty_list_is_noop():
    api = FakeApi([])
    r = _RecordingRunner(api, {}, None, None, harvester=_Harv())
    s = r.run_first_crawl(5)
    assert r.crawled == [] and s == r._empty_summary()
    assert api.uncrawled_called is True


def test_run_active_runs_first_crawl_in_both_ddg_modes():
    for ddg in (True, False):
        api = FakeApi([_src(1)])
        r = _RecordingRunner(api, {}, None, None, harvester=_Harv(), first_crawl_budget=5)
        r.run_active(ddg_allowed=ddg)
        assert r.crawled == [1]


def test_run_active_skips_first_crawl_when_budget_zero():
    api = FakeApi([_src(1)])
    r = _RecordingRunner(api, {}, None, None, harvester=_Harv(), first_crawl_budget=0)
    r.run_active(ddg_allowed=True)
    assert r.crawled == [] and api.uncrawled_called is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `crawler/`): `./.venv/Scripts/python.exe -m pytest tests/test_first_crawl.py -q`
Expected: FAIL — `run_first_crawl` undefined / `first_crawl_budget` not accepted (TypeError).

- [ ] **Step 3: Add the constructor knob**

In `crawler/crawler/runner.py`, add `first_crawl_budget=0` to the end of `__init__`'s signature (after `reject_ingestor=None`):

```python
                 reject_ingestor=None, first_crawl_budget=0):
```

and store it (after `self._reject_ingestor = reject_ingestor`):

```python
        self._first_crawl_budget = first_crawl_budget
```

- [ ] **Step 4: Add `run_first_crawl` and wire it into `run_active`**

In `crawler/crawler/runner.py`, add the method (place it after `run_active`, before `_mark_consumed_search_phrases`):

```python
    def run_first_crawl(self, budget) -> dict:
        """Crawl up to `budget` never-crawled active website sources NOW — the same passive
        deep-walk path, but without waiting for the rare passive cadence. DDG-independent. A
        source whose crawl raises is marked attempted (set_crawl_state None) so it drops out of
        'uncrawled' and cannot loop the budget; the next passive cycle re-crawls it fresh."""
        summary = self._empty_summary()
        if budget <= 0:
            return summary
        try:
            sources = self._api.list_uncrawled_sources(budget)
        except Exception as exc:  # noqa: BLE001 — first-crawl must not crash the pass
            summary["errors"] += 1
            log.warning("first-crawl: list uncrawled failed: %s", exc)
            return summary
        if not sources:
            return summary
        cats = CategoryIndex(self._api.list_target_categories(),
                             self._api.list_offer_categories())
        known = {normalize_ref(s["type"], s["url_or_handle"])
                 for s in self._api.list_sources(is_active=True)}
        for source in sources:
            summary["sources"] += 1
            try:
                self._crawl_source(source, cats, known, summary)
            except Exception as exc:  # noqa: BLE001 — isolate per source
                summary["errors"] += 1
                log.warning("first-crawl source #%s failed: %s", source.get("id"), exc)
                try:
                    self._api.set_crawl_state(source["id"], None)   # mark attempted -> no loop
                except Exception as exc2:  # noqa: BLE001 — mark is best-effort
                    log.warning("first-crawl mark-attempted #%s failed: %s",
                                source.get("id"), exc2)
        return summary
```

Then, in `run_active`, insert the invocation right before the final `return summary` (after the `finally` block that prunes the domain registry):

```python
        if self._first_crawl_budget > 0:
            fc = self.run_first_crawl(self._first_crawl_budget)
            for k in fc:
                summary[k] = summary.get(k, 0) + fc[k]
        return summary
```

- [ ] **Step 5: Run tests to verify they pass**

Run (from `crawler/`): `./.venv/Scripts/python.exe -m pytest tests/test_first_crawl.py tests/test_runner_discovery.py tests/test_runner.py -q`
Expected: PASS — new first-crawl tests green; existing runner tests unaffected (constructor default `first_crawl_budget=0` keeps `run_active` from invoking it).

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/runner.py crawler/tests/test_first_crawl.py
git commit -m "feat(crawler): Runner.run_first_crawl — prompt first-crawl of never-crawled sources"
```

---

### Task 4: Config knob + wiring (make it live)

**Files:**
- Modify: `crawler/crawler/config.py` (3 spots: settings, Config, builder)
- Modify: `crawler/crawler/wiring.py:215-224` (Runner construction)
- Test: `crawler/tests/test_wiring.py`

**Interfaces:**
- Consumes: `Runner(..., first_crawl_budget=...)` (Task 3).
- Produces: `config.first_crawl_budget` (default 10) flowing to `runner._first_crawl_budget`.

- [ ] **Step 1: Write the failing test**

In `crawler/tests/test_wiring.py`, add:

```python
def test_wiring_sets_first_crawl_budget(monkeypatch):
    from crawler.config import load_config
    from crawler.wiring import build_runner
    cfg = load_config()
    runner = build_runner(cfg)
    assert runner._first_crawl_budget == cfg.first_crawl_budget
    assert cfg.first_crawl_budget == 10          # live default
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `crawler/`): `./.venv/Scripts/python.exe -m pytest tests/test_wiring.py -q -k first_crawl`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'first_crawl_budget'` (or `runner._first_crawl_budget == 0 != 10`).

- [ ] **Step 3: Add the config field (3 spots)**

In `crawler/crawler/config.py`:

Settings class — after `active_fetch_budget: int = 80` (near line 32):

```python
    first_crawl_budget: int = 10
```

Config dataclass — after `active_fetch_budget: int = 80` (near line 135):

```python
    first_crawl_budget: int = 10
```

Builder mapping — after `active_fetch_budget=s.active_fetch_budget,` (near line 261):

```python
        first_crawl_budget=s.first_crawl_budget,
```

- [ ] **Step 4: Pass it through wiring**

In `crawler/crawler/wiring.py`, add to the `Runner(...)` construction (in the keyword block near line 215-224):

```python
                  first_crawl_budget=config.first_crawl_budget,
```

- [ ] **Step 5: Run test to verify it passes + full crawler suite**

Run (from `crawler/`): `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — entire crawler suite green including the new wiring test.

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/config.py crawler/crawler/wiring.py crawler/tests/test_wiring.py
git commit -m "feat(crawler): first_crawl_budget config knob (default 10) wired to Runner"
```

---

### Task 5: Deploy + live verification (edclinic gets an offer)

**Files:** none (Docker rebuild + live checks).

**Interfaces:** Consumes: merged branch on `main`.

- [ ] **Step 1: Merge the branch (after review)**

```bash
git checkout main && git merge --ff-only feat/first-crawl-new-sources
```

- [ ] **Step 2: Canonical rebuild + restart backend and crawler**

```bash
docker compose build backend crawler && docker compose up -d backend crawler
```
Expected: clean build; both `Up`.

- [ ] **Step 3: Confirm the endpoint returns the uncrawled backlog**

```bash
docker exec ubd_probe-crawler-1 python -c "import os,httpx; c=httpx.Client(); r=c.get('http://backend:8000/api/internal/sources/uncrawled', params={'limit':50}, headers={'X-API-Key': os.environ['CRAWLER_API_KEY']}); print('uncrawled:', [s['url_or_handle'] for s in r.json()])"
```
Expected: a list including `https://edclinic.com.ua` (and the other never-crawled sources).

- [ ] **Step 4: Let a few active passes run, then confirm first-crawl consumed the backlog**

Wait for the crawler to run a few active passes (first-crawl runs every pass, budget 10, including during DDG backoff), then:

```bash
docker exec ubd_probe-db-1 mysql -uroot -pmy-secret-pw -N ubd -e "SELECT COUNT(*) FROM source_crawl_state;"
docker exec ubd_probe-db-1 mysql -uroot -pmy-secret-pw -N ubd -e "SELECT id,status,site_url FROM offers WHERE site_url LIKE '%edclinic%' OR article_url LIKE '%edclinic%';"
```
Expected: `source_crawl_state` count climbs from 0 toward the number of website sources (backlog draining); an `edclinic` offer row now exists (status `pending_review`), confirming its −15% discount reached moderation. Cross-check the admin queue.

- [ ] **Step 5: Confirm no breakage**

```bash
docker logs --since 15m ubd_probe-crawler-1 2>&1 | grep -aiE "first-crawl|traceback|error" | tail -20
```
Expected: no tracebacks; first-crawl proceeding; passes still complete and sleep normally.
