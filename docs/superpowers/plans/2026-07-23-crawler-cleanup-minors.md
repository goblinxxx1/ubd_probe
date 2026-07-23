# Crawler cleanup minors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retire six accumulated crawler tech-debt items (A–F from the spec) as small, independently testable tasks, changing no live behavior except wiring an already-documented config knob (A) and broadening a schema-type matcher (B).

**Architecture:** Seven TDD tasks. Five are 1–2 file local changes (E, C, B, A, F). Item D — consolidating the copy-pasted bare-host idiom — is split into D1 (create the shared helper + tests) and D2 (migrate all call sites), so the risky migration gets its own reviewer gate.

**Tech Stack:** Python crawler, pytest.

## Global Constraints

- Crawler tests from `crawler/`: `./.venv/Scripts/python.exe -m pytest -q`. Baseline **350** passing. No backend/admin/frontend/DB; MySQL not required.
- Live moderation gate and deterministic core untouched.
- Byte-safe defaults: A and D must not change behavior for the live input shape (URL with a scheme, no port) at defaults.
- Single bare-host helper after D: `bare_host(value) -> str` = thorough (strips scheme via `//`-prepend, userinfo `@`, port `:`, leading `www.`, lowercases) + dual-mode (scheme-less inputs resolve to their host), returns `""` on empty/invalid. Call sites preserve their existing `str | None` vs `str` return contract via thin wrappers.

Order: E → C → B → A → F → D1 → D2 (D last as the broadest change).

---

### Task 1 (E): move mid-file import to the top in test_blocklist.py

**Files:**
- Modify: `crawler/tests/test_blocklist.py`

Cosmetic. `crawler/tests/test_blocklist.py:80` has a module-level `from crawler.discovery import blocklist` sitting mid-file (between test functions). Move it into the top import block. No behavior change; the deliverable is the suite staying green. (The function-local `from crawler.discovery.blocklist import is_blocked_telegram` imports inside individual tests are a separate, intentional pattern — leave them.)

- [ ] **Step 1: Edit the file**

At the top of `crawler/tests/test_blocklist.py`, the first line is:

```python
from crawler.discovery.blocklist import is_blocked_host
```

Add the module import right after it so the top block reads:

```python
from crawler.discovery.blocklist import is_blocked_host
from crawler.discovery import blocklist
```

Then delete the mid-file line (currently at line 80, a standalone `from crawler.discovery import blocklist` preceded/followed by blank lines) together with its now-redundant surrounding blank line, so the two `reload_learned` tests follow the preceding test with normal spacing.

- [ ] **Step 2: Run the blocklist suite**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_blocklist.py -q`
Expected: PASS (same count as before — a pure move).

- [ ] **Step 3: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: 350 passed.

- [ ] **Step 4: Commit**

```bash
git add crawler/tests/test_blocklist.py
git commit -m "refactor(crawler): hoist mid-file import in test_blocklist"
```

---

### Task 2 (C): None-guard `int(outbound_hosts)` in host_miner

**Files:**
- Modify: `crawler/crawler/learn/host_miner.py`
- Test: `crawler/tests/test_host_miner.py` (append)

**Interfaces:**
- Consumes: corpus rows (dict with optional `outbound_hosts`).
- Produces: `mine_hosts` treats `outbound_hosts=None` as 0 instead of raising.

- [ ] **Step 1: Write the failing test**

```python
# append to crawler/tests/test_host_miner.py
def test_none_outbound_hosts_treated_as_zero():
    rows = [{"host": "x.ua", "label": "pass", "is_article": True,
             "outbound_hosts": None, "pos_anchor": False, "url": "https://x.ua/a"}
            for _ in range(3)]
    s = {x.host: x for x in mine_hosts(rows)}["x.ua"]
    assert s.aggregator_ratio == 0.0
    assert s.support == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_host_miner.py::test_none_outbound_hosts_treated_as_zero -q`
Expected: FAIL — `TypeError: int() argument must be ... not 'NoneType'`.

- [ ] **Step 3: Implement**

In `crawler/crawler/learn/host_miner.py`, change both `outbound_hosts` reads (currently at lines 28 and 30) from `int(r.get("outbound_hosts", 0))` to `int(r.get("outbound_hosts") or 0)`:

```python
        if int(r.get("outbound_hosts") or 0) >= aggregator_min_outbound:
            a["aggr"] += 1
        if r.get("pos_anchor") and int(r.get("outbound_hosts") or 0) == 0:
            a["provider"] += 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_host_miner.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/learn/host_miner.py crawler/tests/test_host_miner.py
