# Crawler Early Language Gate (A+B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Abandon a foreign-language domain before its sitemap is enumerated, and persistently block the host so it never re-walks — closing the justcolor.net budget leak.

**Architecture:** A new `LanguageGate` judges a domain from its homepage alone (content Cyrillic ratio + hreflang), called inside `DomainWalker.walk()` before `collect_sitemap_urls` (**A**). When it — or the existing content gate in `_harvest_one` (**B**) — trips, the host is pinned into a new local `LangBlockStore` (mirror of `GeoBlockStore`) which pushes into `blocklist`, so `is_blocked_host` drops it everywhere, this run and next.

**Tech Stack:** Python 3, pytest, selectolax (HTML parsing), httpx (fetch). No backend/DB change.

## Global Constraints

- Ukrainian-only project: never add Russian text to lexicons/regexes/seeds.
- Conservative gating: never block on uncertainty (fetch error, thin content) — a false block silently drops a real UA business.
- The decisive signal is the **content Cyrillic ratio** (`is_non_ukrainian`); `<html lang>` is never load-bearing (sites lie). hreflang only **vetoes** a block when a `uk`/`ua` alternate exists.
- Persistent block target is the **local** `LangBlockStore` (`/data/lang_blocked_hosts.json`), **not** the backend `blocked_hosts` table.
- Follow existing patterns: `LangBlockStore` mirrors `crawler/discovery/geo_block.py`; the block-on-detect wiring mirrors the RU/BY handling at `crawler/discovery/harvest.py:58-61`.
- Thresholds reuse `is_non_ukrainian` defaults: `min_ratio=0.3`, `min_alpha=15`.
- Run tests from `crawler/` with the project venv. `is_non_ukrainian` lives in `crawler/util/text_lang.py`; `bare_host` in `crawler/util/hosts.py`; `_host` is re-exported into `harvest.py` from `crawler.discovery.brand_feed`.

---

## File Structure

- Create `crawler/crawler/discovery/lang_block.py` — local persistent store of language-blocked hosts (mirror of `geo_block.py`).
- Create `crawler/crawler/discovery/language_gate.py` — homepage-only foreign-language judgment.
- Modify `crawler/crawler/discovery/blocklist.py` — new `_LANG_BLOCKED` slot + `reload_lang_blocked`, included in `is_blocked_host`.
- Modify `crawler/crawler/discovery/walker.py` — `WalkPlan.foreign` field; `DomainWalker` accepts `language_gate`; `walk()` early-returns a foreign plan.
- Modify `crawler/crawler/discovery/harvest.py` — `ActiveHarvester` accepts `lang_block_store`; `_plan` surfaces `foreign`; `_harvest_one` pins the host on A and B.
- Modify `crawler/crawler/config.py` — `lang_gate_enabled`, `lang_blocked_hosts_path` (Settings + Config + mapping).
- Modify `crawler/crawler/wiring.py` — build `LangBlockStore` + `LanguageGate`, inject them.
- Tests: `test_lang_block.py`, `test_language_gate.py` (new); additions to `test_walker.py`, `test_active_harvest.py`.

---

## Task 1: LangBlockStore + blocklist slot

**Files:**
- Create: `crawler/crawler/discovery/lang_block.py`
- Modify: `crawler/crawler/discovery/blocklist.py:41` (add slot), `:64-71` (add reloader), `:74-86` (include in check)
- Test: `crawler/tests/test_lang_block.py`

**Interfaces:**
- Produces: `LangBlockStore(path).load() -> LangBlockStore`; `.add(host_or_url) -> bool`; `.hosts() -> frozenset[str]`. `blocklist.reload_lang_blocked(hosts)`; `blocklist.is_blocked_host(host)` now also True for lang-blocked hosts.

- [ ] **Step 1: Write the failing test** — `crawler/tests/test_lang_block.py`

