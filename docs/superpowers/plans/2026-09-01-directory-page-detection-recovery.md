# Directory-Page Detection + Isolated Sub-Search Recovery — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop attributing catalog/directory pages (myhelp-type) as offers; instead, in an isolated "sub-search" lane, extract the business name, search the web for its own site once, extract the real offer from there into the normal moderation queue, and drop businesses that yield nothing — all fully autonomous, with the main crawl untouched.

**Architecture:** The main crawl detects a directory page (`is_directory_page`), suppresses the offer, registers the host with the backend (which auto-rejects existing + future catalog offers), and appends the business name to an in-memory queue. A separate `run_subsearch` phase (own budget, skipped under backoff) resolves each business to its official domain and runs it through a **second, isolated `ActiveHarvester`** (registry/aggregator disabled) that submits any real offers. Nothing from the sub-search writes back into main-crawl feeds/registries.

**Tech Stack:** Python 3.12 (crawler, `crawler/crawler/discovery/`), FastAPI + SQLAlchemy + MySQL (backend), pytest, Alembic.

## Global Constraints

- **Autonomy invariant:** everything automatic, free ($0), no human-in-loop, no new UI. Only the existing DDG/SearXNG search — no paid APIs.
- **Isolation:** the sub-search MUST NOT write to `domain_registry`, `aggregator_store`, or the main source feeds. Its only external effect is `api.submit_offer` (offers to the normal `pending_review` moderation queue) and reading the shared search backends under a budget cap.
- **No persistent recovery memory:** the sub-search queue is per-run; a business that yields no offer is simply forgotten (no memo store).
- **Robustness:** any sub-search failure (search/fetch/extract) is caught per-item and never breaks the main harvest pass.
- **Ukrainian only** for any user-facing text/log copy where relevant; never Russian.
- **Backend directory hosts are FETCHABLE** — they must NOT enter the crawler no-fetch blocklist (`blocked_hosts` approved). Use a separate `directory_hosts` table.
- Run crawler tests: from `crawler/` → `./.venv/Scripts/python.exe -m pytest -q` (Windows). Run backend tests inside the running MySQL: from `backend/` → `./.venv/Scripts/python.exe -m pytest -q` (needs `mysql-container` up; schema `ubd_test`).

---

### Task 1: Directory-page detector — `is_directory_page`

**Files:**
- Modify: `crawler/crawler/discovery/host_quality.py`
- Test: `crawler/tests/test_host_quality.py`

**Interfaces:**
- Produces: `DIRECTORY_HOST_SEEDS: frozenset[str]`; `is_directory_page(url: str | None, title: str | None) -> bool` — True when the page is a directory/catalog listing entry (host in seeds, OR listing-entry URL pattern) AND the title carries a ` | ` brand separator.

- [ ] **Step 1: Write the failing test**

```python
# append to crawler/tests/test_host_quality.py
from crawler.discovery.host_quality import is_directory_page, DIRECTORY_HOST_SEEDS

_MYHELP = ("https://myhelp.com.ua/places/vinnytsia-language-school/services/"
           "znyzhka-dlia-uchasnykiv-boiovykh-dii-197164d0")

def test_directory_page_myhelp_seed_host_and_title():
    assert is_directory_page(_MYHELP, "Знижка ... для ... Vinnytsia Language School | MY Help")

def test_directory_page_url_pattern_non_seed_host():
    # non-seed host but clear listing-entry path + brand title
    url = "https://katalog-znyzhok.ua/company/kavarnya-lviv/offers/minus-15"
    assert is_directory_page(url, "Кав'ярня Львів | Каталог знижок")

def test_directory_page_false_on_first_party_business():
    # a real business's own discount page: no listing path, no brand-suffix title
    assert not is_directory_page("https://kavarnya-lviv.com.ua/aktsiyi",
                                 "Акції — Кав'ярня Львів")

def test_directory_page_false_when_title_has_no_brand_separator():
    # seed host but title without ' | ' → still treat as directory via seed host?
    # NO: require BOTH signals, so a bare seed-host page with no brand title is not matched here
    assert not is_directory_page(_MYHELP, "Vinnytsia Language School")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_host_quality.py -k directory -v`
