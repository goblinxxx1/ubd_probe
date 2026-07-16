# Search Result Type Classification Implementation Plan — Track D

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Classify search-discovery results by platform type (t.me→telegram, instagram/facebook profiles→their type, else website) and drop social junk, so search-found sources reach the correct fetcher instead of all being `website`.

**Architecture:** A `classify_candidate(url)` helper in `providers.py` returns `(type, url_or_handle)` or `None`; both `DuckDuckGoProvider` and `SearxngProvider` use it in place of hardcoding `type="website"`.

**Tech Stack:** Python, existing crawler discovery stack (`urllib.parse`, `_normalize_url`).

## Global Constraints

- Crawler-only: `providers.py` + its tests. Backend/admin/public untouched (they already accept every source type).
- `classify_candidate(url) -> tuple[str, str] | None`: `(type, url_or_handle)` or `None` (invalid or reserved junk).
- Host types: `t.me`/`telegram.me`→telegram; `instagram.com`→instagram; `facebook.com`/`fb.com`→facebook; else website. Strip a leading `www.`.
- Reserved (→ `None`): IG `/p/ /reel/ /reels/ /explore/ /stories/` + bare root; FB `/share /sharer /events /photo /watch` + bare root.
- `url_or_handle` = normalised full URL (fetchers extract the handle via their own `_handle_of`).
- No new config flag — always on for search providers.
- Crawler tests run from `crawler/` via `./.venv/Scripts/python.exe -m pytest`.

---

### Task D-1: `classify_candidate` helper (TDD)

**Files:**
- Modify: `crawler/crawler/discovery/providers.py` (add `classify_candidate`)
- Create: `crawler/tests/test_classify_candidate.py`

**Interfaces:**
- Consumes: `_normalize_url` (already in `providers.py`).
- Produces: `classify_candidate(url: str) -> tuple[str, str] | None`.

- [ ] **Step 1: Write the failing test** — `crawler/tests/test_classify_candidate.py`

```python
import pytest

from crawler.discovery.providers import classify_candidate


@pytest.mark.parametrize("url, expected_type", [
    ("https://t.me/veteranychat", "telegram"),
    ("https://t.me/s/veteranychat", "telegram"),
    ("https://www.instagram.com/some_profile", "instagram"),
    ("https://facebook.com/somebiz", "facebook"),
    ("https://fb.com/somebiz", "facebook"),
    ("https://shop.example.com/deal", "website"),
])
def test_classifies_type_from_host(url, expected_type):
    result = classify_candidate(url)
    assert result is not None
    assert result[0] == expected_type


@pytest.mark.parametrize("url", [
    "https://instagram.com/p/AbC123",
    "https://instagram.com/reel/xyz",
    "https://instagram.com/explore/tags/x",
    "https://instagram.com/",
    "https://facebook.com/share/abc",
    "https://facebook.com/sharer/x",
    "https://facebook.com/",
    "not-a-url",
    "",
])
def test_reserved_or_invalid_returns_none(url):
    assert classify_candidate(url) is None


def test_returns_normalised_url_as_handle_field():
    t, uoh = classify_candidate("HTTPS://T.me/Chan?utm_source=x")
    assert t == "telegram"
    assert uoh == "https://t.me/chan"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_classify_candidate.py -q
```
Expected: FAIL — `classify_candidate` does not exist.

- [ ] **Step 3: Implement `classify_candidate` in `crawler/crawler/discovery/providers.py`**

Add near `_normalize_url` (it uses `urlsplit`, already imported):

```python
_IG_RESERVED = ("/p/", "/reel/", "/reels/", "/explore/", "/stories/")
_FB_RESERVED = ("/share", "/sharer", "/events", "/photo", "/watch")


def classify_candidate(url: str) -> tuple[str, str] | None:
    """Map a search-result URL to (source_type, url_or_handle), or None to skip."""
    norm = _normalize_url(url)
    if not norm:
        return None
    host = urlsplit(norm).netloc.lower().removeprefix("www.")
    path = urlsplit(norm).path or "/"
    if host in ("t.me", "telegram.me"):
        return ("telegram", norm)
    if host == "instagram.com":
        if path == "/" or any(path.startswith(p) for p in _IG_RESERVED):
            return None
        return ("instagram", norm)
    if host in ("facebook.com", "fb.com"):
        if path == "/" or any(path.startswith(p) for p in _FB_RESERVED):
            return None
        return ("facebook", norm)
    return ("website", norm)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_classify_candidate.py -q
```
Expected: all parametrised cases pass.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/providers.py crawler/tests/test_classify_candidate.py
git commit -m "feat(crawler): classify_candidate maps search URLs to source types"
```

---

### Task D-2: Providers use the classifier (TDD)

**Files:**
- Modify: `crawler/crawler/discovery/providers.py` (`DuckDuckGoProvider.__call__`, `SearxngProvider.__call__`)
- Create: `crawler/tests/test_provider_typeclass.py`

**Interfaces:**
- Consumes: `classify_candidate` from Task D-1.
- Produces: providers emit `SourceCandidate`s with classifier-derived `type`; reserved/invalid results are skipped.

- [ ] **Step 1: Write the failing test** — `crawler/tests/test_provider_typeclass.py`

```python
import httpx

from crawler.discovery.providers import DuckDuckGoProvider, SearxngProvider


class FakeDDGS:
    def __init__(self, results): self._results = results
    def text(self, query, max_results=7): return self._results


