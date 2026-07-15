# Search Discovery (DuckDuckGo) Implementation Plan — Track A

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the disconnected `ActiveDiscovery` into the crawl pass with a best-effort `DuckDuckGoProvider`, so env-configured keyword searches produce normalised website `SourceCandidate`s that land in `suggested_sources` for moderation.

**Architecture:** A provider callable `(keyword) -> list[SourceCandidate]` built on `ddgs`; a combinator that assembles enabled providers from `SEARCH_PROVIDERS`; `wiring.py` creates `ActiveDiscovery(budget, provider)` when `ACTIVE_DISCOVERY=true` and passes it to `Runner`; `runner.run()` runs discovery after visiting sources and submits candidates as suggestions.

**Tech Stack:** Python, `ddgs` (free, keyless DuckDuckGo wrapper), existing crawler `httpx`/selectolax stack.

## Global Constraints

- **Discovery is off by default**: `ACTIVE_DISCOVERY=false` → no behaviour change; `ActiveDiscovery`/provider only built when true.
- **Best-effort**: any provider error/ban logs and returns `[]`; the crawl pass never crashes.
- **Two-stage**: discovered candidates go to `suggested_sources` (moderation), never directly to offers.
- **Env-configured** (Track A, no UI): `SEARCH_PROVIDERS` (csv, default `duckduckgo`), `SEARCH_KEYWORDS` (csv), `SEARCH_RESULTS_PER_KEYWORD` (default 7), `SEARCH_MIN_DELAY` (default 4s), `SEARCH_BUDGET` (default = keyword count).
- **ddgs API**: `DDGS().text(query, max_results=N)` → `list[dict]`; result URL is `result["href"]`.
- **`SourceCandidate`** fields (existing): `name, type, url_or_handle, discovered_from_source_id, discovery_note`.
- **SearXNG (Track B) and cross-source dedup (Track C) are OUT of scope.**
- Crawler tests run from `crawler/` via `./.venv/Scripts/python.exe -m pytest`.

---

### Task 1: ddgs dependency + DuckDuckGoProvider (TDD)

**Files:**
- Modify: `crawler/pyproject.toml` (add `ddgs` dependency)
- Create: `crawler/crawler/discovery/providers.py`
- Create: `crawler/tests/test_providers.py`

**Interfaces:**
- Produces: `_normalize_url(url: str) -> str | None`; `DuckDuckGoProvider(results_per_keyword=7, min_delay=4.0, ddgs_factory=DDGS, sleep=time.sleep)` — a callable `(keyword: str) -> list[SourceCandidate]` (type `"website"`, `url_or_handle=<normalised url>`, `name=<result title or url>`, `discovery_note="ddg: <keyword>"`).

- [ ] **Step 1: Add ddgs to `crawler/pyproject.toml`**

In the `dependencies = [` list, add:
```toml
    "ddgs>=6.0",
```
Then install: `./.venv/Scripts/python.exe -m pip install -e .`

- [ ] **Step 2: Write the failing test** — `crawler/tests/test_providers.py`

```python
from crawler.discovery.providers import DuckDuckGoProvider, _normalize_url


class FakeDDGS:
    def __init__(self, results): self._results = results
    def text(self, query, max_results=7):
        return self._results


def _provider(results):
    return DuckDuckGoProvider(results_per_keyword=3, min_delay=0,
                              ddgs_factory=lambda: FakeDDGS(results),
                              sleep=lambda _s: None)


def test_normalize_url_strips_utm_fragment_trailing_and_lowercases_host():
    assert _normalize_url("HTTPS://Shop.Example.com/deal/?utm_source=x#frag") \
        == "https://shop.example.com/deal"
    assert _normalize_url("https://ex.com/") == "https://ex.com"


def test_normalize_url_rejects_junk():
    assert _normalize_url("not a url") is None
    assert _normalize_url("") is None


def test_provider_maps_results_to_website_candidates():
    p = _provider([
        {"title": "Кафе знижки", "href": "https://cafe.example/veterans?utm_medium=x", "body": "b"},
        {"title": "Shop", "href": "https://shop.example/", "body": "b"},
    ])
    cands = p("знижки ветеранам")
    assert [c.url_or_handle for c in cands] == \
        ["https://cafe.example/veterans", "https://shop.example"]
    assert all(c.type == "website" for c in cands)
    assert cands[0].discovery_note == "ddg: знижки ветеранам"
    assert cands[0].name == "Кафе знижки"


def test_provider_is_best_effort_on_error():
    class Boom:
        def text(self, *a, **k): raise RuntimeError("banned")
    p = DuckDuckGoProvider(ddgs_factory=lambda: Boom(), min_delay=0, sleep=lambda _s: None)
    assert p("kw") == []
```