Expected: FAIL with `ImportError: cannot import name 'is_directory_page'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to crawler/crawler/discovery/host_quality.py
from urllib.parse import urlsplit

# Каталоги/директорії знижок: сторінка описує ІНШИЙ бізнес, не власника домену.
# Старт — вручну підтверджений сид; розширюється лише за доказом на реальних даних.
DIRECTORY_HOST_SEEDS = frozenset({"myhelp.com.ua"})

# Сегмент-«контейнер лістинг-запису» + наявність під-сегмента бізнесу.
_DIR_CONTAINER = {"places", "place", "company", "companies", "firm", "profile",
                  "catalog", "business", "org"}


def _is_listing_entry_path(url: str | None) -> bool:
    """URL-шлях виду /{container}/<бізнес>/... — запис каталогу про конкретний бізнес."""
    try:
        parts = [p for p in urlsplit(url or "").path.split("/") if p]
    except ValueError:
        return False
    for i, seg in enumerate(parts):
        if seg.lower() in _DIR_CONTAINER and i + 1 < len(parts):
            return True     # container followed by a business slug
    return False


def is_directory_page(url: str | None, title: str | None) -> bool:
    """True, якщо сторінка — запис каталогу/директорії (не first-party офер): host у
    сид-списку АБО listing-entry URL-патерн, І title має ` | ` (сутність | бренд)."""
    host = bare_host(url)
    if not title or " | " not in title:
        return False
    if host in DIRECTORY_HOST_SEEDS:
        return True
    return _is_listing_entry_path(url)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_host_quality.py -k directory -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/host_quality.py crawler/tests/test_host_quality.py
git commit -m "feat(crawler): is_directory_page detector (seed host / listing-URL + brand title)"
```

---

### Task 2: Business identity extractor — `extract_business`

**Files:**
- Create: `crawler/crawler/discovery/subsearch.py`
- Test: `crawler/tests/test_subsearch.py`

**Interfaces:**
- Consumes: `RawItem` (fields `url`, `text`, `locality`), a candidate with `.url_or_handle`.
- Produces: `extract_business(items: list, cand) -> tuple[str | None, str | None]` — `(name, city)`. `name` de-slugged from the business segment of the URL (robust, clean); `city` from the first item `locality`, else `None`.

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_subsearch.py
from dataclasses import dataclass, field
from crawler.discovery.subsearch import extract_business

@dataclass
class _Item:
    url: str | None = None
    text: str = ""
    locality: str | None = None
    links: list = field(default_factory=list)

@dataclass
class _Cand:
    url_or_handle: str
    type: str = "website"
    name: str | None = None

_URL = ("https://myhelp.com.ua/places/vinnytsia-language-school/services/"
        "znyzhka-dlia-uchasnykiv-boiovykh-dii")

def test_extract_business_name_from_url_slug():
    name, city = extract_business([_Item(url=_URL, locality="Вінниця")], _Cand(_URL))
    assert name == "vinnytsia language school"
    assert city == "Вінниця"

def test_extract_business_city_none_when_no_locality():
    name, city = extract_business([_Item(url=_URL)], _Cand(_URL))
    assert name == "vinnytsia language school"
    assert city is None

def test_extract_business_name_none_when_no_listing_segment():
    name, city = extract_business([_Item(url="https://x.ua/about")], _Cand("https://x.ua/about"))
    assert name is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_subsearch.py -k extract_business -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'crawler.discovery.subsearch'`

- [ ] **Step 3: Write minimal implementation**

```python
# crawler/crawler/discovery/subsearch.py
"""Ізольований «підпошук»: з каталог-сторінки (myhelp-тип) дістати назву бізнесу,
ОДИН РАЗ пошукати його офіційний сайт і витягти реальний офер уже звідти. Повна
ізоляція від основного краулу — не пише в domain_registry/aggregator_store/джерела."""

import logging
from urllib.parse import urlsplit

from crawler.discovery.host_quality import _DIR_CONTAINER

log = logging.getLogger(__name__)


def extract_business(items, cand) -> tuple[str | None, str | None]:
    """(name, city) з каталог-сторінки. name — де-слаг бізнес-сегмента URL (чисте,
    надійне джерело для пошуку); city — locality першого item, інакше None."""
    url = (getattr(cand, "url_or_handle", None)
           or next((it.url for it in items if getattr(it, "url", None)), None))
    parts = [p for p in urlsplit(url or "").path.split("/") if p]
    name = None
    for i, seg in enumerate(parts):
        if seg.lower() in _DIR_CONTAINER and i + 1 < len(parts):
            name = parts[i + 1].replace("-", " ").replace("_", " ").strip().lower()
            break
    city = next((it.locality for it in items if getattr(it, "locality", None)), None)
    return (name or None), city
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_subsearch.py -k extract_business -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/subsearch.py crawler/tests/test_subsearch.py
git commit -m "feat(crawler): extract_business — business name+city from a catalog page"
```

---

### Task 3: Business→domain resolver — `resolve_business_site` (incl. R1)

**Files:**
- Modify: `crawler/crawler/discovery/subsearch.py`
- Test: `crawler/tests/test_subsearch.py`

**Interfaces:**
- Consumes: a `search` callable `search(keyword: str) -> list[SourceCandidate]` (each candidate has `.type == "website"` and `.url_or_handle`); `bare_host`, `is_blocked_host`, `is_foreign_host`, `is_ru_by_geo`, `DIRECTORY_HOST_SEEDS`.
- Produces: `resolve_business_site(name: str, city: str | None, search) -> str | None` — a bare business host, or `None`. **R1:** a generic name (≤2 significant tokens) with `city is None` returns `None` (no guessing).

- [ ] **Step 1: Write the failing test**

```python
# append to crawler/tests/test_subsearch.py
from crawler.discovery.subsearch import resolve_business_site

