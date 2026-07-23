# Crawler per-domain `site:` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a gated P3 recall lever that issues narrow `site:{domain} {intent-term}` search queries for productive + approved-partner domains, surfacing promo pages the sitemap/BFS walker misses.

**Architecture:** A pure generator (`SiteQueryPlanner`) builds `site:` query strings from a domain pool assembled in `Runner.run()` (interleaved `DomainRegistry.top` + rotated approved website hosts). Queries flow through the existing `ActiveDiscovery → provider → candidates → ActiveHarvester` path. Site-sourced candidates carry a new `bypass_host_skip` flag so approved-partner pages are fetched (host-skip only guarded passive-walk duplication). A `site_cursor` in `SearchState` rotates the intent-term phase across passes.

**Tech Stack:** Python 3.11, pytest, existing crawler package (`crawler/`).

## Global Constraints

- Scope is `crawler/` only — no backend, no admin, no DB schema, no migrations.
- Baseline test count is **361** crawler tests, all green; new tests add on top. Run from `crawler/`: `./.venv/Scripts/python.exe -m pytest -q`.
- `site_query_enabled=False` MUST be **byte-equivalent** to pre-track behaviour (the lever's code path is not entered).
- The lever fires only when all three are on: `site_query_enabled` AND `active_discovery` AND `domain_rating_enabled` (registry present). Any off → silent no-op.
- Intent terms are Ukrainian, exact: `знижка`, `акція`, `промокод`, `спеціальна ціна`, `пільгова ціна`, `спеціальна пропозиція`, `сертифікат`. Audience terms are intentionally excluded (recall/precision boundary).
- Config defaults: `site_query_enabled=True`, `site_query_budget=5`.
- Follow existing patterns: keyword-args with defaults on `Runner`/`ActiveHarvester`, curated tuples for vocab, `monkeypatch.chdir(tmp_path)` for default-config tests.

---

### Task 1: `SiteQueryPlanner` generator

**Files:**
- Create: `crawler/crawler/discovery/site_query.py`
- Test: `crawler/tests/test_site_query.py`

**Interfaces:**
- Produces:
  - `SITE_INTENT_FORMS: tuple[str, ...]` — 7 curated Ukrainian intent forms (exact list in Global Constraints).
  - `class SiteQueryPlanner:`
    - `__init__(self, terms=SITE_INTENT_FORMS)`
    - `next_batch(self, domains: list[str], budget: int, cursor: int) -> tuple[list[str], int]` — one rotating term per domain (`domain[i] → terms[(cursor + i) % len(terms)]`), capped at `budget` domains; filters empty/None domains; returns `(queries, new_cursor)` where `new_cursor = (cursor + 1) % len(terms)`; empty `terms` → `([], cursor)`.

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_site_query.py
from crawler.discovery.site_query import SITE_INTENT_FORMS, SiteQueryPlanner


def _planner():
    return SiteQueryPlanner(terms=("знижка", "акція"))


def test_builds_site_prefixed_query_per_domain():
    batch, cur = _planner().next_batch(["a.ua", "b.ua"], budget=5, cursor=0)
    assert batch == ["site:a.ua знижка", "site:b.ua акція"]   # different term per domain index
    assert cur == 1                                            # phase advanced by 1


def test_budget_caps_domain_count():
    batch, _ = _planner().next_batch(["a.ua", "b.ua", "c.ua"], budget=2, cursor=0)
    assert batch == ["site:a.ua знижка", "site:b.ua акція"]    # third domain dropped


def test_cursor_phase_rotates_terms_between_passes():
    batch, cur = _planner().next_batch(["a.ua"], budget=5, cursor=1)
    assert batch == ["site:a.ua акція"]                        # cursor=1 → terms[1]
    assert cur == 0                                            # (1 + 1) % 2


def test_empty_and_none_domains_filtered():
    batch, _ = _planner().next_batch(["a.ua", "", None, "b.ua"], budget=5, cursor=0)
    assert batch == ["site:a.ua знижка", "site:b.ua акція"]    # indices on filtered list


def test_empty_terms_is_safe():
    batch, cur = SiteQueryPlanner(terms=()).next_batch(["a.ua"], budget=5, cursor=3)
    assert batch == [] and cur == 3


def test_default_terms_nonempty_and_deterministic():
    p = SiteQueryPlanner()
    assert "знижка" in SITE_INTENT_FORMS and len(SITE_INTENT_FORMS) == 7
    assert p.next_batch(["a.ua"], 5, 0) == p.next_batch(["a.ua"], 5, 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_site_query.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'crawler.discovery.site_query'`

- [ ] **Step 3: Write minimal implementation**

```python
# crawler/crawler/discovery/site_query.py
"""Offline generator for narrow per-domain `site:` search queries.

For a productive/partner domain, ask the search engine which promo pages it indexes
that our sitemap/BFS walker missed — via `site:{domain} {intent-term}`. Audience is
intentionally absent: the domain constrains scope and the downstream relevance-gate
enforces audience (recall here, precision there). Deterministic, stable order."""

# Curated intent surface forms (no audience, no gov/NGO-program noise).
SITE_INTENT_FORMS = (
    "знижка", "акція", "промокод", "спеціальна ціна", "пільгова ціна",
    "спеціальна пропозиція", "сертифікат",
)


class SiteQueryPlanner:
    """One rotating intent term per domain; the cursor rotates the term phase per pass."""

    def __init__(self, terms=SITE_INTENT_FORMS):
        self._terms = tuple(terms)

    def next_batch(self, domains, budget, cursor):
        if not self._terms:
            return [], cursor
        doms = [d for d in domains if d][:max(0, int(budget))]
        out = [f"site:{d} {self._terms[(cursor + i) % len(self._terms)]}"
               for i, d in enumerate(doms)]
        return out, (cursor + 1) % len(self._terms)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_site_query.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/site_query.py crawler/tests/test_site_query.py
git commit -m "feat(crawler): SiteQueryPlanner generator for narrow per-domain site: queries"
```

---

### Task 2: `SearchState.site_cursor`

**Files:**
- Modify: `crawler/crawler/discovery/search_state.py` (`_EMPTY` dict; new property + setter)
- Test: `crawler/tests/test_search_state.py` (append)

**Interfaces:**
- Consumes: existing `SearchState` (path, `_save()`, `load()` `setdefault` loop).
- Produces:
  - `SearchState.site_cursor -> int` (property, default 0)
  - `SearchState.set_site_cursor(value: int) -> None` (persists via `_save()`)

- [ ] **Step 1: Write the failing test**

```python
# append to crawler/tests/test_search_state.py
def test_site_cursor_defaults_zero(tmp_path):
    st = _state(tmp_path, Clock())
    assert st.site_cursor == 0


def test_set_site_cursor_persists_and_is_independent(tmp_path):
    path = str(tmp_path / "state.json")
    st = SearchState(path, clock=Clock())
    st.set_grid_cursor(42)      # grid cursor — separate field
    st.set_site_cursor(5)       # site cursor — separate field
    reloaded = SearchState.load(path)
    assert reloaded.site_cursor == 5
    assert reloaded.grid_cursor == 42


def test_old_state_file_without_site_cursor_loads(tmp_path):
    import json as _json
    path = tmp_path / "partial.json"
    path.write_text(_json.dumps({"version": 1, "cursor": 0, "grid_cursor": 3,
                                 "next_allowed_at": 0.0, "backends": {}, "cache": {}}),
                    encoding="utf-8")
    st = SearchState.load(str(path), clock=Clock())
    assert st.site_cursor == 0          # missing key defaults cleanly
    assert st.grid_cursor == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_search_state.py -q -k site_cursor`
Expected: FAIL — `AttributeError: 'SearchState' object has no attribute 'site_cursor'`

- [ ] **Step 3: Write minimal implementation**

In `crawler/crawler/discovery/search_state.py`, add `"site_cursor": 0` to `_EMPTY`:

```python
_EMPTY = {"version": 1, "cursor": 0, "grid_cursor": 0, "site_cursor": 0,
          "next_allowed_at": 0.0, "backends": {}, "cache": {}}
```

And add, right after the `grid_cursor` property/setter block (after `set_grid_cursor`):

```python
    # --- site-query rotation cursor (separate from grid/backend cursors) ---
    @property
    def site_cursor(self) -> int:
        return int(self._data.get("site_cursor", 0))

    def set_site_cursor(self, value: int) -> None:
        self._data["site_cursor"] = int(value)
        self._save()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_search_state.py -q`
Expected: PASS (all, including the 3 new)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/search_state.py crawler/tests/test_search_state.py
git commit -m "feat(crawler): persistent site_cursor in SearchState"
```

---

### Task 3: `SourceCandidate.bypass_host_skip` + harvester host-skip

**Files:**
- Modify: `crawler/crawler/models.py` (`SourceCandidate` — new field)
- Modify: `crawler/crawler/discovery/harvest.py:41` (host-skip guard)
- Test: `crawler/tests/test_active_harvest.py` (append)

**Interfaces:**
- Consumes: `SourceCandidate`, `ActiveHarvester.harvest(..., known_hosts=...)`.
- Produces: `SourceCandidate.bypass_host_skip: bool = False`; harvester host-skip is bypassed when the flag is True.

- [ ] **Step 1: Write the failing test**

```python
# append to crawler/tests/test_active_harvest.py
def test_source_candidate_defaults_no_bypass():
    assert SourceCandidate(name="x", type="website",
                           url_or_handle="https://x.ua").bypass_host_skip is False


def test_bypass_host_skip_forces_fetch_of_known_host(tmp_path):
    api = FakeApi()
    cand = _cand(url="https://cafe.example")
    cand.bypass_host_skip = True                       # site:-sourced candidate
    h = ActiveHarvester(api, {"website": _RecFetcher("Знижка 20% УБД")},
                        GateExtractor(), rate_limiter=None, fetch_budget=5)
    summary = _summary()
    h.harvest([cand], cats=None, known=set(), summary=summary,
              known_hosts={"cafe.example"})            # host normally skipped
    assert summary["offers"] == 1                      # fetched anyway
```

(The existing `test_website_candidate_in_known_hosts_is_skipped` already covers the
`bypass_host_skip=False` skip case — do not duplicate it.)

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_active_harvest.py -q -k bypass_host_skip`
Expected: FAIL — `AttributeError: 'SourceCandidate' object has no attribute 'bypass_host_skip'`

- [ ] **Step 3: Write minimal implementation**

In `crawler/crawler/models.py`, add the field to `SourceCandidate`:

```python
@dataclass
class SourceCandidate:
    name: str
    type: str
    url_or_handle: str
    discovered_from_source_id: int | None = None
    discovery_note: str | None = None
    bypass_host_skip: bool = False   # site:-sourced candidates set True; host-skip only guarded
                                     # passive-walk duplication, which a site:-page is not
```

In `crawler/crawler/discovery/harvest.py`, change the host-skip guard (currently line 41):

```python
            if (cand.type == "website" and not cand.bypass_host_skip
                    and _host(cand.url_or_handle) in known_hosts):
                continue
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_active_harvest.py -q`
Expected: PASS (all, including the 2 new; existing skip test still green)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/models.py crawler/crawler/discovery/harvest.py crawler/tests/test_active_harvest.py
git commit -m "feat(crawler): bypass_host_skip so site: pages on approved domains are fetched"
```

---

### Task 4: config flags

**Files:**
- Modify: `crawler/crawler/config.py` (`_RawSettings`, `Config`, `load_config`)
- Test: `crawler/tests/test_config.py` (append)

**Interfaces:**
- Produces: `Config.site_query_enabled: bool = True`, `Config.site_query_budget: int = 5`.

- [ ] **Step 1: Write the failing test**

```python
# append to crawler/tests/test_config.py
def test_site_query_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)      # no .env -> defaults apply
    cfg = load_config()
    assert cfg.site_query_enabled is True
    assert cfg.site_query_budget == 5


def test_site_query_env_overrides(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SITE_QUERY_ENABLED", "false")
    monkeypatch.setenv("SITE_QUERY_BUDGET", "9")
    cfg = load_config()
    assert cfg.site_query_enabled is False
    assert cfg.site_query_budget == 9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_config.py -q -k site_query`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'site_query_enabled'`

- [ ] **Step 3: Write minimal implementation**

In `crawler/crawler/config.py`:

1. In `_RawSettings`, add near the other search flags (e.g. after `search_queries_per_pass`):
```python
    site_query_enabled: bool = True
    site_query_budget: int = 5
```

2. In the `Config` dataclass, add (after `search_queries_per_pass`):
```python
    site_query_enabled: bool = True
    site_query_budget: int = 5
```

3. In `load_config()`'s `Config(...)` call, add:
```python
        site_query_enabled=s.site_query_enabled,
        site_query_budget=s.site_query_budget,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_config.py -q`
Expected: PASS (all, including the 2 new)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/config.py crawler/tests/test_config.py
git commit -m "feat(crawler): site_query_enabled / site_query_budget config flags"
```

---

### Task 5: wiring + runner integration

**Files:**
- Modify: `crawler/crawler/wiring.py` (build planner, pass to `Runner`)
- Modify: `crawler/crawler/runner.py` (`__init__` params, `zip_longest` import, site block)
- Test: `crawler/tests/test_wiring.py` (append), `crawler/tests/test_runner.py` (append)

**Interfaces:**
- Consumes: `SiteQueryPlanner` (Task 1), `SearchState.site_cursor`/`set_site_cursor` (Task 2), `SourceCandidate.bypass_host_skip` (Task 3), `Config.site_query_enabled`/`site_query_budget` (Task 4), existing `DomainRegistry.top(n, known_hosts)`, `ActiveDiscovery.run(keywords, known)`.
- Produces: `Runner.__init__` gains `site_planner=None, site_state=None, site_query_budget=5`; `Runner.run()` generates and runs site queries in the candidate block.

- [ ] **Step 1: Write the failing tests**

```python
# append to crawler/tests/test_runner.py
from crawler.discovery.search_state import SearchState
from crawler.discovery.site_query import SiteQueryPlanner


class _MutatingDiscovery:
    """Records each keyword list passed; returns one candidate per call."""
    def __init__(self): self.calls = []
    def run(self, keywords, known):
        self.calls.append(list(keywords))
        return [SourceCandidate(name="site", type="website",
                                url_or_handle="https://proven.ua/promo")]


def test_site_query_block_generates_flags_and_advances_cursor(tmp_path):
    src = {"id": 1, "type": "website", "name": "Silpo", "url_or_handle": "https://silpo.ua"}
    api = FakeApi([src])
    reg = DomainRegistry(str(tmp_path / "r.json"), clock=lambda: 1.0)
    reg.record("proven.ua", offers=2, errors=0)          # productive, non-approved
    state = SearchState(str(tmp_path / "s.json"), clock=lambda: 1.0)
    disc = _MutatingDiscovery()
    hv = _RecordingHarvester()
    runner = Runner(api, {"website": FakeFetcher([])}, get_extractor("heuristic"), _rl(),
                    harvester=hv, discovery=disc, domain_registry=reg,
                    site_planner=SiteQueryPlanner(terms=("знижка", "акція")),
                    site_state=state, site_query_budget=5)
    runner.run()

    site_qs = disc.calls[-1]
    assert "site:proven.ua знижка" in site_qs             # productive domain
    assert "site:silpo.ua акція" in site_qs               # approved partner (interleaved, next term)
    assert hv.candidates and all(c.bypass_host_skip for c in hv.candidates)
    assert SearchState.load(str(tmp_path / "s.json")).site_cursor == 1   # advanced & persisted


def test_site_query_off_is_byte_equivalent(tmp_path):
    src = {"id": 1, "type": "website", "name": "Silpo", "url_or_handle": "https://silpo.ua"}
    api = FakeApi([src])
    reg = DomainRegistry(str(tmp_path / "r.json"), clock=lambda: 1.0)
    reg.record("proven.ua", offers=2, errors=0)
    disc = _MutatingDiscovery()
    runner = Runner(api, {"website": FakeFetcher([])}, get_extractor("heuristic"), _rl(),
                    harvester=_RecordingHarvester(), discovery=disc, domain_registry=reg,
                    domain_feed=_StubFeed([]),
                    site_planner=None, site_state=None)   # lever off
    runner.run()
    assert disc.calls == []                               # no site queries issued
```

```python
# append to crawler/tests/test_wiring.py
from crawler.discovery.site_query import SiteQueryPlanner


def _base_cfg(tmp_path, **kw):
    defaults = dict(
        internal_api_url="http://api", crawler_api_key="k", extractor="heuristic",
        request_timeout=5.0, min_delay_seconds=0.0, bot_accounts=[], proxies={},
        search_providers=[], search_state_path=str(tmp_path / "state.json"),
        brand_feed_enabled=False, domain_registry_path=str(tmp_path / "r.json"))
    defaults.update(kw)
    return Config(**defaults)


def test_build_runner_wires_site_query_lever(tmp_path):
    cfg = _base_cfg(tmp_path, active_discovery=True, site_query_enabled=True,
                    site_query_budget=7, domain_rating_enabled=True)
    runner = build_runner(cfg)
    assert isinstance(runner._site_planner, SiteQueryPlanner)
    assert runner._site_state is not None            # active_discovery on → shared state
    assert runner._site_query_budget == 7


def test_build_runner_site_query_disabled(tmp_path):
    cfg = _base_cfg(tmp_path, active_discovery=True, site_query_enabled=False)
    runner = build_runner(cfg)
    assert runner._site_planner is None


def test_build_runner_site_state_none_without_active_discovery(tmp_path):
    cfg = _base_cfg(tmp_path, active_discovery=False, site_query_enabled=True)
    runner = build_runner(cfg)
    assert runner._site_planner is not None
    assert runner._site_state is None                # no active search → no state to rotate
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_runner.py tests/test_wiring.py -q -k "site_query or site_state"`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'site_planner'` (runner) / `AttributeError: ... '_site_planner'` (wiring)

- [ ] **Step 3: Write minimal implementation**

In `crawler/crawler/runner.py`:

1. Add the import at the top (with the other imports):
```python
from itertools import zip_longest
```

2. Extend `Runner.__init__` signature — append three keyword params after `domain_evict_ttl_seconds=2_592_000.0`:
```python
                 domain_evict_min_score=0.1, domain_evict_ttl_seconds=2_592_000.0,
                 site_planner=None, site_state=None, site_query_budget=5):
```
and store them in the body:
```python
        self._site_planner = site_planner
        self._site_state = site_state
        self._site_query_budget = site_query_budget
```

3. In `run()`, inside `if self._harvester is not None:`, insert the site block **after** the
   `brand_feed` candidates line and **before** `if candidates:`:
```python
                if (self._site_planner is not None and self._site_state is not None
                        and self._discovery is not None and self._domain_registry is not None):
                    cur = self._site_state.site_cursor
                    reg = self._domain_registry.top(self._site_query_budget, known_hosts)
                    approved = sorted(known_hosts)
                    if approved:
                        off = cur % len(approved)
                        approved = approved[off:] + approved[:off]   # rotate large partner sets
                    pool = [d for pair in zip_longest(reg, approved) for d in pair if d]
                    site_queries, new_cur = self._site_planner.next_batch(
                        pool, self._site_query_budget, cur)
                    self._site_state.set_site_cursor(new_cur)
                    if site_queries:
                        site_cands = self._discovery.run(site_queries, known)
                        for c in site_cands:
                            c.bypass_host_skip = True
                        candidates += site_cands
```

In `crawler/crawler/wiring.py`:

4. Bind `state` unconditionally, then build the planner. `state` is currently assigned only
   inside `if config.active_discovery:`, so add `state = None` on the line **immediately before**
   that block:
```python
    state = None
    if config.active_discovery:
        state = SearchState.load(config.search_state_path)
        ...
```
   Then, after the `active_discovery` block and before the `return Runner(...)`, add:
```python
    site_planner = None
    site_state = None
    if config.site_query_enabled:
        from crawler.discovery.site_query import SiteQueryPlanner
        site_planner = SiteQueryPlanner()
        site_state = state if config.active_discovery else None   # rotate only when search runs
```

5. Extend the `return Runner(...)` call with the three new kwargs:
```python
                  domain_evict_min_score=config.domain_evict_min_score,
                  domain_evict_ttl_seconds=config.domain_evict_ttl_hours * 3600,
                  site_planner=site_planner, site_state=site_state,
                  site_query_budget=config.site_query_budget)