```python
import json

from crawler.discovery.blocklist import is_blocked_host, reload_lang_blocked
from crawler.discovery.lang_block import LangBlockStore


def teardown_function():
    reload_lang_blocked(None)   # keep module-global blocklist clean between tests


def test_reload_lang_blocked_makes_host_blocked():
    reload_lang_blocked({"justcolor.net"})
    assert is_blocked_host("justcolor.net") is True
    assert is_blocked_host("https://www.justcolor.net/enfants") is True
    assert is_blocked_host("sub.justcolor.net") is True     # suffix match
    assert is_blocked_host("shop.ua") is False


def test_reload_lang_blocked_empty_clears():
    reload_lang_blocked({"justcolor.net"})
    reload_lang_blocked(None)
    assert is_blocked_host("justcolor.net") is False


def test_store_add_persists_and_blocks(tmp_path):
    path = tmp_path / "lang_blocked_hosts.json"
    store = LangBlockStore(str(path)).load()
    assert store.add("https://www.justcolor.net/enfants") is True   # url -> bare host
    assert "justcolor.net" in store.hosts()
    assert is_blocked_host("justcolor.net") is True                 # live-blocked after add
    assert json.loads(path.read_text(encoding="utf-8")) == ["justcolor.net"]


def test_store_add_duplicate_is_noop(tmp_path):
    store = LangBlockStore(str(tmp_path / "l.json")).load()
    assert store.add("justcolor.net") is True
    assert store.add("https://justcolor.net/other") is False        # same bare host


def test_store_load_existing_file_blocks(tmp_path):
    path = tmp_path / "l.json"
    path.write_text(json.dumps(["justcolor.net", "example.com"]), encoding="utf-8")
    LangBlockStore(str(path)).load()
    assert is_blocked_host("justcolor.net") is True
    assert is_blocked_host("example.com") is True


def test_store_missing_file_is_empty(tmp_path):
    store = LangBlockStore(str(tmp_path / "nope.json")).load()
    assert store.hosts() == frozenset()
    assert is_blocked_host("justcolor.net") is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_lang_block.py -q` (from `crawler/`)
Expected: FAIL — `ModuleNotFoundError: crawler.discovery.lang_block` / `cannot import reload_lang_blocked`.

- [ ] **Step 3: Add the blocklist slot** — edit `crawler/crawler/discovery/blocklist.py`

After the `_GEO_BLOCKED` definition (around line 41) add:

```python
# Hosts pinned as non-Ukrainian by the language gate (homepage content + hreflang) —
# persisted crawler-side (LangBlockStore) and pushed here so the WHOLE host is never
# fetched/walked/re-fed again. Separate slot from _GEO_BLOCKED and _LEARNED.
_LANG_BLOCKED: frozenset[str] = frozenset()


def reload_lang_blocked(hosts) -> None:
    """Replace the language-blocked host set. None/empty ⇒ cleared."""
    global _LANG_BLOCKED
    if not hosts:
        _LANG_BLOCKED = frozenset()
        return
    norm = {bare_host(h) for h in hosts if h and h.strip()}
    _LANG_BLOCKED = frozenset(n for n in norm if n)
```

Then in `is_blocked_host`, add a check alongside the geo one (before the final `_LEARNED` return):

```python
    if any(host == d or host.endswith("." + d) for d in _GEO_BLOCKED):
        return True
    if any(host == d or host.endswith("." + d) for d in _LANG_BLOCKED):
        return True
    return any(host == d or host.endswith("." + d) for d in _LEARNED)
```

- [ ] **Step 4: Create `crawler/crawler/discovery/lang_block.py`**

```python
"""Persistent language-block: hosts judged non-Ukrainian by the language gate
(homepage content + hreflang) get pinned so the WHOLE host is never crawled again.

Kept on the crawler /data volume (like geo_block/domain_registry) — self-contained,
no backend dependency. On load() and on every add() the set is pushed into
discovery.blocklist so is_blocked_host (used by harvest, walk, feeds, attribution)
respects it everywhere at once. Mirrors GeoBlockStore."""

import json
import logging
import os

from crawler.discovery import blocklist
from crawler.util.hosts import bare_host

log = logging.getLogger(__name__)


class LangBlockStore:
    def __init__(self, path: str):
        self._path = path
        self._hosts: set[str] = set()

    def load(self) -> "LangBlockStore":
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, ValueError, OSError):
            data = []
        self._hosts = {h for h in (bare_host(x) for x in data if x) if h}
        self._push()
        return self

    def hosts(self) -> frozenset[str]:
        return frozenset(self._hosts)

    def add(self, host_or_url: str | None) -> bool:
        """Pin a host (accepts a full URL). Returns True if newly added."""
        h = bare_host(host_or_url)
        if not h or h in self._hosts:
            return False
        self._hosts.add(h)
        self._save()
        self._push()
        return True

    def _push(self) -> None:
        blocklist.reload_lang_blocked(self._hosts)

    def _save(self) -> None:
        tmp = self._path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(sorted(self._hosts), f, ensure_ascii=False)
            os.replace(tmp, self._path)
        except OSError as e:
            log.warning("lang-block save failed: %s", e)
```