@dataclass
class _SC:
    url_or_handle: str
    type: str = "website"
    name: str | None = None

def _search_returning(*hosts):
    return lambda kw: [_SC(f"https://{h}/") for h in hosts]

def test_resolve_picks_first_clean_business_host():
    search = _search_returning("facebook.com", "vinnytsia-language-school.com.ua")
    # facebook is a blocked/social host → skipped; business host wins
    host = resolve_business_site("vinnytsia language school", "Вінниця", search)
    assert host == "vinnytsia-language-school.com.ua"

def test_resolve_none_when_only_aggregators_and_social():
    search = _search_returning("facebook.com", "myhelp.com.ua")
    assert resolve_business_site("vinnytsia language school", "Вінниця", search) is None

def test_resolve_r1_generic_name_without_city_returns_none():
    search = _search_returning("planetfitness.com")
    # ≤2 tokens ("планета фітнес") + city=None → refuse to guess (homonym risk)
    assert resolve_business_site("планета фітнес", None, search) is None

def test_resolve_r1_generic_name_with_city_allowed():
    search = _search_returning("planet-fitness-vinnytsia.com.ua")
    host = resolve_business_site("планета фітнес", "Вінниця", search)
    assert host == "planet-fitness-vinnytsia.com.ua"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_subsearch.py -k resolve -v`
Expected: FAIL with `ImportError: cannot import name 'resolve_business_site'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to crawler/crawler/discovery/subsearch.py
from crawler.discovery.blocklist import is_blocked_host
from crawler.discovery.host_quality import (DIRECTORY_HOST_SEEDS, is_low_value_host,
                                             is_news_host)
from crawler.util.hosts import bare_host, is_foreign_host, is_ru_by_geo

_SOCIAL = frozenset({"facebook.com", "instagram.com", "t.me", "tiktok.com",
                     "youtube.com", "twitter.com", "x.com", "linkedin.com"})


def _rejected_host(h: str) -> bool:
    if not h or "." not in h:
        return True
    if h in DIRECTORY_HOST_SEEDS or h in _SOCIAL:
        return True
    if any(h == s or h.endswith("." + s) for s in _SOCIAL):
        return True
    url = "https://" + h
    return (is_blocked_host(h) or is_foreign_host(url) or is_ru_by_geo(url)
            or is_low_value_host(h) or is_news_host(h))


def resolve_business_site(name, city, search) -> str | None:
    """ОДИН пошук `"<name>" <city>` → перший чистий UA-бізнес-хост, інакше None.
    R1: для генеричної назви (≤2 токени) без міста — None (не вгадуємо навмання)."""
    if not name:
        return None
    tokens = [t for t in name.split() if len(t) > 1]
    if len(tokens) <= 2 and not city:
        return None                                  # R1: homonym guard
    keyword = f'"{name}" {city}' if city else f'"{name}"'
    try:
        results = search(keyword)
    except Exception as exc:  # noqa: BLE001 — search is best-effort
        log.warning("subsearch resolve failed for %r: %s", name, exc)
        return None
    for cand in results or []:
        if getattr(cand, "type", None) != "website":
            continue
        h = bare_host(getattr(cand, "url_or_handle", None))
        if not _rejected_host(h):
            return h
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_subsearch.py -k resolve -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/subsearch.py crawler/tests/test_subsearch.py
git commit -m "feat(crawler): resolve_business_site — one web search -> official host (R1 city guard)"
```

---

### Task 4: Isolated sub-search runner — `SubSearch.run`

**Files:**
- Modify: `crawler/crawler/discovery/subsearch.py`
- Test: `crawler/tests/test_subsearch.py`

**Interfaces:**
- Consumes: `resolve_business_site` (Task 3); an isolated harvester exposing `harvest(candidates, cats, known, summary, known_hosts=None) -> int`; `SourceCandidate`.
- Produces: `class SubSearch` with `__init__(self, search, harvester)` and `run(self, businesses, cats, known, summary, budget) -> None`. Per-run dedupe by normalized name; at most `budget` searches; each business isolated in `try/except`; found offers submitted by the isolated harvester; empties simply dropped (nothing persisted).

- [ ] **Step 1: Write the failing test**

```python
# append to crawler/tests/test_subsearch.py
from crawler.discovery.subsearch import SubSearch

