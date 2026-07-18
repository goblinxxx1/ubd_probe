# Active-Search Offer Harvesting (Variant A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the crawler's active search fetch found pages, attribute a provider, and submit offers straight to moderation (`source_id=None`), with source suggestions as a conditional by-product — instead of only proposing sources.

**Architecture:** A new `ActiveHarvester` orchestrates fetch → discount-gate → provider attribution → submit. Attribution is a pure heuristic (`attribute()`), combining first-party detection and named-provider extraction. The backend's `content_hash` dedup is extended to source-less crawler offers. Website + telegram only; Instagram/Facebook deferred.

**Tech Stack:** Python 3.12, httpx, selectolax, pydantic-settings, pytest (crawler); FastAPI, SQLAlchemy, pytest (backend).

## Global Constraints

- Zero-cost / offline runtime: no cloud LLM, no paid services. All tests use fakes — no network.
- Types harvested for now: **website + telegram** only. Instagram/Facebook results are ignored (not harvested, not suggested).
- An offer is created **only** when a provider is attributed; otherwise the block is skipped (no offer, no source).
- Source suggestions are emitted **only** as a by-product of a successful, attributed extraction.
- Fetch budget default: **20** page fetches per pass; `0` disables harvesting.
- Per-candidate errors are isolated (log + continue); harvesting never crashes the pass.
- Crawler tests run: `cd crawler && .venv/Scripts/python.exe -m pytest -q`.
- Backend tests run: `cd backend && .venv/Scripts/python.exe -m pytest -q`.
- Spec: `docs/superpowers/specs/2026-07-18-crawler-active-harvest-design.md`.

---

## File Structure

- `backend/app/crud/offer.py` — extend `content_hash` dedup to source-less crawler offers (modify).
- `backend/tests/test_internal.py` — dedup + rejected-not-resurrected tests (modify).
- `crawler/crawler/models.py` — `RawItem.site_name` field (modify).
- `crawler/crawler/fetchers/website.py` — populate `site_name` (modify).
- `crawler/tests/test_website_fetcher.py` — site_name test (modify).
- `crawler/crawler/discovery/attribution.py` — `PageCtx`, `Attribution`, `build_page_ctx`, `attribute` (create).
- `crawler/tests/test_attribution.py` — attribution unit tests (create).
- `crawler/crawler/payloads.py` — `offer_payload`, `suggestion_payload` moved out of runner (create).
- `crawler/crawler/discovery/harvest.py` — `ActiveHarvester` (create).
- `crawler/tests/test_active_harvest.py` — harvester tests (create).
- `crawler/crawler/runner.py` — import payloads; delegate active branch to harvester (modify).
- `crawler/tests/test_runner_discovery.py` — rewrite for harvester delegation (modify).
- `crawler/crawler/config.py` — `active_fetch_budget` (modify).
- `crawler/crawler/wiring.py` — build `ActiveHarvester` (modify).
- `crawler/.env.example` — `ACTIVE_FETCH_BUDGET` (modify).

---

## Task 1: Backend — content_hash dedup for source-less crawler offers

**Files:**
- Modify: `backend/app/crud/offer.py:24-30`
- Test: `backend/tests/test_internal.py`

**Interfaces:**
- Consumes: `create_offer(db, data, created_by, status, source_id=None, content_hash=None)` (existing).
- Produces: no signature change; behaviour: a repeated `content_hash` on a source-less crawler offer returns the existing row.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_internal.py`:

```python
def test_crawler_sourceless_offer_dedup_is_idempotent(client, db_session):
    body = {"type": "discount", "title": "10% UBD", "provider": "Cafe",
            "content_hash": "hashnosrc"}   # no source_id
    h = {"X-API-Key": settings.crawler_api_key}
    r1 = client.post("/api/internal/offers", json=body, headers=h)
    r2 = client.post("/api/internal/offers", json=body, headers=h)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]      # deduped, not a duplicate
    assert r1.json()["source_id"] is None