- [ ] **Step 5: Run to verify it passes**

Run: `python -m pytest tests/test_lang_block.py -q`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/discovery/lang_block.py crawler/crawler/discovery/blocklist.py crawler/tests/test_lang_block.py
git commit -m "feat(crawler): LangBlockStore + blocklist lang slot"
```

---

## Task 2: LanguageGate (homepage-only foreign judgment)

**Files:**
- Create: `crawler/crawler/discovery/language_gate.py`
- Test: `crawler/tests/test_language_gate.py`

**Interfaces:**
- Consumes: `is_non_ukrainian` from `crawler.util.text_lang`.
- Produces: `LanguageGate(client, rate_limiter, *, min_ratio=0.3, min_alpha=15)`; `.is_foreign(homepage: str, domain: str, delay: float | None) -> bool`. `client.get(url, follow_redirects=True)` returns an object with `.text` and `.raise_for_status()`. `rate_limiter.wait(domain, delay)` (may be `None`).

- [ ] **Step 1: Write the failing test** — `crawler/tests/test_language_gate.py`

```python
from crawler.discovery.language_gate import LanguageGate


class NoWait:
    def wait(self, *a, **k):
        pass


class _Resp:
    def __init__(self, html):
        self.text = html
    def raise_for_status(self):
        pass


class _Client:
    def __init__(self, html):
        self._html = html
        self.gets = []
    def get(self, url, **kw):
        self.gets.append(url)
        return _Resp(self._html)


class _BoomClient:
    def get(self, url, **kw):
        raise RuntimeError("network down")


def _gate(html, client=None):
    return LanguageGate(client or _Client(html), NoWait())


EN_HTML = ('<html lang="en-US"><head>'
           '<link rel="alternate" hreflang="en" href="https://x/">'
           '<link rel="alternate" hreflang="fr" href="https://x/fr">'
           '</head><body>Free coloring pages for kids and adults to print and '
           'download in many themes animals nature mandalas</body></html>')


def test_english_homepage_with_no_uk_hreflang_is_foreign():
    g = _gate(EN_HTML)
    assert g.is_foreign("https://www.justcolor.net/", "justcolor.net", 0.0) is True


def test_ukrainian_homepage_is_not_foreign():
    html = ('<html lang="uk"><body>Знижки для військових та ветеранів у нашій '
            'мережі магазинів по всій Україні кожного дня</body></html>')
    assert _gate(html).is_foreign("https://shop.ua/", "shop.ua", 0.0) is False


def test_non_cyrillic_but_has_uk_hreflang_is_not_foreign():
    # a real multilingual UA site: English landing but a Ukrainian version exists
    html = ('<html lang="en"><head>'
            '<link rel="alternate" hreflang="uk-UA" href="https://x/uk">'
            '</head><body>Discounts for the military across all our stores every day</body></html>')
    assert _gate(html).is_foreign("https://x.com/", "x.com", 0.0) is False


def test_thin_content_is_not_foreign():
    # under min_alpha=15 letters → never block on lack of content
    assert _gate("<html><body>Hi</body></html>").is_foreign("https://x/", "x", 0.0) is False


def test_fetch_error_is_not_foreign():
    g = LanguageGate(_BoomClient(), NoWait())
    assert g.is_foreign("https://x/", "x", 0.0) is False