class _FakeHarvester:
    def __init__(self): self.crawled = []
    def harvest(self, candidates, cats, known, summary, known_hosts=None):
        self.crawled += [c.url_or_handle for c in candidates]
        return summary

def test_subsearch_resolves_and_crawls_via_isolated_harvester():
    search = _search_returning("vinnytsia-language-school.com.ua")
    hv = _FakeHarvester()
    ss = SubSearch(search, hv)
    summary = {"offers": 0, "errors": 0}
    ss.run([("vinnytsia language school", "Вінниця")], cats=None, known=set(),
           summary=summary, budget=15)
    assert hv.crawled == ["https://vinnytsia-language-school.com.ua"]

def test_subsearch_dedupes_same_name_within_pass():
    search = _search_returning("biz.com.ua")
    hv = _FakeHarvester()
    ss = SubSearch(search, hv)
    ss.run([("some unique business name", None), ("some unique business name", None)],
           cats=None, known=set(), summary={"offers": 0, "errors": 0}, budget=15)
    assert len(hv.crawled) == 1

def test_subsearch_budget_caps_number_of_searches():
    calls = {"n": 0}
    def search(kw):
        calls["n"] += 1
        return [_SC("https://biz-" + str(calls["n"]) + ".com.ua")]
    hv = _FakeHarvester()
    SubSearch(search, hv).run(
        [(f"unique business number {i}", None) for i in range(10)],
        cats=None, known=set(), summary={"offers": 0, "errors": 0}, budget=3)
    assert calls["n"] == 3

def test_subsearch_isolates_per_item_failure():
    def search(kw):
        raise RuntimeError("network down")
    hv = _FakeHarvester()
    # must not raise
    SubSearch(search, hv).run([("unique business name here", "Київ")],
                              cats=None, known=set(), summary={"offers": 0, "errors": 0},
                              budget=15)
    assert hv.crawled == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_subsearch.py -k subsearch -v`
Expected: FAIL with `ImportError: cannot import name 'SubSearch'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to crawler/crawler/discovery/subsearch.py
from crawler.models import SourceCandidate