def test_ddg_provider_classifies_and_skips_junk():
    results = [
        {"title": "Site", "href": "https://shop.example/deal", "body": "b"},
        {"title": "TG", "href": "https://t.me/veteranychat", "body": "b"},
        {"title": "IG post", "href": "https://instagram.com/p/AbC", "body": "b"},
        {"title": "IG prof", "href": "https://instagram.com/veteranshop", "body": "b"},
    ]
    p = DuckDuckGoProvider(results_per_keyword=10, min_delay=0,
                           ddgs_factory=lambda: FakeDDGS(results), sleep=lambda _s: None)
    cands = p("kw")
    got = {(c.type, c.url_or_handle) for c in cands}
    assert ("website", "https://shop.example/deal") in got
    assert ("telegram", "https://t.me/veteranychat") in got
    assert ("instagram", "https://instagram.com/veteranshop") in got
    assert all("instagram.com/p/" not in c.url_or_handle for c in cands)  # junk dropped
    assert len(cands) == 3


def _searx_factory(handler):
    return lambda: httpx.Client(transport=httpx.MockTransport(handler))


def test_searxng_provider_classifies_and_skips_junk():
    def handler(req):
        return httpx.Response(200, json={"results": [
            {"url": "https://shop.example/deal", "title": "Site"},
            {"url": "https://t.me/vetchan", "title": "TG"},
            {"url": "https://facebook.com/share/x", "title": "FB share"},
        ]})
    p = SearxngProvider("http://searxng:8080", results_per_keyword=10, min_delay=0,
                        client_factory=_searx_factory(handler), sleep=lambda _s: None)
    cands = p("kw")
    got = {(c.type, c.url_or_handle) for c in cands}
    assert ("website", "https://shop.example/deal") in got
    assert ("telegram", "https://t.me/vetchan") in got
    assert all("facebook.com/share" not in c.url_or_handle for c in cands)  # junk dropped
    assert len(cands) == 2
```

- [ ] **Step 2: Run test to verify it fails**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_provider_typeclass.py -q
```
Expected: FAIL — providers still hardcode `type="website"` and don't skip junk.

- [ ] **Step 3: Update `DuckDuckGoProvider.__call__`** in `providers.py`

Replace its result loop body:
```python
        out: list[SourceCandidate] = []
        for r in results or []:
            url = _normalize_url(r.get("href", ""))
            if not url:
                continue
            out.append(SourceCandidate(
                name=r.get("title") or url, type="website", url_or_handle=url,
                discovered_from_source_id=None, discovery_note=f"ddg: {keyword}"))
        return out
```
with:
```python
        out: list[SourceCandidate] = []
        for r in results or []:
            classified = classify_candidate(r.get("href", ""))
            if classified is None:
                continue
            type_, url_or_handle = classified
            out.append(SourceCandidate(
                name=r.get("title") or url_or_handle, type=type_, url_or_handle=url_or_handle,
                discovered_from_source_id=None, discovery_note=f"ddg: {keyword}"))
        return out
```

- [ ] **Step 4: Update `SearxngProvider.__call__`** in `providers.py`

Replace its result loop body:
```python
        out: list[SourceCandidate] = []
        for r in (data.get("results") or [])[:self._n]:
            url = _normalize_url(r.get("url", ""))
            if not url:
                continue
            out.append(SourceCandidate(
                name=r.get("title") or url, type="website", url_or_handle=url,
                discovered_from_source_id=None, discovery_note=f"searxng: {keyword}"))
        return out
```
with:
```python
        out: list[SourceCandidate] = []
        for r in (data.get("results") or [])[:self._n]:
            classified = classify_candidate(r.get("url", ""))
            if classified is None:
                continue
            type_, url_or_handle = classified
            out.append(SourceCandidate(
                name=r.get("title") or url_or_handle, type=type_, url_or_handle=url_or_handle,
                discovered_from_source_id=None, discovery_note=f"searxng: {keyword}"))
        return out
```

- [ ] **Step 5: Run tests (new + full crawler suite)**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_provider_typeclass.py -q
./.venv/Scripts/python.exe -m pytest -q
```
Expected: new file passes; full crawler suite green. (Existing `test_providers.py` /
`test_searxng_provider.py` cases used only website URLs, so they still pass — a
website URL still classifies as `website`.)

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/discovery/providers.py crawler/tests/test_provider_typeclass.py
git commit -m "feat(crawler): providers classify search results by source type"
```

---

## Self-Review

**Spec coverage:**
- `classify_candidate(url) -> (type, url_or_handle) | None` → Task D-1. ✅
- Host types + reserved-path filtering → Task D-1 (`_IG_RESERVED`/`_FB_RESERVED`). ✅
- Both providers use it, skip `None` → Task D-2. ✅
- `url_or_handle` = normalised URL → Task D-1 (returns `norm`). ✅
- No config flag; crawler-only → Global Constraints (nothing else touched). ✅
- Non-goals (backend/admin/public, passive.py) → untouched. ✅

**Placeholder scan:** No TBD/TODO; every step has full code and exact commands. ✅

**Type consistency:** `classify_candidate(url) -> tuple[str, str] | None` defined in
D-1 and consumed identically in both providers (D-2). `_normalize_url` (existing)
reused. `SourceCandidate(name/type/url_or_handle/discovered_from_source_id/discovery_note)`
matches the existing model. Provider constructor signatures
(`DuckDuckGoProvider(results_per_keyword, min_delay, ddgs_factory, sleep)`,
`SearxngProvider(base_url, results_per_keyword, min_delay, client_factory, sleep)`)
match Tracks A/B and the tests. ✅