git commit -m "fix(crawler): host_miner treats None outbound_hosts as 0"
```

---

### Task 3 (B): broaden `_ARTICLE_TYPE` to catch `*Article` subtypes + `Report`

**Files:**
- Modify: `crawler/crawler/fetchers/website.py`
- Test: `crawler/tests/test_website_fetcher.py` (append)

**Interfaces:**
- Produces: `_has_article_schema`/`is_article` now True for `TechArticle`, `ScholarlyArticle`, `Report` (and existing `NewsArticle`/`BlogPosting`/`LiveBlogPosting`). Business-schema guard unchanged, so `is_media` still cannot re-classify a `LocalBusiness`-tagged page.

- [ ] **Step 1: Write the failing test**

The test module already has a `_fetcher_returning(html)` helper. Append:

```python
# append to crawler/tests/test_website_fetcher.py
def test_tech_article_subtype_sets_is_article():
    html = ('<html><head>'
            '<script type="application/ld+json">'
            '{"@context":"https://schema.org","@type":"TechArticle","headline":"Огляд"}'
            '</script></head><body>'
            '<article>Знижка 20% для ветеранів детально розписана тут</article>'
            '</body></html>')
    f = _fetcher_returning(html)
    items, _ = f.fetch({"id": 1, "url_or_handle": "https://news.example/a"}, None)
    assert items and items[0].is_article is True
    assert items[0].has_business_schema is False


def test_report_type_sets_is_article():
    html = ('<html><head>'
            '<script type="application/ld+json">'
            '{"@context":"https://schema.org","@type":"Report","headline":"Звіт"}'
            '</script></head><body>'
            '<p>Знижка 20% для ветеранів у місті протягом місяця</p>'
            '</body></html>')
    f = _fetcher_returning(html)
    items, _ = f.fetch({"id": 1, "url_or_handle": "https://ngo.example/r"}, None)
    assert items and items[0].is_article is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_website_fetcher.py -q`
Expected: FAIL — `TechArticle`/`Report` not detected (`is_article is False`).

- [ ] **Step 3: Implement**

In `crawler/crawler/fetchers/website.py`, change the `_ARTICLE_TYPE` alternation (currently at lines 124–126) so the trailing `\bArticle\b` becomes a plain `Article` substring (which subsumes `TechArticle`/`ScholarlyArticle`/`NewsArticle`) and add `Report`:

```python
_ARTICLE_TYPE = re.compile(
    r'"@type"\s*:\s*"[^"]*(?:NewsArticle|BlogPosting|LiveBlogPosting|Report|Article)',
    re.IGNORECASE)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_website_fetcher.py -q`
Expected: PASS (new + existing, including the `LocalBusiness`→business-not-article case).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/fetchers/website.py crawler/tests/test_website_fetcher.py
git commit -m "feat(crawler): _ARTICLE_TYPE catches *Article subtypes and Report"
```

---

### Task 4 (A): wire `AGGREGATOR_MIN_OUTBOUND` into the live gate

**Files:**
- Modify: `crawler/crawler/discovery/harvest.py`
- Modify: `crawler/crawler/wiring.py:140-145`
- Test: `crawler/tests/test_active_harvest.py` (append)

**Interfaces:**
- Consumes: `config.aggregator_min_outbound` (already exists, default 3).
- Produces: `ActiveHarvester(..., aggregator_min_outbound: int = 3)`; `_process_page` passes it into `attribute(...)`. Default keeps every existing caller byte-identical.

- [ ] **Step 1: Write the failing test**

This test spies on the `attribute` call to prove the configured threshold is threaded through (the semantics of the threshold itself are already covered by `tests/test_attribution.py`). Append:

```python
# append to crawler/tests/test_active_harvest.py
def test_harvester_threads_aggregator_threshold(monkeypatch):
    import crawler.discovery.harvest as hv
    seen = {}
    def spy(item, ctx, **kw):
        seen.update(kw)
        return None                      # drop → no offer submitted
    monkeypatch.setattr(hv, "attribute", spy)
    api = FakeApi()
    h = ActiveHarvester(api, {"website": FakeFetcher([_item("Знижка 20% для УБД у нас",
                                                            site_name="Cafe")])},
                        GateExtractor(), rate_limiter=None, fetch_budget=5,
                        aggregator_min_outbound=7)
    h.harvest([_cand()], cats=None, known=set(), summary=_summary())
    assert seen.get("aggregator_min_outbound") == 7
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_active_harvest.py::test_harvester_threads_aggregator_threshold -q`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'aggregator_min_outbound'`.

- [ ] **Step 3: Implement**

In `crawler/crawler/discovery/harvest.py`, add the parameter to `ActiveHarvester.__init__` (after `hardening_enabled=True`) and store it:

```python
    def __init__(self, api, fetchers, extractor, rate_limiter, fetch_budget=20,
                 walker=None, domain_rate_limiter=None, corpus_recorder=None,
                 domain_registry=None, hardening_enabled=True,
                 aggregator_min_outbound=3):
```

```python
        self._hardening_enabled = hardening_enabled
        self._aggregator_min_outbound = aggregator_min_outbound
```

In `_process_page`, pass it into the `attribute(...)` call (currently at line 91):

```python
            attr = attribute(item, ctx, hardening_enabled=self._hardening_enabled,
                             aggregator_min_outbound=self._aggregator_min_outbound)
```

In `crawler/crawler/wiring.py`, add the argument to the `ActiveHarvester(...)` construction (currently ending at line 145 with `hardening_enabled=config.attribution_hardening_enabled`):

```python
        harvester = ActiveHarvester(api, fetchers, extractor, rate_limiter,
                                    fetch_budget=config.active_fetch_budget,
                                    walker=walker, domain_rate_limiter=domain_rl,
                                    corpus_recorder=corpus_recorder,
                                    domain_registry=domain_registry,
                                    hardening_enabled=config.attribution_hardening_enabled,
                                    aggregator_min_outbound=config.aggregator_min_outbound)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_active_harvest.py tests/test_wiring.py -q`
Expected: PASS (new threading test + existing wiring/harvest tests green).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/harvest.py crawler/crawler/wiring.py crawler/tests/test_active_harvest.py
git commit -m "feat(crawler): thread aggregator_min_outbound into the live attribution gate"
```

---

### Task 5 (F): tie-break test for `DomainRegistry.top()`

**Files:**
- Test: `crawler/tests/test_domain_registry.py` (append)

**Interfaces:**
- Consumes: existing `_reg(tmp_path, **kw)` helper, `DomainRegistry.record(host, offers, errors)`, `DomainRegistry.top(n, known_hosts)`.

- [ ] **Step 1: Write the test**

`top` sorts by `(-score, host)`. This locks in the host tiebreaker on equal scores. Append:

```python
# append to crawler/tests/test_domain_registry.py
def test_top_tie_break_by_host_on_equal_scores(tmp_path):
    r = _reg(tmp_path, offer_weight=1.0)
    r.record("b.ua", offers=5, errors=0)      # recorded first
    r.record("a.ua", offers=5, errors=0)      # equal score
    assert r.top(10, set()) == ["a.ua", "b.ua"]   # host asc, not insertion order
```

- [ ] **Step 2: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_domain_registry.py::test_top_tie_break_by_host_on_equal_scores -q`
Expected: PASS (this is a characterization test for existing correct behavior).

- [ ] **Step 3: Commit**

```bash
git add crawler/tests/test_domain_registry.py
git commit -m "test(crawler): lock DomainRegistry.top() host tie-break on equal scores"
```

---

### Task 6 (D1): create the shared `bare_host` helper

**Files:**
- Create: `crawler/crawler/util/__init__.py`
- Create: `crawler/crawler/util/hosts.py`
- Test: `crawler/tests/test_hosts.py` (create)

**Interfaces:**
- Produces: `bare_host(value: str | None) -> str` — thorough + dual-mode superset (see Global Constraints). Returns `""` on empty/invalid. Consumed by Task 7.

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_hosts.py
from crawler.util.hosts import bare_host


def test_scheme_url_to_bare_host():
    assert bare_host("https://shop.ua/deal?x=1") == "shop.ua"


def test_strips_www():
    assert bare_host("https://www.shop.ua/") == "shop.ua"


def test_strips_port_and_userinfo():
    assert bare_host("http://user:pw@www.shop.ua:8080/x") == "shop.ua"


def test_scheme_less_input_resolves_to_host():
    assert bare_host("shop.ua") == "shop.ua"
    assert bare_host("www.shop.ua") == "shop.ua"


def test_empty_and_none_return_empty_string():
    assert bare_host("") == ""
    assert bare_host(None) == ""
    assert bare_host("   ") == ""


def test_subdomain_preserved():
    assert bare_host("https://sub.shop.ua/p") == "sub.shop.ua"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_hosts.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'crawler.util'`.