- [ ] **Step 3: Run test to verify it fails**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_providers.py -q
```
Expected: FAIL — `crawler.discovery.providers` does not exist.

- [ ] **Step 4: Implement `crawler/crawler/discovery/providers.py`**

```python
import logging
import time
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from ddgs import DDGS

from crawler.models import SourceCandidate

log = logging.getLogger(__name__)


def _normalize_url(url: str) -> str | None:
    if not url:
        return None
    p = urlsplit(url.strip())
    if p.scheme not in ("http", "https") or not p.netloc:
        return None
    query = urlencode([(k, v) for k, v in parse_qsl(p.query)
                       if not k.lower().startswith("utm_")])
    path = p.path.rstrip("/")
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), path, query, ""))


class DuckDuckGoProvider:
    """Callable (keyword) -> list[SourceCandidate]; best-effort."""

    def __init__(self, results_per_keyword: int = 7, min_delay: float = 4.0,
                 ddgs_factory=DDGS, sleep=time.sleep):
        self._n = results_per_keyword
        self._delay = min_delay
        self._ddgs_factory = ddgs_factory
        self._sleep = sleep

    def __call__(self, keyword: str) -> list[SourceCandidate]:
        if self._delay:
            self._sleep(self._delay)
        try:
            results = self._ddgs_factory().text(keyword, max_results=self._n)
        except Exception as exc:  # noqa: BLE001 — search is best-effort
            log.warning("duckduckgo search failed for %r: %s", keyword, exc)
            return []
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

- [ ] **Step 5: Run test to verify it passes**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_providers.py -q
```
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add crawler/pyproject.toml crawler/crawler/discovery/providers.py crawler/tests/test_providers.py
git commit -m "feat(crawler): DuckDuckGoProvider for search discovery"
```

---

### Task 2: Search config (env)

**Files:**
- Modify: `crawler/crawler/config.py`
- Create: `crawler/tests/test_search_config.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `Config` gains `search_providers: list[str]`, `search_keywords: list[str]`, `search_results_per_keyword: int`, `search_min_delay: float`, `search_budget: int | None`.

- [ ] **Step 1: Write the failing test** — `crawler/tests/test_search_config.py`

```python
from crawler.config import _split_csv


def test_split_csv_trims_and_drops_empty():
    assert _split_csv("a, b ,,c") == ["a", "b", "c"]
    assert _split_csv("") == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_search_config.py -q
```
Expected: FAIL — `_split_csv` does not exist.

- [ ] **Step 3: Extend `crawler/crawler/config.py`**

In `_RawSettings`, add fields (after `proxies`):
```python
    search_providers: str = "duckduckgo"
    search_keywords: str = ""
    search_results_per_keyword: int = 7
    search_min_delay: float = 4.0
    search_budget: int = 0  # 0 = process all keywords
```
In the `Config` dataclass, add:
```python
    search_providers: list[str] = field(default_factory=list)
    search_keywords: list[str] = field(default_factory=list)
    search_results_per_keyword: int = 7
    search_min_delay: float = 4.0
    search_budget: int | None = None
```
Add a helper near `_parse_proxies`:
```python
def _split_csv(raw: str) -> list[str]:
    return [c.strip() for c in raw.split(",") if c.strip()]
```
In `load_config()`, extend the returned `Config(...)` with:
```python
        search_providers=_split_csv(s.search_providers),
        search_keywords=_split_csv(s.search_keywords),
        search_results_per_keyword=s.search_results_per_keyword,
        search_min_delay=s.search_min_delay,
        search_budget=(s.search_budget or None),
```

- [ ] **Step 4: Run test to verify it passes**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_search_config.py -q
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/config.py crawler/tests/test_search_config.py
git commit -m "feat(crawler): search discovery config (providers/keywords/budget)"
```

---

### Task 3: Provider combinator + wiring

**Files:**
- Modify: `crawler/crawler/discovery/providers.py` (add `build_search_provider`)
- Modify: `crawler/crawler/wiring.py`
- Modify: `crawler/crawler/runner.py` (`Runner.__init__` accepts `discovery=None`)
- Create: `crawler/tests/test_build_provider.py`

