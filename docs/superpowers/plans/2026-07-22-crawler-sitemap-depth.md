# Crawler sitemap-depth domain expansion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand each website discovery-candidate from its homepage to promo pages
(`/sale`, `/акції`, …) via `robots.txt → sitemap → URL-filter → BFS≤2`, with a per-domain
politeness layer, so the brand-feed → depth → moderation chain actually yields offers.

**Architecture:** Variant A — a dedicated `DomainWalker` invoked by `ActiveHarvester` at the
wiring point `harvest.py:48`. The walker resolves a domain's promo URLs (robots-cache +
sitemap + BFS fallback) and returns a `WalkPlan(domain, urls, crawl_delay)`. The harvester
fetches each URL with the **unchanged** `WebsiteFetcher` and runs the **unchanged**
attribution→moderation pipeline **per page**. A shared `DomainRateLimiter` serialises every
per-domain fetch. Only the harvest path is touched; DB-source crawling and the telegram path
are byte-for-byte unchanged.

**Tech Stack:** Python 3, `httpx` (injected clients), stdlib `urllib.robotparser`,
`xml.etree.ElementTree`, `gzip`, `pytest`. Windows venv at `crawler/.venv`.

## Global Constraints

- Best-effort everywhere: **the network NEVER crashes or blocks a pass** — every fetch/parse
  failure returns empty/allow-all and logs a warning.
- Human moderation gate stays; deterministic extractor core stays; **`WebsiteFetcher` is not
  modified**; DB-source crawl (`Runner._crawl_source`) and the telegram path are unchanged.
- Existing **228** crawler tests stay green.
- All new HTTP goes through an **injected** client (testability), like `BrandResolver`.
- Robots UA constant: `ROBOTS_UA = "UBDCrawler"`.
- Run tests from `crawler/`: `./.venv/Scripts/python.exe -m pytest -q`.
- Feature branch: `feat/crawler-sitemap-depth`. Commit after every task.

---

### Task 1: Promo-URL filter

**Files:**
- Create: `crawler/discovery/walker.py` (module-level filter only; the `DomainWalker` class is added in Task 5)
- Test: `crawler/tests/test_promo_url_filter.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `url_is_promo(url: str) -> bool`; module constant `_PROMO_URL_TOKENS: tuple[str, ...]`.

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_promo_url_filter.py
import pytest

from crawler.discovery.walker import url_is_promo


@pytest.mark.parametrize("url", [
    "https://shop.ua/sale",
    "https://shop.ua/promo/summer",
    "https://shop.ua/akcii",
    "https://shop.ua/akcii-znizhki",
    "https://shop.ua/rozprodazh",
    "https://shop.ua/discount",
    "https://shop.ua/offers/black-friday",
    "https://shop.ua/deals",
    "https://shop.ua/%D0%B0%D0%BA%D1%86%D1%96%D1%97",   # /акції percent-encoded
    "https://shop.ua/%D0%B7%D0%BD%D0%B8%D0%B6%D0%BA%D0%B8",  # /знижки
    "https://shop.ua/спецпропозиції",
])
def test_promo_urls_match(url):
    assert url_is_promo(url) is True


@pytest.mark.parametrize("url", [
    "https://shop.ua/",
    "https://shop.ua/product/12345",
    "https://shop.ua/blog/how-to",
    "https://shop.ua/about",
    "https://shop.ua/cart",
])
def test_non_promo_urls_do_not_match(url):
    assert url_is_promo(url) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_promo_url_filter.py -q`
Expected: FAIL — `ModuleNotFoundError: crawler.discovery.walker` / `ImportError`.

- [ ] **Step 3: Write minimal implementation**

```python
# crawler/discovery/walker.py
"""Domain-depth expansion: turn a website homepage candidate into a small set of
promo-relevant page URLs (robots + sitemap + BFS fallback) under a per-domain politeness
layer. This module hosts the promo-URL filter; DomainWalker (added later) orchestrates."""

from urllib.parse import unquote, urlsplit

# Curated promo tokens (latin + cyrillic), matched against the lowercased, percent-decoded
# URL path. Same curation technique as query_grid.BRANDS.
_PROMO_URL_TOKENS: tuple[str, ...] = (
    "sale", "promo", "akci", "akcii", "aktsi", "znizhk", "znyzhk", "rozprodazh",
    "discount", "discounts", "offer", "offers", "deal", "deals", "black-friday",
    "blackfriday", "specialpropoz", "spec-propoz", "cyber-monday",
    "акці", "акция", "знижк", "розпродаж", "спецпропоз", "дисконт", "вигід",
)


def url_is_promo(url: str) -> bool:
    """True if the URL path contains any curated promo token (case/encoding insensitive)."""
    path = unquote(urlsplit(url or "").path).lower()
    return any(tok in path for tok in _PROMO_URL_TOKENS)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_promo_url_filter.py -q`
Expected: PASS (16 cases).

- [ ] **Step 5: Commit**

```bash
git add crawler/discovery/walker.py crawler/tests/test_promo_url_filter.py
git commit -m "feat(crawler): promo-URL filter for domain-depth expansion"
```

---

### Task 2: DomainRateLimiter

**Files:**
- Modify: `crawler/ratelimit.py` (append a new class; leave `RateLimiter` untouched)
- Test: `crawler/tests/test_ratelimit.py` (append)

**Interfaces:**
- Consumes: nothing.
- Produces: `DomainRateLimiter(min_delay: float, sleep=time.sleep, monotonic=time.monotonic)`
  with `wait(domain: str, delay: float | None = None) -> None`. The effective delay for a
  call is `max(min_delay, delay or 0)`; waits are tracked **per domain** independently.

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_ratelimit.py  (append; keep existing imports/tests)
from crawler.ratelimit import DomainRateLimiter


def _fake_clock():
    t = {"now": 0.0}
    return t


def test_domain_rate_limiter_waits_min_delay_per_domain():
    slept = []
    t = {"now": 100.0}
    rl = DomainRateLimiter(min_delay=5.0, sleep=lambda s: slept.append(s),
                           monotonic=lambda: t["now"])
    rl.wait("a.ua")            # first call for domain -> no wait
    rl.wait("a.ua")            # immediate second call -> waits full min_delay
    assert slept == [5.0]