class SubSearch:
    """Окрема фаза: resolve → ізольований harvest. Ізольований harvester має
    domain_registry=None + aggregator_store=None, тож нічого не пише в стан
    основного краулу; «нема офера → нічого» виходить само (нічого не сабмітиться)."""

    def __init__(self, search, harvester):
        self._search = search
        self._harvester = harvester

    def run(self, businesses, cats, known, summary, budget) -> None:
        seen, searches = set(), 0
        for name, city in businesses:
            key = (name or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            if searches >= budget:
                break
            searches += 1
            try:
                host = resolve_business_site(name, city, self._search)
                if not host:
                    continue
                cand = SourceCandidate(type="website",
                                       url_or_handle=f"https://{host}", name=name)
                self._harvester.harvest([cand], cats, known, summary)
            except Exception as exc:  # noqa: BLE001 — one business must not sink the rest
                log.warning("subsearch item failed for %r: %s", name, exc)
```

Note: confirm `SourceCandidate` accepts kwargs `type`, `url_or_handle`, `name` (as used across `harvest.py`). If its field is positional-only, adjust to match `crawler/crawler/models.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_subsearch.py -k subsearch -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/subsearch.py crawler/tests/test_subsearch.py
git commit -m "feat(crawler): SubSearch.run — isolated resolve+harvest, dedupe, budget, per-item isolation"
```

---

### Task 5: Harvester gate — suppress directory offers + collect businesses

**Files:**
- Modify: `crawler/crawler/discovery/harvest.py`
- Test: `crawler/tests/test_active_harvest.py`

**Interfaces:**
- Consumes: `is_directory_page` (Task 1), `extract_business` (Task 2).
- Produces: on a directory page, `_process_page` returns WITHOUT emitting offers, appends `(name, city)` to `self._directory_businesses`, and calls `self._register_directory_host(ctx.host)` (best-effort). New accessor `take_directory_businesses(self) -> list` returns and clears the queue. `ActiveHarvester.__init__` gains `register_directory_host=None` (a callable `host -> None`, default no-op).

- [ ] **Step 1: Write the failing test**

```python
# append to crawler/tests/test_active_harvest.py — mirror existing harness in that file
# (reuse its fake api/fetcher/extractor helpers; below shows the intent, adapt to them).
def test_directory_page_suppresses_offer_and_collects_business(make_harvester):
    # make_harvester: existing test helper building an ActiveHarvester with fakes.
    hv, api = make_harvester()  # api records submit_offer calls
    url = ("https://myhelp.com.ua/places/easy-english/services/"
           "znyzhka-dlia-uchasnykiv-boiovykh-dii")
    items = [FakeItem(url=url, text="Знижка 10% для УБД", locality="Вінниця",
                      title="Знижка для Easy English | MY Help")]
    hv._process_page(FakeCand(url), items, cats=None, known=set(),
                     summary={"offers": 0, "suggestions": 0, "errors": 0})
    assert api.submitted_offers == []                      # offer suppressed
    assert hv.take_directory_businesses() == [("easy english", "Вінниця")]
    assert hv.take_directory_businesses() == []            # queue cleared
```

Note: `FakeItem` must expose `title` — if the harness's item lacks a `title` attribute, add one (the detector reads title). The page title is available on the fetched item; if the real `RawItem` has no `title`, pass the title via an existing field the fetcher fills, or thread it from the fetch metadata. Verify against `crawler/crawler/models.py` and the fetcher before implementing; if no title field exists, extend `RawItem` with `title: str | None = None` in a preliminary sub-step and have the fetcher populate it from `<title>`.

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_active_harvest.py -k directory -v`
Expected: FAIL with `AttributeError: 'ActiveHarvester' object has no attribute 'take_directory_businesses'`

- [ ] **Step 3: Write minimal implementation**

```python
# in ActiveHarvester.__init__ signature, add param (default no-op keeps existing callers working):
#     register_directory_host=None,
# and in the body:
self._directory_businesses = []
self._register_directory_host_cb = register_directory_host or (lambda host: None)

# add imports at top of harvest.py:
from crawler.discovery.host_quality import is_low_value_host, is_news_host, is_directory_page
from crawler.discovery.subsearch import extract_business

# accessor:
def take_directory_businesses(self):
    out = self._directory_businesses
    self._directory_businesses = []
    return out

def _register_directory_host(self, host):
    try:
        if host:
            self._register_directory_host_cb(host)
    except Exception as exc:  # noqa: BLE001 — registration best-effort, never sinks harvest
        log.warning("directory-host registration failed for %s: %s", host, exc)

# at the START of _process_page, right after `ctx = build_page_ctx(cand, passing)`
# (compute a title from the items; use item.title if present):
title = next((getattr(it, "title", None) for it in items if getattr(it, "title", None)), None)
if is_directory_page(cand.url_or_handle, title):
    self._register_directory_host(ctx.host)
    name, city = extract_business(items, cand)
    if name:
        self._directory_businesses.append((name, city))
    return structural_provider   # НЕ емітимо офери з каталог-сторінки
```

Important: place the directory check AFTER `structural_provider` and `ctx` are computed but BEFORE the offer-collection loop, so no offers are submitted. Verify variable names against the current `_process_page` (see `harvest.py:238` region).

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_active_harvest.py -k directory -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/harvest.py crawler/tests/test_active_harvest.py
git commit -m "feat(crawler): suppress directory-page offers, collect businesses for sub-search"
```

---

### Task 6: Backend — `directory_hosts` table + migration + register/sweep CRUD

**Files:**
- Create: `backend/app/models/directory_host.py`
- Modify: `backend/app/models/__init__.py` (register model)
- Create: `backend/alembic/versions/<rev>_directory_hosts.py`
- Create: `backend/app/crud/directory_host.py`
- Test: `backend/tests/test_directory_hosts.py`

**Interfaces:**
- Produces: model `DirectoryHost(id, host UNIQUE, created_at)`; `directory_host.register(db, host) -> bool` (True if newly created; on new registration runs the sweep); `directory_host.list_hosts(db) -> list[str]`; `directory_host.is_directory(db, host) -> bool`. Sweep: soft-reject offers with `created_by == crawler` AND `status == pending_review` AND host(site_url|article_url) == host.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_directory_hosts.py
from app.crud import directory_host as dh
from app.models import Offer
from app.models.enums import OfferStatus, CreatedBy

def _mk_offer(db, host, status=OfferStatus.pending_review, created_by=CreatedBy.crawler):
    o = Offer(title="t", status=status, created_by=created_by,
              site_url=f"https://{host}", article_url=f"https://{host}/x")
    db.add(o); db.commit(); db.refresh(o); return o

def test_register_is_idempotent(db_session):
    assert dh.register(db_session, "myhelp.com.ua") is True
    assert dh.register(db_session, "myhelp.com.ua") is False
    assert dh.list_hosts(db_session) == ["myhelp.com.ua"]

def test_register_sweeps_existing_crawler_pending_offers(db_session):
    keep_pub = _mk_offer(db_session, "myhelp.com.ua", status=OfferStatus.published)
    keep_other = _mk_offer(db_session, "otherbiz.com.ua")
    victim = _mk_offer(db_session, "myhelp.com.ua")
    dh.register(db_session, "myhelp.com.ua")
    db_session.refresh(victim); db_session.refresh(keep_pub); db_session.refresh(keep_other)
    assert victim.status == OfferStatus.rejected
    assert keep_pub.status == OfferStatus.published      # published untouched
    assert keep_other.status == OfferStatus.pending_review  # other host untouched
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_directory_hosts.py -v`
Expected: FAIL (module `app.crud.directory_host` missing)

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/models/directory_host.py
from datetime import datetime
from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

class DirectoryHost(Base):
    __tablename__ = "directory_hosts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    host: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(),
                                                 nullable=False)