**Interfaces:**
- Consumes: `Config` from Task 2, `DuckDuckGoProvider` from Task 1, `ActiveDiscovery(budget, search_provider)`.
- Produces: `build_search_provider(config) -> callable|None`; `Runner(api, fetchers, extractor, rate_limiter, discovery=None)`.

- [ ] **Step 1: Write the failing test** — `crawler/tests/test_build_provider.py`

```python
from types import SimpleNamespace
from crawler.discovery.providers import build_search_provider


def _cfg(**over):
    base = dict(search_providers=["duckduckgo"], search_results_per_keyword=3,
                search_min_delay=0)
    base.update(over)
    return SimpleNamespace(**base)


def test_build_returns_callable_for_known_provider():
    p = build_search_provider(_cfg())
    assert callable(p)


def test_build_returns_none_when_no_known_providers():
    assert build_search_provider(_cfg(search_providers=[])) is None
    assert build_search_provider(_cfg(search_providers=["unknown"])) is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_build_provider.py -q
```
Expected: FAIL — `build_search_provider` does not exist.

- [ ] **Step 3: Add `build_search_provider` to `crawler/crawler/discovery/providers.py`**

```python
def build_search_provider(config):
    """Combine enabled search providers into one callable, or None."""
    providers = []
    for name in config.search_providers:
        if name == "duckduckgo":
            providers.append(DuckDuckGoProvider(
                results_per_keyword=config.search_results_per_keyword,
                min_delay=config.search_min_delay))
        else:
            log.warning("unknown search provider %r, ignoring", name)
    if not providers:
        return None

    def combined(keyword):
        out = []
        for p in providers:
            out.extend(p(keyword))
        return out

    return combined
```

- [ ] **Step 4: Run test to verify it passes**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_build_provider.py -q
```
Expected: 2 passed.

- [ ] **Step 5: Add `discovery` param to `Runner.__init__`** in `crawler/crawler/runner.py`

Change the constructor (lines 37-41) to:
```python
    def __init__(self, api_client, fetchers: dict, extractor, rate_limiter, discovery=None):
        self._api = api_client
        self._fetchers = fetchers
        self._extractor = extractor
        self._rl = rate_limiter
        self._discovery = discovery
```

- [ ] **Step 6: Wire discovery in `crawler/crawler/wiring.py`**

Add imports at the top:
```python
from crawler.discovery.active import ActiveDiscovery
from crawler.discovery.providers import build_search_provider
```
At the end of `build_runner`, replace the final `return Runner(...)` line with:
```python
    discovery = None
    if config.active_discovery:
        provider = build_search_provider(config)
        if provider is not None:
            budget = config.search_budget or len(config.search_keywords)
            discovery = ActiveDiscovery(budget=budget, search_provider=provider)
    return Runner(api, fetchers, extractor, rate_limiter, discovery=discovery)
```

- [ ] **Step 7: Run the full crawler suite (nothing regressed)**

```bash
./.venv/Scripts/python.exe -m pytest -q
```
Expected: all pass (existing Runner callers still work — `discovery` defaults to `None`).

- [ ] **Step 8: Commit**

```bash
git add crawler/crawler/discovery/providers.py crawler/crawler/wiring.py crawler/crawler/runner.py crawler/tests/test_build_provider.py
git commit -m "feat(crawler): combinator + wire ActiveDiscovery into the runner"
```

---

### Task 4: Runner runs discovery → suggestions (TDD)

**Files:**
- Modify: `crawler/crawler/runner.py` (call discovery in `run()`)
- Create: `crawler/tests/test_runner_discovery.py`

**Interfaces:**
- Consumes: `Runner(..., discovery=...)` from Task 3; `config.search_keywords` (passed via wiring — see Step 4).
- Produces: after visiting sources, `run()` calls `self._discovery.run(keywords, known)` and `submit_suggestion(...)` for each candidate.

- [ ] **Step 1: Write the failing test** — `crawler/tests/test_runner_discovery.py`

```python
from crawler.runner import Runner
from crawler.models import SourceCandidate


class FakeApi:
    def __init__(self):
        self.suggested = []
    def list_target_categories(self): return []
    def list_offer_categories(self): return []
    def list_sources(self, is_active=True): return []
    def submit_suggestion(self, payload): self.suggested.append(payload); return {}


class FakeDiscovery:
    def __init__(self, cands): self._cands = cands; self.called_with = None
    def run(self, keywords, known):
        self.called_with = (keywords, set(known))
        return self._cands