def test_domain_rate_limiter_isolates_domains():
    slept = []
    t = {"now": 0.0}
    rl = DomainRateLimiter(min_delay=5.0, sleep=lambda s: slept.append(s),
                           monotonic=lambda: t["now"])
    rl.wait("a.ua")
    rl.wait("b.ua")            # different domain -> no wait
    assert slept == []


def test_domain_rate_limiter_per_call_delay_overrides_min():
    slept = []
    t = {"now": 0.0}
    rl = DomainRateLimiter(min_delay=2.0, sleep=lambda s: slept.append(s),
                           monotonic=lambda: t["now"])
    rl.wait("a.ua")
    rl.wait("a.ua", delay=9.0)  # crawl-delay bigger than floor -> waits 9.0
    assert slept == [9.0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_ratelimit.py -q`
Expected: FAIL — `ImportError: cannot import name 'DomainRateLimiter'`.

- [ ] **Step 3: Write minimal implementation**

```python
# crawler/ratelimit.py  (append below the existing RateLimiter class)
class DomainRateLimiter:
    """Per-domain minimum-delay limiter. The per-call `delay` (e.g. robots Crawl-delay)
    raises the floor for that call; each domain is tracked independently."""

    def __init__(self, min_delay: float, sleep=time.sleep, monotonic=time.monotonic):
        self._min_delay = min_delay
        self._sleep = sleep
        self._monotonic = monotonic
        self._last: dict[str, float] = {}

    def wait(self, domain: str, delay: float | None = None) -> None:
        effective = max(self._min_delay, delay or 0.0)
        now = self._monotonic()
        last = self._last.get(domain)
        if last is not None:
            remaining = effective - (now - last)
            if remaining > 0:
                self._sleep(remaining)
                now = self._monotonic() if self._monotonic() > now else now + remaining
        self._last[domain] = now
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_ratelimit.py -q`
Expected: PASS (existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add crawler/ratelimit.py crawler/tests/test_ratelimit.py
git commit -m "feat(crawler): per-domain rate limiter"
```

---

### Task 3: RobotsPolicy (fetch + persistent cache + parse)

**Files:**
- Create: `crawler/discovery/robots.py`
- Test: `crawler/tests/test_robots.py`

**Interfaces:**
- Consumes: `DomainRateLimiter` (Task 2) for the robots fetch.
- Produces:
  - `ROBOTS_UA = "UBDCrawler"`.
  - `ParsedRobots` with `can_fetch(url: str) -> bool`, `crawl_delay() -> float | None`,
    `sitemaps() -> list[str]`.
  - `RobotsPolicy(client, rate_limiter, path: str, ttl_seconds: float, clock=time.time)`
    with `get(domain: str) -> ParsedRobots`. `client.get(url)` is the injected HTTP call.
    Cache persists to `path` as JSON `{domain: {"fetched_at": float, "text": str}}` (atomic write).

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_robots.py
import json

from crawler.discovery.robots import ParsedRobots, RobotsPolicy


class FakeResp:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeClient:
    def __init__(self, text="", status=200, boom=False):
        self._text, self._status, self._boom = text, status, boom
        self.calls = 0

    def get(self, url, **kw):
        self.calls += 1
        if self._boom:
            raise RuntimeError("network down")
        return FakeResp(self._text, self._status)


class NoWait:
    def wait(self, *a, **k):
        pass


ROBOTS_TXT = (
    "User-agent: *\n"
    "Disallow: /cart\n"
    "Crawl-delay: 7\n"
    "Sitemap: https://shop.ua/sitemap.xml\n"
    "Sitemap: https://shop.ua/sitemap-2.xml\n"
)


def test_parses_sitemaps_crawl_delay_and_disallow(tmp_path):
    client = FakeClient(text=ROBOTS_TXT)
    pol = RobotsPolicy(client, NoWait(), str(tmp_path / "r.json"), ttl_seconds=1000)
    r = pol.get("shop.ua")
    assert set(r.sitemaps()) == {"https://shop.ua/sitemap.xml", "https://shop.ua/sitemap-2.xml"}
    assert r.crawl_delay() == 7.0
    assert r.can_fetch("https://shop.ua/sale") is True
    assert r.can_fetch("https://shop.ua/cart") is False


def test_cache_persists_and_avoids_refetch(tmp_path):
    path = str(tmp_path / "r.json")
    client = FakeClient(text=ROBOTS_TXT)
    RobotsPolicy(client, NoWait(), path, ttl_seconds=1000).get("shop.ua")
    assert client.calls == 1
    # a fresh policy reading the same file must NOT hit the network
    client2 = FakeClient(text=ROBOTS_TXT)
    RobotsPolicy(client2, NoWait(), path, ttl_seconds=1000).get("shop.ua")
    assert client2.calls == 0
    saved = json.loads(open(path, encoding="utf-8").read())
    assert "shop.ua" in saved


def test_stale_entry_refetches(tmp_path):
    path = str(tmp_path / "r.json")
    clk = {"now": 1000.0}
    client = FakeClient(text=ROBOTS_TXT)
    RobotsPolicy(client, NoWait(), path, ttl_seconds=100,
                 clock=lambda: clk["now"]).get("shop.ua")
    clk["now"] = 2000.0     # advance well past ttl
    client2 = FakeClient(text=ROBOTS_TXT)
    RobotsPolicy(client2, NoWait(), path, ttl_seconds=100,
                 clock=lambda: clk["now"]).get("shop.ua")
    assert client2.calls == 1


def test_fetch_failure_allows_all(tmp_path):
    client = FakeClient(boom=True)
    pol = RobotsPolicy(client, NoWait(), str(tmp_path / "r.json"), ttl_seconds=1000)
    r = pol.get("shop.ua")
    assert r.can_fetch("https://shop.ua/cart") is True
    assert r.crawl_delay() is None
    assert r.sitemaps() == []


def test_corrupt_cache_file_starts_clean(tmp_path):
    path = str(tmp_path / "r.json")
    open(path, "w", encoding="utf-8").write("{not json")
    client = FakeClient(text=ROBOTS_TXT)
    pol = RobotsPolicy(client, NoWait(), path, ttl_seconds=1000)
    assert pol.get("shop.ua").crawl_delay() == 7.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_robots.py -q`
Expected: FAIL — `ModuleNotFoundError: crawler.discovery.robots`.

- [ ] **Step 3: Write minimal implementation**

```python
# crawler/discovery/robots.py
"""Per-domain robots.txt: fetch (rate-limited, injected client), persist raw text to a JSON
cache with a freshness gate, and parse on read via stdlib urllib.robotparser. Best-effort:
any failure yields an allow-all policy. Mirrors the BrandDomainCache persistence pattern."""

import json
import logging
import os
import time
from urllib.robotparser import RobotFileParser

log = logging.getLogger(__name__)

ROBOTS_UA = "UBDCrawler"


class ParsedRobots:
    """Thin wrapper over a parsed RobotFileParser. An empty/failed parse allows everything."""

    def __init__(self, text: str):
        self._rp = RobotFileParser()
        self._rp.parse((text or "").splitlines())

    def can_fetch(self, url: str) -> bool:
        try:
            return self._rp.can_fetch(ROBOTS_UA, url)
        except Exception:  # noqa: BLE001 — never block on a parser edge case
            return True

    def crawl_delay(self) -> float | None:
        try:
            d = self._rp.crawl_delay(ROBOTS_UA)
            return float(d) if d is not None else None
        except Exception:  # noqa: BLE001
            return None

    def sitemaps(self) -> list[str]:
        try:
            return list(self._rp.site_maps() or [])
        except Exception:  # noqa: BLE001
            return []


class RobotsPolicy:
    def __init__(self, client, rate_limiter, path: str, ttl_seconds: float,
                 clock=time.time):
        self._client = client
        self._rl = rate_limiter
        self._path = path
        self._ttl = ttl_seconds
        self._clock = clock
        self._data = self._load()

    def _load(self) -> dict:
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        directory = os.path.dirname(self._path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = f"{self._path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False)
        os.replace(tmp, self._path)

    def _fresh(self, entry: dict) -> bool:
        return self._clock() - float(entry.get("fetched_at", 0.0)) < self._ttl

    def get(self, domain: str) -> ParsedRobots:
        entry = self._data.get(domain)
        if isinstance(entry, dict) and self._fresh(entry):
            return ParsedRobots(entry.get("text", ""))
        text = self._fetch(domain)
        self._data[domain] = {"fetched_at": self._clock(), "text": text}
        try:
            self._save()
        except OSError as exc:  # noqa: BLE001 — cache write is best-effort
            log.warning("robots cache save failed: %s", exc)
        return ParsedRobots(text)

    def _fetch(self, domain: str) -> str:
        url = f"https://{domain}/robots.txt"
        try:
            self._rl.wait(domain)
            resp = self._client.get(url, follow_redirects=True)
            resp.raise_for_status()
            return resp.text or ""
        except Exception as exc:  # noqa: BLE001 — allow-all on any failure
            log.warning("robots fetch failed for %s: %s", domain, exc)
            return ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_robots.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add crawler/discovery/robots.py crawler/tests/test_robots.py
git commit -m "feat(crawler): robots.txt policy with persistent cache"
```

---

### Task 4: Sitemap collector

**Files:**
- Create: `crawler/discovery/sitemap.py`
- Test: `crawler/tests/test_sitemap.py`

**Interfaces:**
- Consumes: `DomainRateLimiter` (Task 2).
- Produces: `collect_sitemap_urls(sitemap_urls: list[str], client, rate_limiter, domain: str,
  crawl_delay: float | None, max_docs: int) -> list[str]` — walks sitemap-index → child
  sitemaps → `<urlset>`, supports gzip, caps the number of sitemap documents fetched at
  `max_docs`, best-effort (any doc failure → skipped). Returns de-duplicated page `<loc>` URLs.

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_sitemap.py
import gzip

from crawler.discovery.sitemap import collect_sitemap_urls


class NoWait:
    def wait(self, *a, **k):
        pass


URLSET = (
    '<?xml version="1.0"?>'
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    '<url><loc>https://shop.ua/sale</loc></url>'
    '<url><loc>https://shop.ua/product/1</loc></url>'
    '</urlset>'
)
INDEX = (
    '<?xml version="1.0"?>'
    '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    '<sitemap><loc>https://shop.ua/child.xml</loc></sitemap>'
    '</sitemapindex>'
)


class Resp:
    def __init__(self, content, text=None, status=200):
        self.content = content
        self.text = text if text is not None else (
            content.decode() if isinstance(content, bytes) else content)
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")


class MapClient:
    def __init__(self, mapping):
        self._m = mapping
        self.calls = []

    def get(self, url, **kw):
        self.calls.append(url)
        body = self._m[url]
        return Resp(body if isinstance(body, bytes) else body.encode())


def test_urlset_returns_locs():
    client = MapClient({"https://shop.ua/sitemap.xml": URLSET})
    urls = collect_sitemap_urls(["https://shop.ua/sitemap.xml"], client, NoWait(),
                                "shop.ua", None, max_docs=10)
    assert urls == ["https://shop.ua/sale", "https://shop.ua/product/1"]


def test_index_recurses_into_children():
    client = MapClient({"https://shop.ua/root.xml": INDEX,
                        "https://shop.ua/child.xml": URLSET})
    urls = collect_sitemap_urls(["https://shop.ua/root.xml"], client, NoWait(),
                                "shop.ua", None, max_docs=10)
    assert "https://shop.ua/sale" in urls


def test_gzip_sitemap_is_decoded():
    client = MapClient({"https://shop.ua/sitemap.xml.gz": gzip.compress(URLSET.encode())})
    urls = collect_sitemap_urls(["https://shop.ua/sitemap.xml.gz"], client, NoWait(),
                                "shop.ua", None, max_docs=10)
    assert "https://shop.ua/sale" in urls


def test_max_docs_caps_fetches():
    client = MapClient({"https://shop.ua/root.xml": INDEX,
                        "https://shop.ua/child.xml": URLSET})
    collect_sitemap_urls(["https://shop.ua/root.xml"], client, NoWait(),
                         "shop.ua", None, max_docs=1)
    assert client.calls == ["https://shop.ua/root.xml"]  # child not fetched


def test_malformed_xml_yields_empty():
    client = MapClient({"https://shop.ua/sitemap.xml": "<not-xml"})
    urls = collect_sitemap_urls(["https://shop.ua/sitemap.xml"], client, NoWait(),
                                "shop.ua", None, max_docs=10)
    assert urls == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_sitemap.py -q`
Expected: FAIL — `ModuleNotFoundError: crawler.discovery.sitemap`.

- [ ] **Step 3: Write minimal implementation**

```python
# crawler/discovery/sitemap.py
"""Best-effort sitemap collector: walk sitemap-index -> child sitemaps -> <urlset>, decode
gzip, cap the number of documents fetched, and return de-duplicated page URLs. Any document
that fails to fetch or parse is skipped; the walk never raises."""

import gzip
import logging
from xml.etree import ElementTree as ET

log = logging.getLogger(__name__)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]  # strip XML namespace


def _decode(resp) -> str:
    content = getattr(resp, "content", None)
    if isinstance(content, (bytes, bytearray)):
        if content[:2] == b"\x1f\x8b":
            try:
                return gzip.decompress(content).decode("utf-8", "replace")
            except OSError:
                return ""
        return content.decode("utf-8", "replace")
    return resp.text or ""


def collect_sitemap_urls(sitemap_urls, client, rate_limiter, domain, crawl_delay,
                         max_docs) -> list[str]:
    pages: list[str] = []
    seen_pages: set[str] = set()
    queue = list(sitemap_urls)
    visited: set[str] = set()
    fetched = 0
    while queue and fetched < max_docs:
        sm = queue.pop(0)
        if sm in visited:
            continue
        visited.add(sm)
        fetched += 1
        try:
            rate_limiter.wait(domain, crawl_delay)
            resp = client.get(sm, follow_redirects=True)
            resp.raise_for_status()
            root = ET.fromstring(_decode(resp))
        except Exception as exc:  # noqa: BLE001 — skip a bad document, keep going
            log.warning("sitemap fetch/parse failed for %s: %s", sm, exc)
            continue
        is_index = _local(root.tag) == "sitemapindex"
        for loc in root.iter():
            if _local(loc.tag) != "loc" or not (loc.text and loc.text.strip()):
                continue
            value = loc.text.strip()
            if is_index:
                queue.append(value)
            elif value not in seen_pages:
                seen_pages.add(value)
                pages.append(value)
    return pages
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_sitemap.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add crawler/discovery/sitemap.py crawler/tests/test_sitemap.py
git commit -m "feat(crawler): best-effort sitemap URL collector"
```

---

### Task 5: DomainWalker

**Files:**
- Modify: `crawler/discovery/walker.py` (add `WalkPlan`, `DomainWalker`; keep `url_is_promo`)
- Test: `crawler/tests/test_walker.py`

**Interfaces:**
- Consumes: `url_is_promo` (Task 1), `RobotsPolicy`/`ParsedRobots` (Task 3),
  `collect_sitemap_urls` (Task 4), `DomainRateLimiter` (Task 2), `SourceCandidate`,
  `passive.normalize_ref`.
- Produces:
  - `WalkPlan(domain: str, urls: list[str], crawl_delay: float | None)` (dataclass).
  - `DomainWalker(client, robots, rate_limiter, *, domain_page_cap=10, sitemap_max_docs=20,
    bfs_max_depth=2, bfs_max_pages=8, bfs_trigger_min=3, domain_min_delay=3.0,
    crawl_delay_cap=30.0)` with `walk(cand: SourceCandidate) -> WalkPlan`.
    `walk` never raises; on total failure it returns `WalkPlan(domain, [homepage], floor)`.

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_walker.py
from crawler.discovery import walker as walker_mod
from crawler.discovery.walker import DomainWalker, WalkPlan
from crawler.models import SourceCandidate


class NoWait:
    def wait(self, *a, **k):
        pass


class FakeRobots:
    """ParsedRobots stand-in."""
    def __init__(self, sitemaps=None, crawl_delay=None, disallow=()):
        self._sm = sitemaps or []
        self._cd = crawl_delay
        self._disallow = tuple(disallow)

    def can_fetch(self, url):
        return not any(d in url for d in self._disallow)

    def crawl_delay(self):
        return self._cd

    def sitemaps(self):
        return list(self._sm)


class FakePolicy:
    def __init__(self, parsed):
        self._parsed = parsed

    def get(self, domain):
        return self._parsed


def _cand(url="https://shop.ua"):
    return SourceCandidate(name="Shop", type="website", url_or_handle=url)


def test_sitemap_path_filters_promo_homepage_first_and_caps(monkeypatch):
    monkeypatch.setattr(walker_mod, "collect_sitemap_urls",
                        lambda *a, **k: ["https://shop.ua/sale", "https://shop.ua/product/1",
                                         "https://shop.ua/promo", "https://shop.ua/blog"])
    policy = FakePolicy(FakeRobots(sitemaps=["https://shop.ua/sitemap.xml"]))
    w = DomainWalker(client=object(), robots=policy, rate_limiter=NoWait(),
                     domain_page_cap=2, bfs_trigger_min=1)
    plan = w.walk(_cand())
    assert isinstance(plan, WalkPlan)
    assert plan.domain == "shop.ua"
    assert plan.urls[0] == "https://shop.ua"          # homepage first
    assert plan.urls == ["https://shop.ua", "https://shop.ua/sale"]  # capped at 2, promo only


def test_disallowed_urls_are_dropped(monkeypatch):
    monkeypatch.setattr(walker_mod, "collect_sitemap_urls",
                        lambda *a, **k: ["https://shop.ua/sale", "https://shop.ua/promo"])
    policy = FakePolicy(FakeRobots(sitemaps=["https://shop.ua/s.xml"],
                                   disallow=("/promo",)))
    w = DomainWalker(client=object(), robots=policy, rate_limiter=NoWait(),
                     domain_page_cap=10, bfs_trigger_min=1)
    plan = w.walk(_cand())
    assert "https://shop.ua/promo" not in plan.urls
    assert "https://shop.ua/sale" in plan.urls


def test_disallowed_homepage_yields_no_urls(monkeypatch):
    monkeypatch.setattr(walker_mod, "collect_sitemap_urls", lambda *a, **k: [])
    policy = FakePolicy(FakeRobots(disallow=("shop.ua",)))
    w = DomainWalker(client=object(), robots=policy, rate_limiter=NoWait())
    plan = w.walk(_cand())
    assert plan.urls == []


def test_crawl_delay_is_clamped(monkeypatch):
    monkeypatch.setattr(walker_mod, "collect_sitemap_urls", lambda *a, **k: [])
    policy = FakePolicy(FakeRobots(crawl_delay=9999.0))
    w = DomainWalker(client=object(), robots=policy, rate_limiter=NoWait(),
                     domain_min_delay=3.0, crawl_delay_cap=30.0)
    plan = w.walk(_cand())
    assert plan.crawl_delay == 30.0


def test_bfs_fallback_when_sitemap_thin(monkeypatch):
    monkeypatch.setattr(walker_mod, "collect_sitemap_urls", lambda *a, **k: [])

    # BFS fetches homepage HTML and follows same-domain promo links
    class HtmlResp:
        text = ('<a href="/sale">s</a><a href="https://other.ua/promo">x</a>'
                '<a href="/product/1">p</a>')
        content = None
        status_code = 200

        def raise_for_status(self):
            pass

    class HtmlClient:
        def get(self, url, **kw):
            return HtmlResp()

    policy = FakePolicy(FakeRobots())
    w = DomainWalker(client=HtmlClient(), robots=policy, rate_limiter=NoWait(),
                     bfs_trigger_min=3, bfs_max_pages=3, domain_page_cap=10)
    plan = w.walk(_cand())
    assert "https://shop.ua/sale" in plan.urls          # in-domain promo link found by BFS
    assert all("other.ua" not in u for u in plan.urls)   # off-domain dropped


def test_walk_never_raises(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("kaboom")
    monkeypatch.setattr(walker_mod, "collect_sitemap_urls", boom)
    policy = FakePolicy(FakeRobots(sitemaps=["https://shop.ua/s.xml"]))
    w = DomainWalker(client=object(), robots=policy, rate_limiter=NoWait(),
                     bfs_trigger_min=99)
    plan = w.walk(_cand())
    assert plan.urls == ["https://shop.ua"]              # fallback to homepage
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_walker.py -q`
Expected: FAIL — `ImportError: cannot import name 'DomainWalker'`.

- [ ] **Step 3: Write minimal implementation**

Append to `crawler/discovery/walker.py` (below `url_is_promo`):

```python
import logging
from dataclasses import dataclass

from selectolax.parser import HTMLParser

from crawler.discovery.passive import normalize_ref
from crawler.discovery.sitemap import collect_sitemap_urls

log = logging.getLogger(__name__)


def _host(url: str) -> str:
    netloc = urlsplit(url or "").netloc.lower()
    netloc = netloc.split("@")[-1].split(":")[0]
    return netloc[4:] if netloc.startswith("www.") else netloc


def _same_domain(url: str, domain: str) -> bool:
    h = _host(url)
    return h == domain or h.endswith("." + domain)


@dataclass
class WalkPlan:
    domain: str
    urls: list[str]
    crawl_delay: float | None


class DomainWalker:
    def __init__(self, client, robots, rate_limiter, *, domain_page_cap=10,
                 sitemap_max_docs=20, bfs_max_depth=2, bfs_max_pages=8,
                 bfs_trigger_min=3, domain_min_delay=3.0, crawl_delay_cap=30.0):
        self._client = client
        self._robots = robots
        self._rl = rate_limiter
        self._page_cap = domain_page_cap
        self._sitemap_max_docs = sitemap_max_docs
        self._bfs_max_depth = bfs_max_depth
        self._bfs_max_pages = bfs_max_pages
        self._bfs_trigger_min = bfs_trigger_min
        self._floor = domain_min_delay
        self._cap = crawl_delay_cap

    def walk(self, cand) -> WalkPlan:
        homepage = cand.url_or_handle
        domain = _host(homepage)
        try:
            robots = self._robots.get(domain)
            delay = min(max(self._floor, robots.crawl_delay() or 0.0), self._cap)
            sm_urls = robots.sitemaps() or [f"https://{domain}/sitemap.xml"]
            found = collect_sitemap_urls(sm_urls, self._client, self._rl, domain,
                                         delay, self._sitemap_max_docs)
            promo = [u for u in found if _same_domain(u, domain) and url_is_promo(u)]
            if len(promo) < self._bfs_trigger_min:
                promo += self._bfs(homepage, domain, robots, delay)
            urls = self._finalize(homepage, promo, robots)
            return WalkPlan(domain, urls, delay)
        except Exception as exc:  # noqa: BLE001 — expansion must never crash a pass
            log.warning("domain walk failed for %s: %s", homepage, exc)
            return WalkPlan(domain, [homepage], self._floor)

    def _finalize(self, homepage, promo, robots) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for url in [homepage, *promo]:
            if not robots.can_fetch(url):
                continue
            key = normalize_ref("website", url)
            if key in seen:
                continue
            seen.add(key)
            out.append(url)
            if len(out) >= self._page_cap:
                break
        return out

    def _bfs(self, homepage, domain, robots, delay) -> list[str]:
        found: list[str] = []
        seen: set[str] = set()
        frontier = [homepage]
        fetched = 0
        for _ in range(self._bfs_max_depth):
            nxt: list[str] = []
            for page in frontier:
                if fetched >= self._bfs_max_pages:
                    return found
                if not robots.can_fetch(page):
                    continue
                fetched += 1
                for link in self._links(page, domain, delay):
                    if link in seen:
                        continue
                    seen.add(link)
                    if url_is_promo(link):
                        found.append(link)
                    else:
                        nxt.append(link)
            frontier = nxt
        return found

    def _links(self, url, domain, delay) -> list[str]:
        try:
            self._rl.wait(domain, delay)
            resp = self._client.get(url, follow_redirects=True)
            resp.raise_for_status()
            tree = HTMLParser(resp.text)
        except Exception as exc:  # noqa: BLE001 — one page failing must not stop BFS
            log.warning("bfs link fetch failed for %s: %s", url, exc)
            return []
        out: list[str] = []
        for a in tree.css("a"):
            href = a.attributes.get("href")
            if not href:
                continue
            absolute = urljoin(url, href)
            if _same_domain(absolute, domain):
                out.append(absolute.split("#")[0])
        return out
```

Also update the top-of-file imports so `urljoin` is available — change the existing import
line to:

```python
from urllib.parse import unquote, urljoin, urlsplit
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_walker.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add crawler/discovery/walker.py crawler/tests/test_walker.py
git commit -m "feat(crawler): DomainWalker (robots+sitemap+BFS domain expansion)"
```

---

### Task 6: Harvester integration

**Files:**
- Modify: `crawler/discovery/harvest.py`
- Test: `crawler/tests/test_active_harvest.py` (append)

**Interfaces:**
- Consumes: `DomainWalker.walk` → `WalkPlan` (Task 5), `DomainRateLimiter` (Task 2).
- Produces: `ActiveHarvester(api, fetchers, extractor, rate_limiter, fetch_budget=20,
  walker=None, domain_rate_limiter=None)`. When `walker` is set and a candidate is
  `type == "website"`, its pages come from `walker.walk(cand).urls` and each page is fetched
  and processed **individually**; the telegram path and `walker=None` behave exactly as before.

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_active_harvest.py  (append; reuse existing fakes if present)
from crawler.discovery.harvest import ActiveHarvester
from crawler.discovery.walker import WalkPlan
from crawler.models import RawItem, SourceCandidate


class _Fetcher:
    """Records fetched URLs; returns one trivial passing item per page."""
    def __init__(self):
        self.urls = []

    def fetch(self, source, last_seen_key):
        self.urls.append(source["url_or_handle"])
        item = RawItem(source_id=None, platform="website", key="k",
                       text="Ми пропонуємо знижку 20% для ветеранів у нас",
                       url=source["url_or_handle"], links=[], site_name="Shop")
        return [item], None


class _Extractor:
    def extract(self, item, provider, cats):
        if provider == "":
            return object()   # passes the relevance gate
        from crawler.models import OfferCandidate
        return OfferCandidate(source_id=None, title="t", provider=provider, body="b")


class _Api:
    def __init__(self):
        self.offers = []

    def submit_offer(self, payload):
        self.offers.append(payload)

    def submit_suggestion(self, payload):
        pass


class _Walker:
    def __init__(self, urls):
        self._urls = urls

    def walk(self, cand):
        return WalkPlan(domain="shop.ua", urls=self._urls, crawl_delay=1.0)


class _DomainRL:
    def __init__(self):
        self.calls = []

    def wait(self, domain, delay=None):
        self.calls.append((domain, delay))


def _website_cand():
    return SourceCandidate(name="Shop", type="website", url_or_handle="https://shop.ua")


def test_walker_expands_website_candidate_to_multiple_pages(monkeypatch):
    import crawler.discovery.harvest as h
    monkeypatch.setattr(h, "resolve_offer_categories", lambda *a, **k: [])
    monkeypatch.setattr(h, "attribute",
                        lambda item, ctx: type("A", (), {
                            "provider": "shop.ua", "suggest_url_or_handle": None,
                            "suggest_type": "website", "suggest_name": "Shop"})())
    fetcher = _Fetcher()
    drl = _DomainRL()
    harv = ActiveHarvester(_Api(), {"website": fetcher}, _Extractor(), rate_limiter=None,
                           walker=_Walker(["https://shop.ua", "https://shop.ua/sale"]),
                           domain_rate_limiter=drl)
    summary = {"offers": 0, "suggestions": 0, "errors": 0}
    harv.harvest([_website_cand()], cats=object(), known=set(), summary=summary)
    assert fetcher.urls == ["https://shop.ua", "https://shop.ua/sale"]
    assert drl.calls == [("shop.ua", 1.0), ("shop.ua", 1.0)]


def test_walker_none_keeps_single_homepage_fetch(monkeypatch):
    import crawler.discovery.harvest as h
    monkeypatch.setattr(h, "resolve_offer_categories", lambda *a, **k: [])
    monkeypatch.setattr(h, "attribute",
                        lambda item, ctx: type("A", (), {
                            "provider": "shop.ua", "suggest_url_or_handle": None,
                            "suggest_type": "website", "suggest_name": "Shop"})())

    class PlatformRL:
        def __init__(self):
            self.calls = []

        def wait(self, platform):
            self.calls.append(platform)

    fetcher = _Fetcher()
    prl = PlatformRL()
    harv = ActiveHarvester(_Api(), {"website": fetcher}, _Extractor(), rate_limiter=prl)
    summary = {"offers": 0, "suggestions": 0, "errors": 0}
    harv.harvest([_website_cand()], cats=object(), known=set(), summary=summary)
    assert fetcher.urls == ["https://shop.ua"]     # single homepage fetch, unchanged
    assert prl.calls == ["website"]                 # per-platform wait, unchanged


def test_one_broken_page_does_not_stop_the_domain(monkeypatch):
    import crawler.discovery.harvest as h
    monkeypatch.setattr(h, "resolve_offer_categories", lambda *a, **k: [])
    monkeypatch.setattr(h, "attribute",
                        lambda item, ctx: type("A", (), {
                            "provider": "shop.ua", "suggest_url_or_handle": None,
                            "suggest_type": "website", "suggest_name": "Shop"})())

    class FlakyFetcher(_Fetcher):
        def fetch(self, source, last_seen_key):
            if source["url_or_handle"].endswith("/boom"):
                raise RuntimeError("dead page")
            return super().fetch(source, last_seen_key)

    fetcher = FlakyFetcher()
    harv = ActiveHarvester(_Api(), {"website": fetcher}, _Extractor(), rate_limiter=None,
                           walker=_Walker(["https://shop.ua/boom", "https://shop.ua/sale"]),
                           domain_rate_limiter=_DomainRL())
    summary = {"offers": 0, "suggestions": 0, "errors": 0}
    harv.harvest([_website_cand()], cats=object(), known=set(), summary=summary)
    assert summary["errors"] == 1
    assert "https://shop.ua/sale" in fetcher.urls    # continued after the broken page
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_active_harvest.py -q`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'walker'`.

- [ ] **Step 3: Write minimal implementation**

Rewrite `crawler/discovery/harvest.py` `ActiveHarvester` (keep `_as_source`, `_FETCHABLE`,
imports; add the walker/domain-rl fields and split `_harvest_one` into per-page processing):

```python
class ActiveHarvester:
    def __init__(self, api, fetchers, extractor, rate_limiter, fetch_budget=20,
                 walker=None, domain_rate_limiter=None):
        self._api = api
        self._fetchers = fetchers
        self._extractor = extractor
        self._rl = rate_limiter
        self._budget = fetch_budget
        self._walker = walker
        self._domain_rl = domain_rate_limiter

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

    def _plan(self, cand):
        """(urls, domain, delay) for a candidate. Website candidates expand via the walker."""
        if self._walker is not None and cand.type == "website":
            plan = self._walker.walk(cand)
            return plan.urls, plan.domain, plan.crawl_delay
        return [cand.url_or_handle], None, None

    def _wait(self, cand_type, domain, delay) -> None:
        if domain is not None and self._domain_rl is not None:
            self._domain_rl.wait(domain, delay)
        elif self._rl is not None:
            self._rl.wait(cand_type)

    def _harvest_one(self, cand, fetcher, cats, known, summary) -> None:
        urls, domain, delay = self._plan(cand)
        for url in urls:
            self._wait(cand.type, domain, delay)
            src = {"id": None, "type": cand.type, "url_or_handle": url, "name": cand.name}
            try:
                items, _ = fetcher.fetch(src, None)
                self._process_page(cand, items, cats, known, summary)
            except Exception as exc:  # noqa: BLE001 — one page must not sink the domain
                summary["errors"] += 1
                log.warning("harvest page failed for %s: %s", url, exc)

    def _process_page(self, cand, items, cats, known, summary) -> None:
        passing = [it for it in items
                   if self._extractor.extract(it, "", cats) is not None]
        ctx = build_page_ctx(cand, passing)
        for item in passing:
            attr = attribute(item, ctx)
            if attr is None:
                continue
            offer = self._extractor.extract(item, attr.provider, cats)
            offer.offer_category_ids = resolve_offer_categories(
                self._api, cats, offer.offer_category_matches)
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

Note: the old inline `self._rl.wait(cand.type)` in `_harvest_one` is removed — waiting now
happens per page in `_wait`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_active_harvest.py -q`
Expected: PASS (existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add crawler/discovery/harvest.py crawler/tests/test_active_harvest.py
git commit -m "feat(crawler): wire DomainWalker into ActiveHarvester (per-page harvest)"
```

---

### Task 7: Config knobs

**Files:**
- Modify: `crawler/config.py` (`_RawSettings` + `Config` + `load_config`)
- Test: `crawler/tests/test_config.py` (append)

**Interfaces:**
- Produces on `Config`: `sitemap_depth_enabled: bool`, `domain_page_cap: int`,
  `sitemap_max_docs: int`, `bfs_max_depth: int`, `bfs_max_pages: int`, `bfs_trigger_min: int`,
  `domain_min_delay_seconds: float`, `crawl_delay_cap_seconds: float`,
  `robots_cache_path: str`, `robots_cache_ttl_hours: int`.

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_config.py  (append)
def test_sitemap_depth_defaults(monkeypatch):
    monkeypatch.setattr("crawler.config._RawSettings.model_config",
                        {"env_file": None, "extra": "ignore"}, raising=False)
    from crawler.config import load_config
    cfg = load_config()
    assert cfg.sitemap_depth_enabled is True
    assert cfg.domain_page_cap == 10
    assert cfg.sitemap_max_docs == 20
    assert cfg.bfs_max_depth == 2
    assert cfg.bfs_max_pages == 8
    assert cfg.bfs_trigger_min == 3
    assert cfg.domain_min_delay_seconds == 3.0
    assert cfg.crawl_delay_cap_seconds == 30.0
    assert cfg.robots_cache_path == "/data/robots_cache.json"
    assert cfg.robots_cache_ttl_hours == 168
```

(If `test_config.py` already asserts defaults via a helper, follow that file's existing
pattern instead of the monkeypatch above — match the surrounding style.)

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_config.py -q`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'sitemap_depth_enabled'`.

- [ ] **Step 3: Write minimal implementation**

Add to `_RawSettings` (after `brand_feed_per_pass`):

```python
    sitemap_depth_enabled: bool = True
    domain_page_cap: int = 10
    sitemap_max_docs: int = 20
    bfs_max_depth: int = 2
    bfs_max_pages: int = 8
    bfs_trigger_min: int = 3
    domain_min_delay_seconds: float = 3.0
    crawl_delay_cap_seconds: float = 30.0
    robots_cache_path: str = "/data/robots_cache.json"
    robots_cache_ttl_hours: int = 168
```

Add the same 10 fields with identical defaults to the `Config` dataclass (after
`brand_feed_per_pass: int = 20`), and pass them through in `load_config`'s `Config(...)` call:

```python
        sitemap_depth_enabled=s.sitemap_depth_enabled,
        domain_page_cap=s.domain_page_cap,
        sitemap_max_docs=s.sitemap_max_docs,
        bfs_max_depth=s.bfs_max_depth,
        bfs_max_pages=s.bfs_max_pages,
        bfs_trigger_min=s.bfs_trigger_min,
        domain_min_delay_seconds=s.domain_min_delay_seconds,
        crawl_delay_cap_seconds=s.crawl_delay_cap_seconds,
        robots_cache_path=s.robots_cache_path,
        robots_cache_ttl_hours=s.robots_cache_ttl_hours,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_config.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/config.py crawler/tests/test_config.py
git commit -m "feat(crawler): sitemap-depth config knobs"
```

---

### Task 8: Wiring

**Files:**
- Modify: `crawler/wiring.py`
- Test: `crawler/tests/test_wiring.py` (append)

**Interfaces:**
- Consumes: `RobotsPolicy` (Task 3), `DomainRateLimiter` (Task 2), `DomainWalker` (Task 5),
  config knobs (Task 7), `ActiveHarvester(..., walker=, domain_rate_limiter=)` (Task 6).
- Produces: `build_runner` builds a `DomainWalker` + `DomainRateLimiter` and passes them into
  `ActiveHarvester` when `config.sitemap_depth_enabled` is true; otherwise the harvester's
  `walker`/`domain_rate_limiter` stay `None`.

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_wiring.py  (append)
# NOTE: mirror the existing test_build_runner_brand_feed_runs_without_ddg pattern —
# pre-write a FRESH brand cache to tmp so build_runner does NOT refresh (no network),
# and enable brand_feed so a harvester (and thus the walker) is actually built.
from crawler.discovery.walker import DomainWalker


def _harvest_config(tmp_path, **over):
    bpath = tmp_path / "brand_domains.json"
    bpath.write_text(json.dumps({"version": 1, "refreshed_at": 9_999_999_999.0,
                                 "domains": {"OKKO": "okko.ua"}}), encoding="utf-8")
    base = dict(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        active_discovery=False, request_timeout=5.0, min_delay_seconds=0.0,
        bot_accounts=[], proxies={},
        brand_feed_enabled=True, brand_domains_path=str(bpath),
        brand_feed_refresh_hours=336, active_fetch_budget=20,
        robots_cache_path=str(tmp_path / "robots.json"),
    )
    base.update(over)
    return Config(**base)


def test_walker_built_when_sitemap_depth_enabled(tmp_path):
    runner = build_runner(_harvest_config(tmp_path, sitemap_depth_enabled=True))
    assert isinstance(runner._harvester._walker, DomainWalker)
    assert runner._harvester._domain_rl is not None


def test_no_walker_when_sitemap_depth_disabled(tmp_path):
    runner = build_runner(_harvest_config(tmp_path, sitemap_depth_enabled=False))
    assert runner._harvester._walker is None
```

(`json` and `Config` are already imported at the top of `test_wiring.py`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_wiring.py -q`
Expected: FAIL — `AttributeError` on `_walker` / walker is `None` when enabled.

- [ ] **Step 3: Write minimal implementation**

In `crawler/wiring.py`, add imports:

```python
from crawler.discovery.robots import RobotsPolicy
from crawler.discovery.walker import DomainWalker
from crawler.ratelimit import RateLimiter, DomainRateLimiter
```

Add a builder helper:

```python
def _build_walker(config, web_client):
    domain_rl = DomainRateLimiter(config.domain_min_delay_seconds)
    robots = RobotsPolicy(web_client, domain_rl, config.robots_cache_path,
                          config.robots_cache_ttl_hours * 3600)
    walker = DomainWalker(
        web_client, robots, domain_rl,
        domain_page_cap=config.domain_page_cap,
        sitemap_max_docs=config.sitemap_max_docs,
        bfs_max_depth=config.bfs_max_depth,
        bfs_max_pages=config.bfs_max_pages,
        bfs_trigger_min=config.bfs_trigger_min,
        domain_min_delay=config.domain_min_delay_seconds,
        crawl_delay_cap=config.crawl_delay_cap_seconds)
    return walker, domain_rl
```

In `build_runner`, after `harvester`/`brand_feed` are decided, build the walker and pass it
into the `ActiveHarvester(...)` construction:

```python
    walker = None
    domain_rl = None
    if config.sitemap_depth_enabled:
        walker, domain_rl = _build_walker(config, web_client)
    if (discovery is not None or brand_feed is not None) and config.active_fetch_budget:
        harvester = ActiveHarvester(api, fetchers, extractor, rate_limiter,
                                    fetch_budget=config.active_fetch_budget,
                                    walker=walker, domain_rate_limiter=domain_rl)
```

(Replace the existing `ActiveHarvester(...)` call with the version above.)

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_wiring.py -q`
Expected: PASS.

- [ ] **Step 5: Full suite + commit**

```bash
./.venv/Scripts/python.exe -m pytest -q
```
Expected: all green (228 prior + new tests).

```bash
git add crawler/wiring.py crawler/tests/test_wiring.py
git commit -m "feat(crawler): wire sitemap-depth walker into build_runner"
```

---

## Self-Review

**Spec coverage:** robots-cache → Task 3; sitemap (index/gzip/cap) → Task 4; promo URL filter →
Task 1; BFS≤2 fallback + caps + Disallow + crawl-delay clamp → Task 5; per-page attribution +
per-page error isolation + telegram/`walker=None` unchanged → Task 6; per-domain rate limit →
Task 2; config knobs → Task 7; wiring + enabled/disabled → Task 8. Homepage-first + dedup +
`domain_page_cap` → Task 5 `_finalize`. All spec sections mapped.

**Placeholder scan:** no TBD/TODO; every code step shows full code; test bodies are concrete.
Two tasks (7, 8) note "match the existing file's style" for `Config` construction — this is a
real adaptation instruction, not a placeholder (the assertion targets are fully specified).

**Type consistency:** `WalkPlan(domain, urls, crawl_delay)` used identically in Tasks 5, 6, 8;
`DomainWalker(...)` keyword names match between Task 5 definition and Task 8 construction;
`ActiveHarvester(..., walker=, domain_rate_limiter=)` matches between Tasks 6 and 8;
`RobotsPolicy(client, rate_limiter, path, ttl_seconds, clock=)` matches Tasks 3 and 8;
`DomainRateLimiter.wait(domain, delay=None)` matches Tasks 2, 4, 5, 6, 8;
`collect_sitemap_urls(sitemap_urls, client, rate_limiter, domain, crawl_delay, max_docs)`
matches Tasks 4 and 5; `url_is_promo` matches Tasks 1 and 5.