def test_rate_limiter_is_called_with_domain_and_delay():
    class RecWait:
        def __init__(self): self.calls = []
        def wait(self, domain, delay=None): self.calls.append((domain, delay))
    rl = RecWait()
    LanguageGate(_Client(EN_HTML), rl).is_foreign("https://justcolor.net/", "justcolor.net", 2.0)
    assert rl.calls == [("justcolor.net", 2.0)]
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_language_gate.py -q`
Expected: FAIL — `ModuleNotFoundError: crawler.discovery.language_gate`.

- [ ] **Step 3: Create `crawler/crawler/discovery/language_gate.py`**

```python
"""Early domain-level language gate: judge a domain from its HOMEPAGE alone, so
DomainWalker can abandon a foreign-language site BEFORE enumerating its sitemap.
Complements the content gate (is_non_ukrainian) in _harvest_one, which only fires
after pages are fetched — by then the sitemap-walk budget is already spent.

Decisive signal is the homepage's Cyrillic ratio (is_non_ukrainian); hreflang only
vetoes the block when a Ukrainian (uk/ua) alternate exists. <html lang> is not used
as a verdict (sites misdeclare it). Any fetch/parse error or thin page → not foreign
(never block on uncertainty)."""

import logging

from selectolax.parser import HTMLParser

from crawler.util.text_lang import is_non_ukrainian

log = logging.getLogger(__name__)

_UA_HREFLANG = {"uk", "ua"}


def _hreflang_langs(tree) -> set[str]:
    langs: set[str] = set()
    for node in tree.css('link[rel="alternate"][hreflang]'):
        hl = (node.attributes.get("hreflang") or "").strip().lower()
        if hl:
            langs.add(hl.split("-", 1)[0])   # uk-UA -> uk
    return langs


class LanguageGate:
    def __init__(self, client, rate_limiter, *, min_ratio: float = 0.3,
                 min_alpha: int = 15):
        self._client = client
        self._rl = rate_limiter
        self._min_ratio = min_ratio
        self._min_alpha = min_alpha

    def is_foreign(self, homepage: str, domain: str, delay) -> bool:
        try:
            if self._rl is not None:
                self._rl.wait(domain, delay)
            resp = self._client.get(homepage, follow_redirects=True)
            resp.raise_for_status()
            tree = HTMLParser(resp.text)
        except Exception as exc:  # noqa: BLE001 — never block on uncertainty
            log.warning("language gate fetch failed for %s: %s", homepage, exc)
            return False
        if _UA_HREFLANG & _hreflang_langs(tree):
            return False                       # a Ukrainian version exists — keep
        body = tree.body
        text = body.text(separator=" ", strip=True) if body is not None else ""
        return is_non_ukrainian(text, min_ratio=self._min_ratio,
                                min_alpha=self._min_alpha)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_language_gate.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/language_gate.py crawler/tests/test_language_gate.py
git commit -m "feat(crawler): LanguageGate — homepage-only foreign-language judgment"
```

---

## Task 3: WalkPlan.foreign + walker integration (A)

**Files:**
- Modify: `crawler/crawler/discovery/walker.py:29-33` (WalkPlan), `:37-53` (ctor), `:55-74` (walk)
- Test: `crawler/tests/test_walker.py`

**Interfaces:**
- Consumes: `LanguageGate.is_foreign(homepage, domain, delay)` from Task 2.
- Produces: `WalkPlan.foreign: bool = False`; `DomainWalker(..., language_gate=None)`; when the gate reports foreign, `walk()` returns `WalkPlan(domain, [], delay, foreign=True)` **without** fetching the sitemap.

- [ ] **Step 1: Write the failing tests** — append to `crawler/tests/test_walker.py`

```python
class _ForeignGate:
    def __init__(self, foreign): self._foreign = foreign; self.calls = []
    def is_foreign(self, homepage, domain, delay):
        self.calls.append((homepage, domain)); return self._foreign


def test_foreign_root_abandons_domain_before_sitemap(monkeypatch):
    calls = {"sitemap": 0}
    def spy(*a, **k):
        calls["sitemap"] += 1
        return ["https://justcolor.net/akcii"]
    monkeypatch.setattr(walker_mod, "collect_sitemap_urls", spy)
    policy = FakePolicy(FakeRobots(sitemaps=["https://justcolor.net/s.xml"]))
    gate = _ForeignGate(True)
    w = DomainWalker(client=object(), robots=policy, rate_limiter=NoWait(),
                     domain_page_cap=10, bfs_trigger_min=1, language_gate=gate)
    plan = w.walk(_cand("https://justcolor.net"))
    assert plan.foreign is True
    assert plan.urls == []                  # nothing to fetch
    assert calls["sitemap"] == 0            # sitemap never enumerated
    assert gate.calls == [("https://justcolor.net", "justcolor.net")]