def _runner(api, discovery):
    r = Runner(api, {}, extractor=None, rate_limiter=None, discovery=discovery)
    r._keywords = ["знижки ветеранам"]
    return r


def test_discovery_submits_each_candidate_as_suggestion():
    api = FakeApi()
    cand = SourceCandidate(name="Cafe", type="website",
                           url_or_handle="https://cafe.example", discovery_note="ddg: x")
    r = _runner(api, FakeDiscovery([cand]))
    summary = r.run()
    assert len(api.suggested) == 1
    assert api.suggested[0]["url_or_handle"] == "https://cafe.example"
    assert summary["suggestions"] == 1


def test_no_discovery_means_no_suggestions():
    api = FakeApi()
    r = _runner(api, None)
    r.run()
    assert api.suggested == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_runner_discovery.py -q
```
Expected: FAIL — `run()` ignores `self._discovery`.

- [ ] **Step 3: Store keywords in `Runner.__init__` and run discovery in `run()`**

In `crawler/crawler/runner.py`, add `keywords=None` to `__init__` and store it:
```python
    def __init__(self, api_client, fetchers: dict, extractor, rate_limiter,
                 discovery=None, keywords=None):
        self._api = api_client
        self._fetchers = fetchers
        self._extractor = extractor
        self._rl = rate_limiter
        self._discovery = discovery
        self._keywords = keywords or []