def test_rejected_sourceless_offer_not_resurrected(client, db_session):
    from app.models import Offer
    from app.models.enums import OfferStatus
    body = {"type": "discount", "title": "x", "provider": "P", "content_hash": "hh"}
    h = {"X-API-Key": settings.crawler_api_key}
    oid = client.post("/api/internal/offers", json=body, headers=h).json()["id"]
    obj = db_session.get(Offer, oid)
    obj.status = OfferStatus.rejected
    db_session.commit()
    r2 = client.post("/api/internal/offers", json=body, headers=h)
    assert r2.json()["id"] == oid                  # same row, not a new pending one
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest -q tests/test_internal.py::test_crawler_sourceless_offer_dedup_is_idempotent tests/test_internal.py::test_rejected_sourceless_offer_not_resurrected`
Expected: FAIL — second POST creates a new row (different id), because current dedup requires `source_id is not None`.

- [ ] **Step 3: Extend the dedup guard**

In `backend/app/crud/offer.py`, replace the block at lines 24-30:

```python
    if content_hash is not None and source_id is not None:
        existing = (db.query(Offer)
                    .filter(Offer.source_id == source_id,
                            Offer.content_hash == content_hash)
                    .first())
        if existing is not None:
            return existing
```

with:

```python
    if content_hash is not None and created_by == CreatedBy.crawler:
        q = db.query(Offer).filter(Offer.content_hash == content_hash)
        q = (q.filter(Offer.source_id == source_id) if source_id is not None
             else q.filter(Offer.source_id.is_(None)))
        existing = q.first()
        if existing is not None:
            return existing