def test_non_foreign_root_walks_normally(monkeypatch):
    monkeypatch.setattr(walker_mod, "collect_sitemap_urls",
                        lambda *a, **k: ["https://shop.ua/akcii"])
    policy = FakePolicy(FakeRobots(sitemaps=["https://shop.ua/s.xml"]))
    w = DomainWalker(client=object(), robots=policy, rate_limiter=NoWait(),
                     domain_page_cap=10, bfs_trigger_min=1, language_gate=_ForeignGate(False))
    plan = w.walk(_cand("https://shop.ua"))
    assert plan.foreign is False
    assert "https://shop.ua/akcii" in plan.urls


def test_walkplan_foreign_defaults_false():
    assert WalkPlan("shop.ua", [], 0.0).foreign is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_walker.py -q`
Expected: FAIL — `WalkPlan.__init__` has no `foreign`; `DomainWalker` has no `language_gate`.

- [ ] **Step 3: Edit `WalkPlan`** — `crawler/crawler/discovery/walker.py`

```python
@dataclass
class WalkPlan:
    domain: str
    urls: list[str]
    crawl_delay: float | None
    foreign: bool = False
```

- [ ] **Step 4: Edit `DomainWalker.__init__`** — add the parameter (keyword-only tail, after `crawl_delay_cap`)

```python
    def __init__(self, client, robots, rate_limiter, *, domain_page_cap=10,
                 sitemap_max_docs=20, bfs_max_depth=2, bfs_max_pages=8,
                 bfs_trigger_min=3, domain_min_delay=3.0, crawl_delay_cap=30.0,
                 language_gate=None):
```

At the end of `__init__` body (after `self._collect_cap = ...`) add:

```python
        self._lang_gate = language_gate
```

- [ ] **Step 5: Edit `walk()`** — early foreign return before `collect_sitemap_urls`

Inside the `try:` block, right after `delay = min(...)` and before `sm_urls = ...`:

```python
            delay = min(max(self._floor, robots.crawl_delay() or 0.0), self._cap)
            if self._lang_gate is not None and self._lang_gate.is_foreign(
                    homepage, domain, delay):
                return WalkPlan(domain, [], delay, foreign=True)
            sm_urls = robots.sitemaps() or [f"https://{domain}/sitemap.xml"]
```

- [ ] **Step 6: Run to verify it passes**

Run: `python -m pytest tests/test_walker.py -q`
Expected: PASS (all existing + 3 new; existing tests construct `DomainWalker` without `language_gate` → gate skipped, unchanged).

- [ ] **Step 7: Commit**

```bash
git add crawler/crawler/discovery/walker.py crawler/tests/test_walker.py
git commit -m "feat(crawler): walker abandons foreign-language domain before sitemap (A)"
```

---

## Task 4: ActiveHarvester block wiring (A + B)

**Files:**
- Modify: `crawler/crawler/discovery/harvest.py:20-26` (ctor), `:111-119` (_plan), `:127-144` (_harvest_one)
- Test: `crawler/tests/test_active_harvest.py`

**Interfaces:**
- Consumes: `plan.foreign` (Task 3); `LangBlockStore.add(host_or_url) -> bool` (Task 1) via the injected `lang_block_store`.
- Produces: `ActiveHarvester(..., lang_block_store=None)`. On a foreign plan (A) or a tripped content gate (B), calls `lang_block_store.add(cand.url_or_handle)` and stops processing the domain.

- [ ] **Step 1: Write the failing tests** — append to `crawler/tests/test_active_harvest.py`

```python
class _LangStore:
    """Fake LangBlockStore recording pinned hosts."""
    def __init__(self): self.added = []
    def add(self, host_or_url):
        from crawler.util.hosts import bare_host
        self.added.append(bare_host(host_or_url)); return True