```

- [ ] **Step 4: Run tests to verify they pass, then the full suite**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_runner.py tests/test_wiring.py -q`
Expected: PASS (all, including the 5 new)

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — 361 baseline + new tests, all green.

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/runner.py crawler/crawler/wiring.py crawler/tests/test_runner.py crawler/tests/test_wiring.py
git commit -m "feat(crawler): wire per-domain site: lever into Runner (union pool, bypass host-skip)"
```

---

## Final verification (after all tasks)

- [ ] Full suite green from `crawler/`: `./.venv/Scripts/python.exe -m pytest -q`
- [ ] Request opus whole-branch code review (superpowers:requesting-code-review) before merge.
- [ ] Live Docker check: enable the lever, confirm well-formed `site:` queries are generated for
      target domains (registry-productive and/or approved partners) with term interleaving; with
      `SITE_QUERY_ENABLED=false` behaviour is byte-equivalent.
- [ ] Merge to `main` (ff), delete branch, update `docs/RESUME.md` + memory.

## Self-review notes (traceability to spec)

- Spec component 1 (`site_query.py`) → Task 1. Component 2 (`site_cursor`) → Task 2.
  Components 3–4 (`bypass_host_skip` field + harvest guard) → Task 3. Component 5 (config) → Task 4.
  Components 6–7 (wiring + runner union block) → Task 5.
- Gate (three levels) → covered by Task 5 tests (`site_query_off_is_byte_equivalent`,
  `site_state_none_without_active_discovery`) + Task 4 (flag defaults).
- Interleave/union + approved-partner inclusion + `bypass_host_skip=True` on site cands →
  `test_site_query_block_generates_flags_and_advances_cursor`.
- Audience-omission is a design boundary, not code — no task (correct).