```

```python
# backend/app/crud/directory_host.py
from app.crud.blocked_host import bare_host
from app.models.directory_host import DirectoryHost
from app.models.offer import Offer
from app.models.enums import OfferStatus, CreatedBy

def list_hosts(db) -> list[str]:
    return [r.host for r in db.query(DirectoryHost).all()]

def is_directory(db, host) -> bool:
    h = bare_host(host)
    return h is not None and db.query(DirectoryHost).filter(DirectoryHost.host == h).first() is not None

def _sweep(db, host) -> None:
    """Soft-reject наявних crawler+pending оферів цього хоста (site_url|article_url)."""
    q = (db.query(Offer)
         .filter(Offer.created_by == CreatedBy.crawler,
                 Offer.status == OfferStatus.pending_review))
    for o in q.all():
        if bare_host(o.site_url) == host or bare_host(o.article_url) == host:
            o.status = OfferStatus.rejected
    db.commit()

def register(db, host) -> bool:
    h = bare_host(host)
    if not h:
        return False
    if db.query(DirectoryHost).filter(DirectoryHost.host == h).first() is not None:
        return False                                   # idempotent
    db.add(DirectoryHost(host=h)); db.commit()
    _sweep(db, h)
    return True
```

Register the model: add `from app.models.directory_host import DirectoryHost` to `backend/app/models/__init__.py` (and `__all__` if present).

Create the migration (autogenerate, then verify it only adds `directory_hosts`):
```bash
cd backend && ./.venv/Scripts/alembic.exe revision --autogenerate -m "directory_hosts"
```
Confirm the generated `upgrade()` creates the `directory_hosts` table with `host` unique; edit if autogenerate added unrelated churn.

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_directory_hosts.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/directory_host.py backend/app/models/__init__.py backend/app/crud/directory_host.py backend/alembic/versions/*directory_hosts*.py backend/tests/test_directory_hosts.py
git commit -m "feat(backend): directory_hosts table + register-with-sweep (autonomous retro-reject)"
```

---

### Task 7: Backend — internal register endpoint + create-time gate

**Files:**
- Modify: `backend/app/routers/internal.py`
- Modify: `backend/app/crud/offer.py` (create-time gate)
- Test: `backend/tests/test_directory_hosts.py`

**Interfaces:**
- Consumes: `directory_host.register`, `directory_host.is_directory` (Task 6).
- Produces: `POST /api/internal/directory-hosts {host}` → `{registered: bool}` (X-API-Key auth like other internal routes). `create_offer` force-rejects a new crawler offer whose source host is a registered directory host (parallel to `_blocked_source_host`).

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_directory_hosts.py
from app.core.config import settings
_KEY = {"X-API-Key": settings.crawler_api_key}

def test_internal_register_endpoint_and_sweep(client, db_session):
    o = _mk_offer(db_session, "myhelp.com.ua")   # helper from Task 6
    r = client.post("/api/internal/directory-hosts", headers=_KEY, json={"host": "myhelp.com.ua"})
    assert r.status_code == 200 and r.json()["registered"] is True
    db_session.refresh(o)
    assert o.status.value == "rejected"

def test_create_gate_rejects_new_offer_from_directory_host(client, db_session):
    client.post("/api/internal/directory-hosts", headers=_KEY, json={"host": "myhelp.com.ua"})
    payload = {"title": "t", "provider": "MY Help", "site_url": "https://myhelp.com.ua",
               "article_url": "https://myhelp.com.ua/places/x/services/y", "body": "b",
               "content_hash": "hash-dir-1"}
    r = client.post("/api/internal/offers", headers=_KEY, json=payload)
    assert r.status_code == 200 and r.json()["status"] == "rejected"
```

Note: match `payload` to the real `InternalOfferCreate` schema (required fields) — inspect `backend/app/schemas/offer.py` and copy an existing internal-create test payload from `backend/tests/`.

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_directory_hosts.py -k "internal or create_gate" -v`
Expected: FAIL (404 on the endpoint; create gate not applied)

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/routers/internal.py — add near the other internal routes
from pydantic import BaseModel
from app.crud import directory_host as directory_host_crud

class DirectoryHostIn(BaseModel):
    host: str

class DirectoryHostOut(BaseModel):
    registered: bool

@router.post("/directory-hosts", response_model=DirectoryHostOut)
def register_directory_host(data: DirectoryHostIn, db: Session = Depends(get_db)):
    return DirectoryHostOut(registered=directory_host_crud.register(db, data.host))