def test_foreign_plan_pins_host_and_skips_processing():
    from crawler.discovery.walker import WalkPlan

    class ForeignWalker:
        def walk(self, cand):
            return WalkPlan("justcolor.net", [], 0.0, foreign=True)

    fetcher = _Fetcher()
    store = _LangStore()
    h = ActiveHarvester(_Api(), {"website": fetcher}, _Extractor(), rate_limiter=None,
                        walker=ForeignWalker(), lang_block_store=store)
    h.harvest([SourceCandidate(name="JC", type="website",
                               url_or_handle="https://www.justcolor.net")],
              cats=object(), known=set(), summary=_summary())
    assert fetcher.urls == []                     # no page fetched
    assert store.added == ["justcolor.net"]       # whole host pinned (A)


def test_content_gate_pins_host_during_walk():
    from crawler.discovery.walker import WalkPlan
    en_url = "https://blog.rottenwifi.com/"

    class W:
        def walk(self, cand):
            return WalkPlan("blog.rottenwifi.com", [en_url], 0.0)

    fetcher = FakeFetcher([_item("Rotten Wifi speed test blog about internet plans reviews")])
    store = _LangStore()
    h = ActiveHarvester(FakeApi(), {"website": fetcher}, GateExtractor(),
                        rate_limiter=None, fetch_budget=5, walker=W(), lang_block_store=store)
    h.harvest([_cand(url=en_url)], cats=None, known=set(), summary=_summary())
    assert store.added == ["blog.rottenwifi.com"]  # pinned by content gate (B)


def test_no_lang_store_is_byte_equivalent():
    # foreign plan without a store must not crash and must still skip processing
    from crawler.discovery.walker import WalkPlan

    class ForeignWalker:
        def walk(self, cand):
            return WalkPlan("justcolor.net", [], 0.0, foreign=True)

    fetcher = _Fetcher()
    h = ActiveHarvester(_Api(), {"website": fetcher}, _Extractor(), rate_limiter=None,
                        walker=ForeignWalker())      # no lang_block_store
    h.harvest([SourceCandidate(name="JC", type="website",
                               url_or_handle="https://justcolor.net")],
              cats=object(), known=set(), summary=_summary())
    assert fetcher.urls == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_active_harvest.py -q`
Expected: FAIL — `ActiveHarvester` has no `lang_block_store`; `_plan` returns a 3-tuple (unpack error) once `_harvest_one` is updated. (Before edits, the `foreign`/store assertions fail.)

- [ ] **Step 3: Edit `ActiveHarvester.__init__`** — add the parameter at the tail

```python
    def __init__(self, api, fetchers, extractor, rate_limiter, fetch_budget=20,
                 walker=None, domain_rate_limiter=None, corpus_recorder=None,
                 domain_registry=None, hardening_enabled=True,
                 aggregator_min_outbound=3, aggregator_store=None,
                 aggregator_max_domains=500, revisit_cooldown_seconds=0,
                 geo_block_store=None, media_blocker=None, media_autoblock_crawls=2,
                 lang_block_store=None):
```

And in the body (next to `self._geo_block_store = geo_block_store`):

```python
        self._lang_block_store = lang_block_store
```

- [ ] **Step 4: Edit `_plan`** — surface `foreign` as a 4th tuple element

```python
    def _plan(self, cand):
        """(urls, domain, delay, foreign) for a candidate. Website candidates expand via
        the walker; without a walker, a website candidate is fetched only if root-or-target."""
        if self._walker is not None and cand.type == "website":
            plan = self._walker.walk(cand)
            return plan.urls, plan.domain, plan.crawl_delay, plan.foreign
        if cand.type == "website" and not seed_is_target(cand.url_or_handle):
            return [], None, None, False
        return [cand.url_or_handle], None, None, False
```

- [ ] **Step 5: Edit `_harvest_one`** — A-block (foreign plan) + B-block (content gate)

```python
    def _harvest_one(self, cand, fetcher, cats, known, summary) -> bool:
        urls, domain, delay, foreign = self._plan(cand)
        if foreign:
            # Foreign-language domain judged at the homepage (A): pin the whole host so it
            # is never re-walked, and skip its pages entirely.
            if self._lang_block_store is not None:
                self._lang_block_store.add(cand.url_or_handle)
            return False
        structural = False
        for url in urls:
            self._wait(cand.type, domain, delay)
            src = {"id": None, "type": cand.type, "url_or_handle": url, "name": cand.name}
            try:
                items, _ = fetcher.fetch(src, None)
                if is_non_ukrainian(" ".join(it.text or "" for it in items)):
                    # Non-Ukrainian content reached during the walk (B): pin the host, then
                    # abandon the whole domain rather than walk its remaining pages.
                    if self._lang_block_store is not None:
                        self._lang_block_store.add(cand.url_or_handle)
                    break
                if self._process_page(cand, items, cats, known, summary):
                    structural = True
            except Exception as exc:  # noqa: BLE001 — one page must not sink the domain
                summary["errors"] += 1
                log.warning("harvest page failed for %s: %s", url, exc)
        return structural