```
In `run()`, after the `for source in sources:` loop (just before `log.info("crawl summary...`), add:
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

- [ ] **Step 4: Pass keywords from wiring** — in `crawler/crawler/wiring.py`, update the final return to include keywords:
```python
    return Runner(api, fetchers, extractor, rate_limiter,
                  discovery=discovery, keywords=config.search_keywords)
```

- [ ] **Step 5: Run tests (new + full suite)**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_runner_discovery.py -q
./.venv/Scripts/python.exe -m pytest -q
```
Expected: new file passes; full crawler suite green.

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/runner.py crawler/crawler/wiring.py crawler/tests/test_runner_discovery.py
git commit -m "feat(crawler): run active discovery and submit suggestions"
```

---

### Task 5: Docs + env example (outbound address, keywords, run)

**Files:**
- Modify: `crawler/.env.example`
- Modify: `README-docker.md`

**Interfaces:**
- Consumes: config keys from Task 2.

- [ ] **Step 1: Add search settings to `crawler/.env.example`**

Append:
```dotenv
# --- Active search discovery (Track A) ---
ACTIVE_DISCOVERY=false
SEARCH_PROVIDERS=duckduckgo
SEARCH_RESULTS_PER_KEYWORD=7
SEARCH_MIN_DELAY=4
SEARCH_BUDGET=0
# Comma-separated search phrases:
SEARCH_KEYWORDS=знижки для учасників бойових дій, пільги УБД Україна, знижки ветеранам війни, знижки для військовослужбовців ЗСУ, спецпропозиції для ветеранів АТО ООС, знижки для сімей учасників бойових дій, пільги родинам військовослужбовців, пільги сім'ям загиблих військових, знижки родинам загиблих захисників, знижки для осіб з інвалідністю внаслідок війни, пільги ветеранам з інвалідністю, знижки для працівників ДСНС, пільги рятувальникам ДСНС, знижки для поліцейських, пільги працівникам Національної поліції, знижки для захисників України, безкоштовні послуги для військових та їхніх родин
```

- [ ] **Step 2: Add a discovery + network section to `README-docker.md`**

Append:
````markdown
## Search discovery (crawler, Track A)

The crawler can find NEW candidate sources by searching the web (DuckDuckGo).
Results go to the moderation queue (`suggested_sources`), not straight to offers.

Enable in `crawler/.env` (or crawler service env): `ACTIVE_DISCOVERY=true`.
Keywords/limits are configured there too (`SEARCH_KEYWORDS`, `SEARCH_RESULTS_PER_KEYWORD`, `SEARCH_MIN_DELAY`).

**First run manually**, then schedule:
```bash
docker compose --profile crawler run --rm crawler          # one manual pass
# then, for scheduled runs, set CRAWL_INTERVAL_SECONDS>0 and:
docker compose --profile crawler up -d crawler
```

### Outbound network address (firewall exception)

The crawler runs in Docker; its egress is NAT'd through the host, so the router
sees the **host LAN IP** as the source. On this machine that is **`192.168.20.69`**
(gateway `192.168.20.1`). Give this address to the network admin for the router's
outbound exception. Note: it is a DHCP/Wi-Fi address and can change — reserve a
static/DHCP-reserved IP so the exception stays valid. Determine it anytime with:
`Get-NetIPConfiguration | ? { $_.IPv4DefaultGateway }`.

Destination domains the crawler contacts during search (for reference):
`duckduckgo.com`, `links.duckduckgo.com`, `html.duckduckgo.com`, plus any site it discovers.
````

- [ ] **Step 3: Commit**

```bash
git add crawler/.env.example README-docker.md
git commit -m "docs(crawler): search discovery config, run flow, outbound address"
```

---

### Task 6: End-to-end verification (Docker)

**Files:** none (verification; may touch nothing or a tiny fixture note).

**Interfaces:** Consumes everything from Tasks 1–5.

- [ ] **Step 1: Rebuild the crawler image (now depends on ddgs)**

```bash
docker compose build crawler
```
Expected: build succeeds (ddgs installed in the image).

- [ ] **Step 2: Offline deterministic check (no external network)**

Confirm the wiring end-to-end with a scheduled offline run is covered by unit
tests already; here just confirm the image runs and discovery is gated off by
default:
```bash
docker compose --profile crawler run --rm crawler 2>&1 | grep "crawl summary"
```
Expected: a `crawl summary` line with `suggestions` present; with `ACTIVE_DISCOVERY`
unset/false, discovery does not run (no external calls).

- [ ] **Step 3: Real manual discovery pass (small budget)**

Temporarily enable discovery with a tiny budget to verify the real path + firewall:
```bash
docker compose --profile crawler run --rm \
  -e ACTIVE_DISCOVERY=true -e SEARCH_BUDGET=2 \
  -e "SEARCH_KEYWORDS=знижки для учасників бойових дій, пільги УБД Україна" \
  crawler 2>&1 | grep -Ei "crawl summary|discovery"
echo "=== suggested_sources ==="
docker compose exec -T db mysql -uroot -pmy-secret-pw \
  -e "USE ubd; SELECT id, LEFT(name,40) AS name, url_or_handle, status FROM suggested_sources LIMIT 10;" 2>&1 | grep -v Warning
```
Expected: `crawl summary` shows `suggestions > 0` (if DuckDuckGo responds); rows
appear in `suggested_sources`. If DuckDuckGo rate-limits/returns empty, the pass
still completes (best-effort) with `suggestions: 0` — that is acceptable and proves
resilience; retry later or from a different network.

- [ ] **Step 4: Confirm in admin**

Open admin (`:8082`) → "Запропоновані джерела" and confirm any discovered
candidates are listed for moderation.

- [ ] **Step 5: Commit (if any fixture/doc tweaks were needed)**

```bash
git commit -am "test(crawler): verify search discovery end-to-end" --allow-empty
```

---

## Self-Review

**Spec coverage:**
- `DuckDuckGoProvider` on `ddgs`, best-effort → Task 1. ✅
- Connect `ActiveDiscovery` in wiring + runner → Tasks 3–4. ✅
- Candidates → `suggested_sources` (two-stage) → Task 4. ✅
- Env config (providers/keywords/results/delay/budget) → Task 2 + Task 5 env.example. ✅
- URL normalisation (utm/fragment/trailing/host-case) → Task 1 `_normalize_url`. ✅
- Outbound source address doc (192.168.20.69 + DHCP caveat) → Task 5. ✅
- First-manual-then-scheduled run → Task 5 docs + Task 6. ✅
- Off-by-default, no behaviour change when false → Tasks 3–4 (discovery None). ✅
- Non-goals (SearXNG, dedup, UI, keyword generation) → not implemented. ✅

**Placeholder scan:** No TBD/TODO; every code step has full code; verification steps
give exact commands + expected output. Task 6 Step 5 uses `--allow-empty` so it is
valid even if verification needed no file change. ✅

**Type consistency:** `DuckDuckGoProvider(results_per_keyword, min_delay, ddgs_factory,
sleep)` and `_normalize_url` names match across Tasks 1/3/tests. `build_search_provider(config)`
returns a `callable|None` consumed by wiring (Task 3). `Runner(..., discovery=None,
keywords=None)` signature matches its construction in wiring (Task 4 Step 4) and tests.
`SourceCandidate` fields (`name/type/url_or_handle/discovered_from_source_id/discovery_note`)
match `suggestion_payload` in runner.py and the provider output. `result["href"]` matches
the verified ddgs return shape. ✅