```

```python
# backend/app/crud/offer.py — extend the create-time rejection
# near: blocked = crawler and _blocked_source_host(db, data) is not None
from app.crud import directory_host as directory_host_crud   # top-level import

def _directory_source_host(db, data) -> str | None:
    for val in (getattr(data, "site_url", None), getattr(data, "article_url", None)):
        h = _source_host(val)
        if h and directory_host_crud.is_directory(db, h):
            return h
    return None

# in create_offer, update the guard:
blocked = crawler and (_blocked_source_host(db, data) is not None
                       or _directory_source_host(db, data) is not None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_directory_hosts.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/internal.py backend/app/crud/offer.py backend/tests/test_directory_hosts.py
git commit -m "feat(backend): internal directory-host register endpoint + create-time reject gate"
```

---

### Task 8: Crawler API client — `register_directory_host`

**Files:**
- Modify: `crawler/crawler/api_client.py`
- Test: `crawler/tests/test_api_client.py`

**Interfaces:**
- Produces: `ApiClient.register_directory_host(self, host: str) -> None` — POST `/api/internal/directory-hosts` with X-API-Key; best-effort (network failure logged, not raised).

- [ ] **Step 1: Write the failing test**

```python
# append to crawler/tests/test_api_client.py — mirror the existing httpx-mock harness there
def test_register_directory_host_posts_host(api_client, mock_transport):
    api_client.register_directory_host("myhelp.com.ua")
    req = mock_transport.last_request
    assert req.url.path == "/api/internal/directory-hosts"
    assert req.headers.get("X-API-Key")
    import json
    assert json.loads(req.content)["host"] == "myhelp.com.ua"
```

Adapt to the existing test harness in `test_api_client.py` (how it builds `api_client` and inspects requests).

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_api_client.py -k directory -v`
Expected: FAIL with `AttributeError: ... 'register_directory_host'`

- [ ] **Step 3: Write minimal implementation**

```python
# crawler/crawler/api_client.py — mirror an existing internal POST method (e.g. submit_offer)
def register_directory_host(self, host: str) -> None:
    try:
        self._post("/api/internal/directory-hosts", json={"host": host})
    except Exception as exc:  # noqa: BLE001 — best-effort; never sink the crawl
        log.warning("register_directory_host failed for %s: %s", host, exc)
```

Match `self._post` / headers / logging to the actual client (see how `submit_offer` is implemented in the same file).

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_api_client.py -k directory -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/api_client.py crawler/tests/test_api_client.py
git commit -m "feat(crawler): api_client.register_directory_host (internal, best-effort)"
```

---

### Task 9: Config + wiring — build the isolated sub-search harvester and phase

**Files:**
- Modify: `crawler/crawler/config.py`
- Modify: `crawler/crawler/wiring.py`
- Modify: `crawler/crawler/runner.py`
- Test: `crawler/tests/test_wiring.py`, `crawler/tests/test_runner_*.py` (or a new `test_runner_subsearch.py`)

**Interfaces:**
- Consumes: `SubSearch` (Task 4), `ActiveHarvester` (Task 5), the search provider from `search_pass.provider_for_site_query()`, `api.register_directory_host` (Task 8).
- Produces: config `subsearch_enabled: bool = True`, `subsearch_search_budget: int = 15`; wiring builds a second **isolated** `ActiveHarvester` (`domain_registry=None`, `aggregator_store=None`, its own small `fetch_budget`) and a `SubSearch`; the main harvester is constructed with `register_directory_host=api.register_directory_host`; `runner.run_active`, after the main `harvester.harvest(...)`, runs the sub-search **only when `ddg_allowed`** (skipped under backoff), passing `budget=config.subsearch_search_budget`.

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_runner_subsearch.py
def test_run_active_runs_subsearch_when_ddg_allowed(make_runner_with_subsearch):
    r, main_hv, subsearch = make_runner_with_subsearch()
    main_hv._directory_businesses = [("easy english", "Вінниця")]
    r.run_active(ddg_allowed=True)
    assert subsearch.ran_with == [("easy english", "Вінниця")]  # fake SubSearch records run()

def test_run_active_skips_subsearch_under_backoff(make_runner_with_subsearch):
    r, main_hv, subsearch = make_runner_with_subsearch()
    main_hv._directory_businesses = [("easy english", "Вінниця")]
    r.run_active(ddg_allowed=False)
    assert subsearch.ran_with is None                            # skipped under backoff
```

Build `make_runner_with_subsearch` from the existing runner-test helpers (fakes for search_pass/harvester/api); `subsearch` is a fake whose `run(businesses, ...)` records `ran_with`.

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_runner_subsearch.py -v`
Expected: FAIL (runner has no sub-search phase)

- [ ] **Step 3: Write minimal implementation**

```python
# crawler/crawler/config.py — add fields
subsearch_enabled: bool = True
subsearch_search_budget: int = 15
subsearch_fetch_budget: int = 20
```

```python
# crawler/crawler/runner.py — accept subsearch in __init__ (default None) and store it:
#   def __init__(self, ..., subsearch=None):
#       self._subsearch = subsearch
# In run_active, AFTER `self._harvester.harvest(candidates, ...)` and inside the try:
if (self._subsearch is not None and ddg_allowed
        and self._harvester is not None):
    businesses = self._harvester.take_directory_businesses()
    if businesses:
        self._subsearch.run(businesses, cats, known, summary,
                            budget=self._subsearch_budget)
```

Store `self._subsearch_budget = subsearch_search_budget` (thread it through `__init__`). Ensure `cats`, `known`, `summary` are in scope at that point in `run_active` (they are used by the harvest call above).

```python
# crawler/crawler/wiring.py — after building the main harvester:
subsearch = None
if config.subsearch_enabled:
    iso_harvester = ActiveHarvester(
        api, fetchers, extractor, rate_limiter,
        fetch_budget=config.subsearch_fetch_budget,
        walker=walker, domain_rate_limiter=domain_rate_limiter,
        domain_registry=None, aggregator_store=None,        # ISOLATION
        hardening_enabled=config.hardening_enabled)
    subsearch = SubSearch(search_pass.provider_for_site_query(), iso_harvester)
# construct the MAIN harvester with register callback:
harvester = ActiveHarvester(..., register_directory_host=api.register_directory_host, ...)
# pass subsearch into Runner(...)
```

Match the exact `ActiveHarvester(...)` kwargs to the existing main construction (`wiring.py:281`), and add `subsearch=subsearch` to the `Runner(...)` call. Import `from crawler.discovery.subsearch import SubSearch`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_runner_subsearch.py tests/test_wiring.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/config.py crawler/crawler/wiring.py crawler/crawler/runner.py crawler/tests/test_runner_subsearch.py
git commit -m "feat(crawler): wire isolated sub-search phase (backoff-aware, budget-capped)"
```

---

### Task 10: Full crawler + backend suite green; deploy

**Files:** none (verification + deploy)

- [ ] **Step 1: Run the full crawler suite**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS (only the known StarletteDeprecationWarning, if any).

- [ ] **Step 2: Run the full backend suite** (needs `mysql-container` up)

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS.

- [ ] **Step 3: Apply the migration + rebuild containers**

```bash
docker compose up -d --build backend crawler
```
The backend entrypoint runs `alembic upgrade`; confirm `directory_hosts` exists:
```bash
docker exec ubd_probe-db-1 mysql -uroot -pmy-secret-pw -D ubd -e "SHOW TABLES LIKE 'directory_hosts';"
```

- [ ] **Step 4: Real-data validation (the 11 myhelp offers)**

Trigger an active pass (or wait for the loop); then confirm the myhelp offers were auto-rejected and the host registered:
```bash
docker exec ubd_probe-db-1 mysql -uroot -pmy-secret-pw -D ubd -e "SELECT status, count(*) FROM offers WHERE site_url LIKE '%myhelp.com.ua%' GROUP BY status;"
docker exec ubd_probe-db-1 mysql -uroot -pmy-secret-pw -D ubd -e "SELECT host FROM directory_hosts;"
```
Expected: myhelp offers move to `rejected`; `myhelp.com.ua` present in `directory_hosts`. Watch crawler logs for `subsearch` activity and any new business-site offers arriving in moderation.

- [ ] **Step 5: Commit any fixups + finish the branch**

Use the `superpowers:finishing-a-development-branch` skill to merge `feat/directory-page-recovery` into main.

---

## Notes for the implementer

- **`RawItem.title`:** Task 5 depends on a page title for `is_directory_page`. Verify whether `RawItem` (`crawler/crawler/models.py`) carries the `<title>`. If not, add `title: str | None = None` and populate it in the fetcher where `site_name`/`site_tagline` are set — do this as the first sub-step of Task 5 (its own red/green/commit) before the gate test.
- **`SourceCandidate` constructor:** confirm keyword names (`type`, `url_or_handle`, `name`) against `crawler/crawler/models.py`; adjust Task 4/9 if positional.
- **Provider callable shape:** `search_pass.provider_for_site_query()` returns a provider whose `__call__(keyword, page=1)` yields `list[SourceCandidate]`. `resolve_business_site` calls it as `search(keyword)` — wrap if the live provider needs the `page` arg (`lambda kw: provider(kw, 1)`).
- **Isolation check:** the isolated harvester is built with `domain_registry=None` and `aggregator_store=None`; grep the final wiring to be sure no main-crawl store is shared into it.