- [ ] **Step 3: Implement**

Create `crawler/crawler/util/__init__.py` (empty file).

Create `crawler/crawler/util/hosts.py`:

```python
"""Єдиний нормалізатор голого хоста для всього краулера.

Приймає як повний URL ("https://www.shop.ua:8080/x"), так і вже голий хост
("shop.ua"): знімає схему, userinfo, порт і провідний "www."; повертає ""
для порожнього/невалідного входу. Раніше ця ідіома копіпастилась у ~10 місцях."""

from urllib.parse import urlsplit


def bare_host(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    netloc = urlsplit(raw if "//" in raw else "//" + raw).netloc.lower()
    netloc = netloc.split("@")[-1].split(":")[0]
    return netloc.removeprefix("www.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_hosts.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/util/__init__.py crawler/crawler/util/hosts.py crawler/tests/test_hosts.py
git commit -m "feat(crawler): shared bare_host normalizer in util/hosts"
```

---

### Task 7 (D2): migrate all bare-host call sites to `bare_host`

**Files:**
- Modify: `crawler/crawler/discovery/attribution.py:31-33`
- Modify: `crawler/crawler/discovery/brand_feed.py:139-150`
- Modify: `crawler/crawler/learn/labeler.py:19-20`
- Modify: `crawler/crawler/discovery/walker.py:18-21`
- Modify: `crawler/crawler/learn/corpus.py:11-18`
- Modify: `crawler/crawler/extract/heuristic.py:11-17`
- Modify: `crawler/crawler/discovery/providers.py:36-37`
- Modify: `crawler/crawler/discovery/blocklist.py:31,38`
- Modify: `crawler/crawler/learn/host_vetoes.py:9`
- Modify: `crawler/crawler/learn/run_host_miner.py:4,11-16,22`

**Interfaces:**
- Consumes: `bare_host` (Task 6).
- Produces: no behavior change for scheme'd-URL inputs at the call sites; each site keeps its prior return contract. This is a refactor — the gate is the full suite staying green (350 + the tests added in Tasks 2–6).

Each `_host` wrapper preserves its module's existing return type (`str | None` vs `str`). The bare-string and inline idioms call `bare_host` directly.

- [ ] **Step 1: Migrate the `_host` wrappers and idioms**

`crawler/crawler/discovery/attribution.py` — replace the `_host` body (lines 31-33), preserving `str | None`:

```python
def _host(url: str) -> str | None:
    return bare_host(url) or None
```

Add the import at the top of `attribution.py` (with the other `from crawler...` imports):

```python
from crawler.util.hosts import bare_host
```

`crawler/crawler/discovery/brand_feed.py` — replace the `_host` body (lines 139-150), preserving `str | None`:

```python
def _host(url: str) -> str | None:
    """Bare registrable host: strip scheme, userinfo, port, path, and a leading www."""
    return bare_host(url) or None
```

Add `from crawler.util.hosts import bare_host` to `brand_feed.py`'s imports. If the `urlparse` import becomes unused after this change, remove it.

`crawler/crawler/learn/labeler.py` — replace the `_host` body (lines 19-20), preserving `str`:

```python
def _host(url: str | None) -> str:
    return bare_host(url)
```

Add `from crawler.util.hosts import bare_host` to `labeler.py`; remove the now-unused `urlsplit` import if nothing else uses it.

`crawler/crawler/discovery/walker.py` — replace the `_host` body (lines 18-21), preserving `str`:

```python
def _host(url: str) -> str:
    return bare_host(url)
```

Add `from crawler.util.hosts import bare_host` to `walker.py`; remove the now-unused `urlsplit`/`urlparse` import if nothing else uses it.

`crawler/crawler/learn/corpus.py` — rewrite `_outbound_count` (lines 11-18) to use `bare_host`:

```python
def _outbound_count(item) -> int:
    src = bare_host(getattr(item, "url", None))
    hosts = set()
    for raw in getattr(item, "links", None) or []:
        h = bare_host(raw)
        if h and h != src:
            hosts.add(h)
    return len(hosts)
```