```

- [ ] **Step 6: Run to verify it passes**

Run: `python -m pytest tests/test_active_harvest.py -q`
Expected: PASS (all existing + 3 new). Existing tests pass a plain `WalkPlan(...)` whose `foreign` defaults to `False`, so `_plan` unpacking is safe.

- [ ] **Step 7: Commit**

```bash
git add crawler/crawler/discovery/harvest.py crawler/tests/test_active_harvest.py
git commit -m "feat(crawler): pin foreign-language host on gate A/B (LangBlockStore)"
```

---

## Task 5: Config + wiring

**Files:**
- Modify: `crawler/crawler/config.py` (Settings ~line 105, Config ~line 220, mapping ~line 357)
- Modify: `crawler/crawler/wiring.py:70-83` (`_build_walker`), `:104-146`/`:218-230` (`build_runner`)
- Test: `crawler/tests/test_config.py`

**Interfaces:**
- Consumes: `LanguageGate` (Task 2), `LangBlockStore` (Task 1), `DomainWalker(language_gate=)` (Task 3), `ActiveHarvester(lang_block_store=)` (Task 4).
- Produces: `config.lang_gate_enabled: bool` (default True), `config.lang_blocked_hosts_path: str` (default `/data/lang_blocked_hosts.json`). When enabled, the walker gets a `LanguageGate` and the harvester a loaded `LangBlockStore`.

- [ ] **Step 1: Write the failing test** — append to `crawler/tests/test_config.py`

```python
def test_lang_gate_defaults_on(monkeypatch):
    from crawler.config import load_config
    monkeypatch.delenv("LANG_GATE_ENABLED", raising=False)
    cfg = load_config()
    assert cfg.lang_gate_enabled is True
    assert cfg.lang_blocked_hosts_path.endswith("lang_blocked_hosts.json")


def test_lang_gate_can_be_disabled(monkeypatch):
    from crawler.config import load_config
    monkeypatch.setenv("LANG_GATE_ENABLED", "false")
    assert load_config().lang_gate_enabled is False
```

> If `test_config.py` builds the config through a different entrypoint than `load_config`, match the pattern already used by `test_grid_cities_enabled`/line 235 (`GRID_CITIES_ENABLED`). Keep the two lang tests structurally identical to that existing bool-env test.

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_config.py -q`
Expected: FAIL — `Config` has no `lang_gate_enabled`.

- [ ] **Step 3: Add the config fields** — `crawler/crawler/config.py`

In the **Settings** dataclass, next to `geo_blocked_hosts_path` (~line 105):

```python
    lang_gate_enabled: bool = True
    lang_blocked_hosts_path: str = "/data/lang_blocked_hosts.json"
```

In the **Config** dataclass, next to its `geo_blocked_hosts_path` (~line 220):

```python
    lang_gate_enabled: bool = True
    lang_blocked_hosts_path: str = "/data/lang_blocked_hosts.json"
```

In the Settings→Config mapping, next to `geo_blocked_hosts_path=s.geo_blocked_hosts_path` (~line 357):

```python
        lang_gate_enabled=s.lang_gate_enabled,
        lang_blocked_hosts_path=s.lang_blocked_hosts_path,
```

- [ ] **Step 4: Wire the LanguageGate into the walker** — `crawler/crawler/wiring.py`, `_build_walker`

Add the import near the other discovery imports at the top of the file:

```python
from crawler.discovery.language_gate import LanguageGate
```

In `_build_walker`, build the gate and pass it to `DomainWalker`:

```python
def _build_walker(config, web_client):
    domain_rl = DomainRateLimiter(config.domain_min_delay_seconds)
    robots = RobotsPolicy(web_client, domain_rl, config.robots_cache_path,
                          config.robots_cache_ttl_hours * 3600)
    language_gate = (LanguageGate(web_client, domain_rl)
                     if config.lang_gate_enabled else None)
    walker = DomainWalker(
        web_client, robots, domain_rl,
        domain_page_cap=config.domain_page_cap,
        sitemap_max_docs=config.sitemap_max_docs,
        bfs_max_depth=config.bfs_max_depth,
        bfs_max_pages=config.bfs_max_pages,
        bfs_trigger_min=config.bfs_trigger_min,
        domain_min_delay=config.domain_min_delay_seconds,
        crawl_delay_cap=config.crawl_delay_cap_seconds,
        language_gate=language_gate)
    return walker, domain_rl
```

- [ ] **Step 5: Wire the LangBlockStore into the harvester** — `crawler/crawler/wiring.py`, `build_runner`

Add the import near the top:

```python
from crawler.discovery.lang_block import LangBlockStore
```

In `build_runner`, next to `geo_block_store = GeoBlockStore(...).load()` (~line 115):

```python
    lang_block_store = (LangBlockStore(config.lang_blocked_hosts_path).load()
                        if config.lang_gate_enabled else None)
```

Then in the `ActiveHarvester(...)` construction (~line 218-230) add the argument:

```python
                                    geo_block_store=geo_block_store,
                                    media_blocker=media_blocker,
                                    media_autoblock_crawls=config.media_autoblock_crawls,
                                    lang_block_store=lang_block_store)
```

- [ ] **Step 6: Run the config test + full suite**

Run: `python -m pytest tests/test_config.py -q && python -m pytest -q`
Expected: PASS across the whole crawler suite (no regressions).

- [ ] **Step 7: Commit**

```bash
git add crawler/crawler/config.py crawler/crawler/wiring.py crawler/tests/test_config.py
git commit -m "feat(crawler): wire LanguageGate + LangBlockStore (config lang_gate_enabled)"
```

---

## Task 6: Rollout

**Files:** none in-repo (operates on the crawler `/data` volume + container image).

- [ ] **Step 1: Rebuild + restart the crawler container**

```bash
docker compose build crawler && docker compose up -d crawler
```

- [ ] **Step 2: Seed justcolor.net so it drops immediately (optional but recommended)**

Append the host to the live `/data/lang_blocked_hosts.json` so it is blocked without waiting for a re-encounter:

```bash
docker compose exec crawler python -c "from crawler.discovery.lang_block import LangBlockStore; LangBlockStore('/data/lang_blocked_hosts.json').load().add('justcolor.net')"
```

- [ ] **Step 3: Verify no more justcolor sitemap fetches**

```bash
docker compose logs --since=10m crawler | grep -c justcolor
```
Expected: `0` new sitemap fetches on subsequent passes (the pre-fetch `is_blocked_host` gate now drops the candidate).

---

## Self-Review

**Spec coverage:**
- Shared `LangBlockStore` (local /data, pushes to blocklist) → Task 1. ✓
- A: early root gate in `walk()` before sitemap, content-Cyrillic + hreflang-veto, `<html lang>` not load-bearing → Tasks 2, 3. ✓
- Block on A (`plan.foreign`) → Task 4. ✓
- B: persistent block at existing content gate → Task 4. ✓
- Config `lang_gate_enabled` (single kill-switch; off ⇒ store `None`, A skipped, B no-op) + `lang_blocked_hosts_path` → Task 5. ✓
- Conservative: thin content / fetch error → not foreign; uk/ua hreflang vetoes → Task 2 tests. ✓
- Rollout (rebuild + seed justcolor.net) → Task 6. ✓

**Placeholder scan:** none — every code/step is concrete.

**Type consistency:** `is_foreign(homepage, domain, delay)` used identically in Tasks 2/3. `WalkPlan.foreign` produced in Task 3, consumed in Task 4 `_plan`→`_harvest_one`. `LangBlockStore.add(host_or_url)` produced in Task 1, consumed in Task 4. `reload_lang_blocked`/`is_blocked_host` consistent across Tasks 1 and 6. `ActiveHarvester(..., lang_block_store=)` and `DomainWalker(..., language_gate=)` names consistent across Tasks 3/4/5.