```

`CreatedBy` is already imported at the top of the file.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest -q tests/test_internal.py`
Expected: PASS (including the existing `test_crawler_offer_dedup_is_idempotent`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/crud/offer.py backend/tests/test_internal.py
git commit -m "feat(backend): dedup source-less crawler offers by content_hash"
```

---

## Task 2: Crawler — `RawItem.site_name` + WebsiteFetcher populates it

**Files:**
- Modify: `crawler/crawler/models.py:12-20`
- Modify: `crawler/crawler/fetchers/website.py`
- Test: `crawler/tests/test_website_fetcher.py`

**Interfaces:**
- Produces: `RawItem.site_name: str | None = None`, set by `WebsiteFetcher` to `og:site_name` → `<title>` → `h1`.

- [ ] **Step 1: Write the failing test**

Add to `crawler/tests/test_website_fetcher.py`:

```python
def test_website_captures_site_name():
    html = ('<html><head><meta property="og:site_name" content="My Cafe">'
            '<title>t</title></head><body>'
            '<article><p>Знижка 15% для ветеранів на каву у нас.</p></article>'
            '</body></html>')
    def handle(request):
        return httpx.Response(200, text=html)
    f = WebsiteFetcher(httpx.Client(transport=httpx.MockTransport(handle)))
    items, _ = f.fetch({"id": 1, "url_or_handle": "http://x"}, None)
    assert items and all(i.site_name == "My Cafe" for i in items)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crawler && .venv/Scripts/python.exe -m pytest -q tests/test_website_fetcher.py::test_website_captures_site_name`
Expected: FAIL — `RawItem` has no `site_name` (TypeError) / attribute missing.

- [ ] **Step 3: Add the field**

In `crawler/crawler/models.py`, add to `RawItem` (after `logo_url`):

```python
@dataclass
class RawItem:
    source_id: int
    platform: str
    key: str                 # stable per-item cursor key (e.g. post id / hash)
    text: str
    url: str | None = None
    links: list[str] = field(default_factory=list)
    logo_url: str | None = None
    site_name: str | None = None
```

- [ ] **Step 4: Populate it in WebsiteFetcher**

In `crawler/crawler/fetchers/website.py`, add a helper after `_extract_logo`:

```python
def _extract_site_name(tree) -> str | None:
    node = tree.css_first('meta[property="og:site_name"]')
    if node is not None and node.attributes.get("content"):
        return node.attributes["content"].strip()
    for css in ("title", "h1"):
        node = tree.css_first(css)
        if node is not None:
            txt = node.text(strip=True)
            if txt:
                return txt
    return None
```

Then in `WebsiteFetcher.fetch`, after `logo = _extract_logo(tree, url)` add:

```python
            site_name = _extract_site_name(tree)
```

and pass it into the `RawItem(...)` construction:

```python
                items.append(RawItem(source_id=source["id"], platform="website",
                                     key=key, text=text, url=url, links=links,
                                     logo_url=logo, site_name=site_name))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd crawler && .venv/Scripts/python.exe -m pytest -q tests/test_website_fetcher.py`
Expected: PASS (all existing website tests plus the new one).

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/models.py crawler/crawler/fetchers/website.py crawler/tests/test_website_fetcher.py
git commit -m "feat(crawler): capture page site_name in WebsiteFetcher RawItems"
```

---

## Task 3: Crawler — provider attribution (`attribution.py`)

**Files:**
- Create: `crawler/crawler/discovery/attribution.py`
- Test: `crawler/tests/test_attribution.py`

**Interfaces:**
- Produces:
  - `PageCtx(cand_type, cand_name, cand_url_or_handle, brand, host, offer_block_count)`
  - `Attribution(provider, is_first_party, suggest_type, suggest_url_or_handle, suggest_name)`
  - `build_page_ctx(cand, passing_items) -> PageCtx`
  - `attribute(item, ctx: PageCtx) -> Attribution | None`
- Consumes: `crawler.extract.heuristic._pick_target(links, source_url)`; `RawItem.site_name` (Task 2); `SourceCandidate` fields `type`, `name`, `url_or_handle`.

- [ ] **Step 1: Write the failing tests**

Create `crawler/tests/test_attribution.py`:

```python
from crawler.discovery.attribution import attribute, build_page_ctx, PageCtx
from crawler.models import RawItem, SourceCandidate


def _item(text, url="https://biz.example/p", links=None, site_name=None):
    return RawItem(source_id=None, platform="website", key="k", text=text,
                   url=url, links=links or [], site_name=site_name)


def test_first_party_first_person():
    item = _item("У нас знижка 10% для УБД", site_name="Biz")
    ctx = build_page_ctx(SourceCandidate(name="Biz", type="website",
                                         url_or_handle="https://biz.example"), [item])
    a = attribute(item, ctx)
    assert a.is_first_party and a.provider == "Biz"
    assert a.suggest_type == "website"
    assert a.suggest_url_or_handle == "https://biz.example"


def test_third_party_external_link():
    item = _item("Заклад Кава дає 15% військовим",
                 links=["https://kava.example/menu"], site_name="Portal")
    ctx = PageCtx(cand_type="website", cand_name="Portal",
                  cand_url_or_handle="https://portal.example",
                  brand="Portal", host="portal.example", offer_block_count=9)
    a = attribute(item, ctx)
    assert not a.is_first_party
    assert a.provider == "kava.example"
    assert a.suggest_url_or_handle == "https://kava.example"


def test_generic_info_rejected():
    item = _item("Для УБД існують знижки по місту", site_name=None)
    ctx = PageCtx(cand_type="website", cand_name="Portal",
                  cand_url_or_handle="https://portal.example",
                  brand=None, host="portal.example", offer_block_count=9)
    assert attribute(item, ctx) is None


def test_single_business_page_first_party():
    item = _item("Знижка 10% ветеранам", site_name="Shop")
    ctx = PageCtx(cand_type="website", cand_name="Shop",
                  cand_url_or_handle="https://shop.example",
                  brand="Shop", host="shop.example", offer_block_count=2)
    a = attribute(item, ctx)
    assert a.is_first_party and a.provider == "Shop"


def test_telegram_channel_is_provider():
    item = _item("Знижка 25% сьогодні", url="https://t.me/kavachan/12")
    ctx = build_page_ctx(SourceCandidate(name="Kava Channel", type="telegram",
                                         url_or_handle="t.me/kavachan"), [item])
    a = attribute(item, ctx)
    assert a.is_first_party and a.provider == "Kava Channel"
    assert a.suggest_type == "telegram"
    assert a.suggest_url_or_handle == "t.me/kavachan"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd crawler && .venv/Scripts/python.exe -m pytest -q tests/test_attribution.py`
Expected: FAIL — `ModuleNotFoundError: crawler.discovery.attribution`.

- [ ] **Step 3: Implement attribution**

Create `crawler/crawler/discovery/attribution.py`:

```python
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from crawler.extract.heuristic import _pick_target

_FIRST_PERSON = re.compile(r"\b(ми|у нас|наш\w*|для наших)\b", re.IGNORECASE)


@dataclass
class PageCtx:
    cand_type: str
    cand_name: str
    cand_url_or_handle: str
    brand: str | None
    host: str | None
    offer_block_count: int


@dataclass
class Attribution:
    provider: str
    is_first_party: bool
    suggest_type: str | None
    suggest_url_or_handle: str | None
    suggest_name: str | None


def _host(url: str) -> str | None:
    netloc = urlsplit(url or "").netloc.lower().removeprefix("www.")
    return netloc or None


def _origin(url: str) -> str | None:
    p = urlsplit(url or "")
    return f"{p.scheme}://{p.netloc}" if p.scheme and p.netloc else None


def build_page_ctx(cand, passing_items) -> PageCtx:
    brand = next((it.site_name for it in passing_items
                  if getattr(it, "site_name", None)), None)
    host = next((_host(it.url) for it in passing_items if it.url), None)
    return PageCtx(
        cand_type=cand.type, cand_name=cand.name, cand_url_or_handle=cand.url_or_handle,
        brand=brand, host=host, offer_block_count=len(passing_items),
    )


def _first_party(ctx: PageCtx) -> Attribution:
    origin = _origin(ctx.cand_url_or_handle) or (f"https://{ctx.host}" if ctx.host else None)
    return Attribution(provider=ctx.brand, is_first_party=True,
                       suggest_type="website", suggest_url_or_handle=origin,
                       suggest_name=ctx.brand)


def attribute(item, ctx: PageCtx) -> Attribution | None:
    if ctx.cand_type == "telegram":
        provider = ctx.cand_name or ctx.cand_url_or_handle
        return Attribution(provider=provider, is_first_party=True,
                           suggest_type="telegram",
                           suggest_url_or_handle=ctx.cand_url_or_handle,
                           suggest_name=ctx.cand_name or provider)

    low = (item.text or "").lower()
    # 1. first-party via first-person marker (wins over an outbound link)
    if _FIRST_PERSON.search(low) and ctx.brand:
        return _first_party(ctx)
    # 2. third-party via an external business link
    ext = _pick_target(getattr(item, "links", None), item.url or "")
    if ext:
        host = _host(ext) or ext
        return Attribution(provider=host, is_first_party=False,
                           suggest_type="website", suggest_url_or_handle=_origin(ext),
                           suggest_name=host)
    # 3. first-party via a single-business page
    if ctx.offer_block_count <= 3 and ctx.brand:
        return _first_party(ctx)
    # 4. generic info → no attributable provider
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd crawler && .venv/Scripts/python.exe -m pytest -q tests/test_attribution.py`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/attribution.py crawler/tests/test_attribution.py
git commit -m "feat(crawler): heuristic provider attribution for active search"
```

---

## Task 4: Crawler — `ActiveHarvester` (+ `payloads.py`)

**Files:**
- Create: `crawler/crawler/payloads.py`
- Modify: `crawler/crawler/runner.py:9-37` (move `offer_payload`/`suggestion_payload` out, import them)
- Create: `crawler/crawler/discovery/harvest.py`
- Test: `crawler/tests/test_active_harvest.py`

**Interfaces:**
- Consumes: `attribute`, `build_page_ctx` (Task 3); `normalize_ref` from `crawler.discovery.passive`; fetchers with `.fetch(source_dict, last_seen_key) -> (items, key)`; an extractor with `.extract(item, provider, cats) -> OfferCandidate | None`.
- Produces:
  - `crawler.payloads.offer_payload(cand) -> dict`, `crawler.payloads.suggestion_payload(sc) -> dict`
  - `ActiveHarvester(api, fetchers, extractor, rate_limiter, fetch_budget=20)` with `.harvest(candidates, cats, known, summary) -> None` (mutates `summary` keys `offers`/`suggestions`/`errors` and `known`).

- [ ] **Step 1: Create `payloads.py` and rewire runner imports**

Create `crawler/crawler/payloads.py` by moving the two functions out of `runner.py` verbatim:

```python
def offer_payload(cand) -> dict:
    return {
        "type": cand.offer_type,
        "title": cand.title,
        "description": cand.body,
        "provider": cand.provider,
        "discount_type": cand.discount_type,
        "discount_value": cand.discount_value,
        "valid_from": cand.valid_from.isoformat() if cand.valid_from else None,
        "valid_until": cand.valid_until.isoformat() if cand.valid_until else None,
        "source_id": cand.source_id,
        "content_hash": cand.content_hash,
        "site_url": cand.site_url,
        "article_url": cand.article_url,
        "image_url": cand.image_url,
        "target_url": cand.target_url,
        "target_category_ids": cand.target_category_ids,
        "offer_category_ids": cand.offer_category_ids,
    }


def suggestion_payload(sc) -> dict:
    return {
        "name": sc.name,
        "type": sc.type,
        "url_or_handle": sc.url_or_handle,
        "discovered_from_source_id": sc.discovered_from_source_id,
        "discovery_note": sc.discovery_note,
    }
```

In `crawler/crawler/runner.py`, delete the two function definitions (lines 9-37) and add at the top with the other imports:

```python
from crawler.payloads import offer_payload, suggestion_payload
```

- [ ] **Step 2: Verify runner still works**

Run: `cd crawler && .venv/Scripts/python.exe -m pytest -q tests/test_runner.py`
Expected: PASS (runner behaviour unchanged; payloads just moved).

- [ ] **Step 3: Write the failing harvester tests**

Create `crawler/tests/test_active_harvest.py`:

```python
from crawler.discovery.harvest import ActiveHarvester
from crawler.discovery.passive import normalize_ref
from crawler.models import SourceCandidate, RawItem, OfferCandidate


class FakeApi:
    def __init__(self):
        self.offers = []
        self.suggested = []
    def submit_offer(self, p): self.offers.append(p); return {}
    def submit_suggestion(self, p): self.suggested.append(p); return {}


class FakeFetcher:
    def __init__(self, items): self._items = items
    def fetch(self, source, last_seen_key): return list(self._items), None


class GateExtractor:
    """Returns an OfferCandidate for blocks whose text has '%', else None."""
    def extract(self, item, provider, cats):
        if "%" not in (item.text or ""):
            return None
        return OfferCandidate(source_id=item.source_id, title=item.text[:50],
                              provider=provider, body=item.text, content_hash="h")


def _cand(url="https://cafe.example", type="website", name="Cafe"):
    return SourceCandidate(name=name, type=type, url_or_handle=url)


def _item(text, site_name=None, links=None):
    return RawItem(source_id=None, platform="website", key="k", text=text,
                   url="https://cafe.example/page", links=links or [], site_name=site_name)


def _summary():
    return {"offers": 0, "suggestions": 0, "errors": 0}


def test_valid_first_party_offer_and_suggestion():
    api = FakeApi()
    h = ActiveHarvester(api, {"website": FakeFetcher([_item("Знижка 20% для УБД у нас",
                                                            site_name="Cafe")])},
                        GateExtractor(), rate_limiter=None, fetch_budget=5)
    summary = _summary()
    h.harvest([_cand()], cats=None, known=set(), summary=summary)
    assert len(api.offers) == 1 and api.offers[0]["provider"] == "Cafe"
    assert api.offers[0]["source_id"] is None
    assert len(api.suggested) == 1
    assert api.suggested[0]["url_or_handle"] == "https://cafe.example"
    assert summary["offers"] == 1 and summary["suggestions"] == 1


def test_generic_info_rejected():
    api = FakeApi()
    h = ActiveHarvester(api, {"website": FakeFetcher([_item("Для УБД існують знижки 10%")])},
                        GateExtractor(), rate_limiter=None, fetch_budget=5)
    summary = _summary()
    h.harvest([_cand()], cats=None, known=set(), summary=summary)
    assert api.offers == [] and api.suggested == []


def test_fetch_budget_caps_fetches():
    api = FakeApi()
    fetched = []
    class CountingFetcher:
        def fetch(self, source, k): fetched.append(source["url_or_handle"]); return [], None
    h = ActiveHarvester(api, {"website": CountingFetcher()}, GateExtractor(),
                        rate_limiter=None, fetch_budget=2)
    cands = [_cand(url=f"https://s{i}.example") for i in range(5)]
    h.harvest(cands, cats=None, known=set(), summary=_summary())
    assert len(fetched) == 2


def test_known_candidate_skipped():
    api = FakeApi()
    fetched = []
    class CountingFetcher:
        def fetch(self, source, k): fetched.append(1); return [], None
    h = ActiveHarvester(api, {"website": CountingFetcher()}, GateExtractor(),
                        rate_limiter=None, fetch_budget=5)
    known = {normalize_ref("website", "https://cafe.example")}
    h.harvest([_cand()], cats=None, known=known, summary=_summary())
    assert fetched == []


def test_error_in_one_candidate_isolated():
    api = FakeApi()
    class BoomFetcher:
        def fetch(self, source, k): raise RuntimeError("boom")
    h = ActiveHarvester(api, {"website": BoomFetcher()}, GateExtractor(),
                        rate_limiter=None, fetch_budget=5)
    summary = _summary()
    h.harvest([_cand()], cats=None, known=set(), summary=summary)
    assert summary["errors"] == 1 and api.offers == []
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd crawler && .venv/Scripts/python.exe -m pytest -q tests/test_active_harvest.py`
Expected: FAIL — `ModuleNotFoundError: crawler.discovery.harvest`.

- [ ] **Step 5: Implement `ActiveHarvester`**

Create `crawler/crawler/discovery/harvest.py`:

```python
import logging

from crawler.discovery.attribution import attribute, build_page_ctx
from crawler.discovery.passive import normalize_ref
from crawler.payloads import offer_payload

log = logging.getLogger(__name__)

_FETCHABLE = ("website", "telegram")


def _as_source(cand) -> dict:
    return {"id": None, "type": cand.type, "url_or_handle": cand.url_or_handle,
            "name": cand.name}


class ActiveHarvester:
    def __init__(self, api, fetchers, extractor, rate_limiter, fetch_budget=20):
        self._api = api
        self._fetchers = fetchers
        self._extractor = extractor
        self._rl = rate_limiter
        self._budget = fetch_budget

    def harvest(self, candidates, cats, known, summary) -> None:
        used = 0
        for cand in candidates:
            if used >= self._budget:
                break
            if cand.type not in _FETCHABLE:
                continue
            if normalize_ref(cand.type, cand.url_or_handle) in known:
                continue
            fetcher = self._fetchers.get(cand.type)
            if fetcher is None:
                continue
            used += 1
            try:
                self._harvest_one(cand, fetcher, cats, known, summary)
            except Exception as exc:  # noqa: BLE001 — isolate per candidate
                summary["errors"] += 1
                log.warning("active harvest failed for %s: %s", cand.url_or_handle, exc)

    def _harvest_one(self, cand, fetcher, cats, known, summary) -> None:
        if self._rl is not None:
            self._rl.wait(cand.type)
        items, _ = fetcher.fetch(_as_source(cand), None)
        passing = [it for it in items
                   if self._extractor.extract(it, "", cats) is not None]
        ctx = build_page_ctx(cand, passing)
        for item in passing:
            attr = attribute(item, ctx)
            if attr is None:
                continue
            offer = self._extractor.extract(item, attr.provider, cats)
            self._api.submit_offer(offer_payload(offer))
            summary["offers"] += 1
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

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd crawler && .venv/Scripts/python.exe -m pytest -q tests/test_active_harvest.py tests/test_runner.py`
Expected: PASS (5 harvester tests + runner unchanged).

- [ ] **Step 7: Commit**

```bash
git add crawler/crawler/payloads.py crawler/crawler/runner.py crawler/crawler/discovery/harvest.py crawler/tests/test_active_harvest.py
git commit -m "feat(crawler): ActiveHarvester turns search hits into moderation offers"
```

---

## Task 5: Crawler — wire harvester into runner, config, wiring, .env

**Files:**
- Modify: `crawler/crawler/runner.py:40-83` (Runner `__init__` + active branch)
- Modify: `crawler/tests/test_runner_discovery.py` (rewrite)
- Modify: `crawler/crawler/config.py:8-43,66-85` (add `active_fetch_budget`)
- Modify: `crawler/crawler/wiring.py:43-50` (build harvester)
- Modify: `crawler/.env.example`

**Interfaces:**
- Consumes: `ActiveHarvester` (Task 4); `Config.active_fetch_budget`.
- Produces: `Runner(api, fetchers, extractor, rate_limiter, discovery=None, keywords=None, harvester=None)`; the active branch calls `harvester.harvest(candidates, cats, known, summary)`.

- [ ] **Step 1: Rewrite the runner-discovery tests**

Replace the entire contents of `crawler/tests/test_runner_discovery.py`:

```python
from crawler.runner import Runner
from crawler.models import SourceCandidate


class FakeApi:
    def __init__(self):
        self.offers = []
        self.suggested = []
    def list_target_categories(self): return []
    def list_offer_categories(self): return []
    def list_sources(self, is_active=True): return []
    def submit_offer(self, p): self.offers.append(p); return {}
    def submit_suggestion(self, p): self.suggested.append(p); return {}


class FakeDiscovery:
    def __init__(self, cands): self._cands = cands; self.called_with = None
    def run(self, keywords, known):
        self.called_with = (keywords, set(known))
        return self._cands


class FakeHarvester:
    def __init__(self): self.calls = []
    def harvest(self, candidates, cats, known, summary):
        self.calls.append(list(candidates))
        summary["offers"] += len(candidates)


def _runner(api, discovery, harvester):
    return Runner(api, {}, extractor=None, rate_limiter=None, discovery=discovery,
                  keywords=["знижки ветеранам"], harvester=harvester)


def test_runner_delegates_active_candidates_to_harvester():
    api = FakeApi()
    cand = SourceCandidate(name="Cafe", type="website", url_or_handle="https://cafe.example")
    h = FakeHarvester()
    summary = _runner(api, FakeDiscovery([cand]), h).run()
    assert h.calls == [[cand]]
    assert summary["offers"] == 1
    assert api.suggested == []          # no blind per-result suggestions anymore


def test_runner_without_harvester_emits_nothing():
    api = FakeApi()
    cand = SourceCandidate(name="Cafe", type="website", url_or_handle="https://cafe.example")
    _runner(api, FakeDiscovery([cand]), None).run()
    assert api.offers == [] and api.suggested == []


def test_runner_no_discovery_is_quiet():
    api = FakeApi()
    _runner(api, None, None).run()
    assert api.offers == [] and api.suggested == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd crawler && .venv/Scripts/python.exe -m pytest -q tests/test_runner_discovery.py`
Expected: FAIL — `Runner.__init__` has no `harvester` parameter (TypeError).

- [ ] **Step 3: Add `harvester` to Runner and delegate the active branch**

In `crawler/crawler/runner.py`, update `Runner.__init__`:

```python
    def __init__(self, api_client, fetchers: dict, extractor, rate_limiter,
                 discovery=None, keywords=None, harvester=None):
        self._api = api_client
        self._fetchers = fetchers
        self._extractor = extractor
        self._rl = rate_limiter
        self._discovery = discovery
        self._keywords = keywords or []
        self._harvester = harvester
```

Replace the active-discovery block in `Runner.run` (currently lines ~72-80):

```python
        if self._discovery is not None and self._keywords:
            try:
                for cand in self._discovery.run(self._keywords, known):
                    self._api.submit_suggestion(suggestion_payload(cand))
                    known.add(normalize_ref(cand.type, cand.url_or_handle))
                    summary["suggestions"] += 1
            except Exception as exc:  # noqa: BLE001 — discovery must not crash the pass
                summary["errors"] += 1
                log.warning("active discovery failed: %s", exc)
```

with:

```python
        if self._discovery is not None and self._keywords and self._harvester is not None:
            try:
                candidates = self._discovery.run(self._keywords, known)
                self._harvester.harvest(candidates, cats, known, summary)
            except Exception as exc:  # noqa: BLE001 — discovery must not crash the pass
                summary["errors"] += 1
                log.warning("active discovery failed: %s", exc)
```

`suggestion_payload` is still imported (used by `_crawl_source`) — leave the import. `normalize_ref` is still used elsewhere in the file — leave it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd crawler && .venv/Scripts/python.exe -m pytest -q tests/test_runner_discovery.py tests/test_runner.py`
Expected: PASS.

- [ ] **Step 5: Add `active_fetch_budget` to config**

In `crawler/crawler/config.py`:

In `_RawSettings` (after `search_budget`):

```python
    active_fetch_budget: int = 20
```

In `Config` dataclass (after `search_budget`):

```python
    active_fetch_budget: int = 20
```

In `load_config()` return (after `search_budget=...`):

```python
        active_fetch_budget=s.active_fetch_budget,
```

- [ ] **Step 6: Add a config assertion**

Add to `crawler/tests/test_config.py` (append a test):

```python
def test_active_fetch_budget_default(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)      # no .env → defaults
    from crawler.config import load_config
    assert load_config().active_fetch_budget == 20
```

If `test_config.py` already has a fixture/pattern for isolating `.env`, follow it instead of `monkeypatch.chdir`; the assertion (`active_fetch_budget == 20`) is what matters.

- [ ] **Step 7: Build the harvester in wiring**

In `crawler/crawler/wiring.py`, add the import near the other discovery imports:

```python
from crawler.discovery.harvest import ActiveHarvester
```

Replace the `discovery` block (lines ~43-50) with:

```python
    discovery = None
    harvester = None
    if config.active_discovery:
        provider = build_search_provider(config)
        if provider is not None:
            budget = config.search_budget or len(config.search_keywords)
            discovery = ActiveDiscovery(budget=budget, search_provider=provider)
            if config.active_fetch_budget:
                harvester = ActiveHarvester(api, fetchers, extractor, rate_limiter,
                                            fetch_budget=config.active_fetch_budget)
    return Runner(api, fetchers, extractor, rate_limiter,
                  discovery=discovery, keywords=config.search_keywords, harvester=harvester)
```

- [ ] **Step 8: Update `.env.example`**

In `crawler/.env.example`, add near the other `SEARCH_*` / `ACTIVE_DISCOVERY` keys:

```
# Max page fetches per pass for active-search offer harvesting (0 disables harvesting)
ACTIVE_FETCH_BUDGET=20
```

- [ ] **Step 9: Run the full crawler + backend suites**

Run: `cd crawler && .venv/Scripts/python.exe -m pytest -q`
Expected: PASS (all crawler tests, incl. `test_wiring`, `test_config`, discovery, harvest, attribution).

Run: `cd backend && .venv/Scripts/python.exe -m pytest -q`
Expected: PASS.

If `test_wiring.py` asserts the old return shape or a suggestion-based active path, update it to expect a `harvester` wired when `active_discovery` + providers are configured.

- [ ] **Step 10: Commit**

```bash
git add crawler/crawler/runner.py crawler/crawler/config.py crawler/crawler/wiring.py crawler/.env.example crawler/tests/test_runner_discovery.py crawler/tests/test_config.py
git commit -m "feat(crawler): wire ActiveHarvester into runner + ACTIVE_FETCH_BUDGET"
```

---

## Task 6: Docs + README refresh

**Files:**
- Modify: `crawler/README.md:27-36` (Configuration section)

**Interfaces:** none (documentation only).

- [ ] **Step 1: Update the README**

In `crawler/README.md`, under Configuration, adjust the active-search line and add the budget key:

```
- `ACTIVE_DISCOVERY=false` — Level-2 active search is opt-in (off by default).
  When on, found website/telegram pages are fetched and, if a provider can be
  attributed, offers are submitted straight to moderation (source suggestions
  are a by-product). Instagram/Facebook results are ignored for now.
- `ACTIVE_FETCH_BUDGET=20` — max page fetches per active-search pass (0 disables).
```

Also update the top-of-file summary line if it still says active search only "proposes new sources".

- [ ] **Step 2: Commit**

```bash
git add crawler/README.md
git commit -m "docs(crawler): document active-search offer harvesting + fetch budget"
```

---

## Self-Review notes (author)

- **Spec coverage:** decisions 1–5 map to Tasks 1 (dedup), 3 (attribution incl. conditional suggest), 4 (harvest, website+telegram, IG/FB skipped), 5 (budget + wiring). Backend source-less offer support already exists (no task needed).
- **Type consistency:** `attribute(item, ctx)` / `build_page_ctx(cand, passing_items)` / `Attribution` fields are used identically in Tasks 3 and 4. `ActiveHarvester(api, fetchers, extractor, rate_limiter, fetch_budget)` matches between Tasks 4 and 5. `offer_payload`/`suggestion_payload` live in `payloads.py` and are imported by both `runner.py` and `harvest.py`.
- **`content_hash` correctness:** the harvester calls `extract(item, attr.provider, cats)` for the real offer so `content_hash = hash(title, provider, text)` reflects the attributed provider (the gate-only `extract(item, "")` output is discarded).
- **No placeholders:** every code step contains full code; every run step has an exact command and expected result.