Replace the `from urllib.parse import urlsplit` import in `corpus.py` with `from crawler.util.hosts import bare_host` (confirm `urlsplit` is not used elsewhere in the file; if it is, keep it).

`crawler/crawler/extract/heuristic.py` — in `_pick_target` (lines 11-17), replace the two host derivations:

```python
def _pick_target(links, source_url: str) -> str | None:
    src_host = bare_host(source_url)
    for raw in links or []:
        norm = _normalize_url(raw or "")
        if not norm:
            continue
        host = bare_host(norm)
```

Add `from crawler.util.hosts import bare_host` to `heuristic.py`; remove the `from urllib.parse import urlsplit` import if `urlsplit` is now unused in the file.

`crawler/crawler/discovery/providers.py` — in `classify_candidate` (lines 36-37), keep `parts = urlsplit(norm)` (its `.path` is still needed) but derive `host` via `bare_host`:

```python
    parts = urlsplit(norm)
    host = bare_host(norm)
    path = parts.path or "/"
```

Add `from crawler.util.hosts import bare_host` to `providers.py` (keep the existing `urlsplit` import — still used for `parts`).

`crawler/crawler/discovery/blocklist.py` — replace the two inline idioms. In `reload_learned` (line 31):

```python
    norm = {bare_host(h) for h in hosts if h and h.strip()}
```

In `is_blocked_host` (line 38):

```python
    host = bare_host(host)
```

Add `from crawler.util.hosts import bare_host` to `blocklist.py`'s top imports (next to `import re`). Note: `_tg_handle` (line 61) uses `removeprefix("@")` for a Telegram handle — that is NOT a host; leave it unchanged.

`crawler/crawler/learn/host_vetoes.py` — replace the protected-set normalization (line 9):

```python
    protected = {bare_host(h) for h in (protected_hosts or set())}
```

Add `from crawler.util.hosts import bare_host` to `host_vetoes.py` (next to the existing `from crawler.discovery.blocklist import is_blocked_host`).

`crawler/crawler/learn/run_host_miner.py` — delete the local `_bare_host` (lines 11-16), import the shared one, and use it (line 22):

```python
from crawler.learn.corpus import read_corpus
from crawler.learn.host_miner import mine_hosts
from crawler.learn.host_vetoes import survivors
from crawler.util.hosts import bare_host
```

```python
    protected = {bare_host(h) for h in (protected_hosts or set())}
```

Remove the now-unused `from urllib.parse import urlsplit` import from `run_host_miner.py`.

- [ ] **Step 2: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: all pass (350 baseline + tests added in Tasks 2–6). If any test fails because it encoded port-bearing or scheme-less-returns-`""` behavior, STOP and report it — that is a real semantic conflict, not something to silently override.

- [ ] **Step 3: Commit**

```bash
git add crawler/crawler/discovery/attribution.py crawler/crawler/discovery/brand_feed.py crawler/crawler/learn/labeler.py crawler/crawler/discovery/walker.py crawler/crawler/learn/corpus.py crawler/crawler/extract/heuristic.py crawler/crawler/discovery/providers.py crawler/crawler/discovery/blocklist.py crawler/crawler/learn/host_vetoes.py crawler/crawler/learn/run_host_miner.py
git commit -m "refactor(crawler): consolidate bare-host derivation onto util.hosts.bare_host"
```

---

## Self-Review

**Spec coverage:**
- Item A → Task 4. Item B → Task 3. Item C → Task 2. Item D → Tasks 6 (helper) + 7 (migration). Item E → Task 1. Item F → Task 5.
- Excluded items (telegram recall gap, build_page_ctx micro-opt, domain-rating cosmetics, duplicative coverage tests) — no tasks, per spec non-goals.

**Placeholder scan:** none — every code step shows the exact edit. The only conditional instructions ("remove the import if now unused") are explicit and verifiable by the implementer against the file.

**Type consistency:** `bare_host(value: str | None) -> str` is defined in Task 6 and consumed identically in Task 7. Return-contract preservation is explicit per call site (`str | None` wrappers return `bare_host(url) or None`; `str` wrappers return `bare_host(url)`). `aggregator_min_outbound` (Task 4) matches the existing `attribute(item, ctx, aggregator_min_outbound=3)` signature and the existing `config.aggregator_min_outbound` field.

## Deferred / out of scope
Per spec non-goals: telegram `site_name=None` relevance recall gap; `build_page_ctx` outbound compute when hardening off; domain-rating cosmetics; purely duplicative coverage tests.
