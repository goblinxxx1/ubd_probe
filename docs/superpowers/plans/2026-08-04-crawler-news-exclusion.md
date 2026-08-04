# Track A — News exclusion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or executing-plans. Steps use `- [ ]`.

**Goal:** News/media sites never enter the active crawl — curated SEED blocklist expansion + drop blocklisted hosts from the candidate pool + live state purge; the moderator "Заблокувати" button handles the tail.

**Architecture:** crawler-only. Extend `blocklist.py::_MEDIA` (suffix-match already covers subdomains); make `DomainFeed` and the `site:` pool skip `is_blocked_host`; purge existing news hosts from live `/data` state. No backend/admin/extractor changes.

**Tech Stack:** Python, crawler pytest.

## Global Constraints
- crawler-only; no backend/admin/extractor/attribution changes.
- Curated list only — NO heuristic (news-token/`.media`) — to avoid false positives on legit businesses.
- `is_blocked_host` already = never-fetch (track blocklist=no-fetch) and never-recorded (gate precedes `registry.record`); this track additionally keeps blocklisted hosts OUT of the candidate pool (no wasted slots) + purges existing.
- TDD test-first; run `./.venv/Scripts/python.exe -m pytest -q` from `crawler/`.

---

### Task 1: Expand SEED media/news blocklist

**Files:**
- Modify: `crawler/crawler/discovery/blocklist.py` (`_MEDIA` set)
- Test: `crawler/tests/test_blocklist.py`

**Interfaces:**
- Consumes/Produces: `is_blocked_host(host)` returns True for the added hosts and their subdomains (existing suffix-match logic, unchanged).

- [ ] **Step 1: Write the failing test**

Add to `crawler/tests/test_blocklist.py`:
```python
def test_curated_news_hosts_are_blocked():
    from crawler.discovery import blocklist
    blocklist.reload_learned(None)  # SEED-only
    for h in ["znaj.ua", "breaking.znaj.ua", "ukrainianwall.com",
              "week.ukrainianwall.com", "kosht.media", "epravda.com.ua",
              "protocol.ua", "focus.ua", "glavcom.ua", "thepage.ua",
              "parlament.ua", "kharakter.media"]:
        assert blocklist.is_blocked_host(h) is True, h
    # a legit business host must stay allowed
    assert blocklist.is_blocked_host("rozetka.com.ua") is False
```

- [ ] **Step 2: Run — fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_blocklist.py::test_curated_news_hosts_are_blocked -v`
Expected: FAIL (hosts not yet in SEED).

- [ ] **Step 3: Implement — extend `_MEDIA`**

In `crawler/crawler/discovery/blocklist.py`, extend the `_MEDIA` set with a curated news/media block (append inside the existing set literal):
```python
    # curated UA news/media that leaked as "productive" providers (Track A)
    "znaj.ua", "ukrainianwall.com", "kosht.media", "epravda.com.ua",
    "protocol.ua", "focus.ua", "glavcom.ua", "thepage.ua", "parlament.ua",
    "kharakter.media",
    # well-known national news outlets (curated, confident — not businesses)
    "liga.net", "hromadske.ua", "suspilne.media", "ukrinform.ua",
    "korrespondent.net", "gordonua.com", "lb.ua", "zaxid.net",
```
(Suffix-match `host == d or host.endswith("."+d)` already covers `breaking.znaj.ua`, `week.ukrainianwall.com`, etc.)

- [ ] **Step 4: Run — passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_blocklist.py -v`
Expected: PASS (new test + existing blocklist tests green).

- [ ] **Step 5: Commit**
```bash
git add crawler/crawler/discovery/blocklist.py crawler/tests/test_blocklist.py
git commit -m "feat(crawler): blocklist curated UA news/media hosts (Track A)"
```

---

### Task 2: Drop blocklisted hosts from the candidate pool

**Files:**
- Modify: `crawler/crawler/discovery/domain_feed.py` (`DomainFeed.candidates`)
- Modify: `crawler/crawler/runner.py` (`run_active` site: branch — filter `registry.top`)
- Test: `crawler/tests/test_domain_feed.py`, `crawler/tests/test_runner.py`

**Interfaces:**
- Consumes: `is_blocked_host(host)` from `crawler.discovery.blocklist`.
- Produces: `DomainFeed.candidates` never emits a blocklisted host; the site: pool excludes blocklisted registry hosts.

- [ ] **Step 1: Write failing test (DomainFeed)**

In `crawler/tests/test_domain_feed.py` (create if absent):
```python
from crawler.discovery.domain_feed import DomainFeed
from crawler.discovery import blocklist


class _Reg:
    def __init__(self, hosts): self._hosts = hosts
    def top(self, n, known_hosts):
        return [h for h in self._hosts if h not in known_hosts][:n]


def test_domain_feed_skips_blocklisted_hosts():
    blocklist.reload_learned(["bad.ua"])
    try:
        feed = DomainFeed(_Reg(["good.ua", "bad.ua", "shop.ua"]), per_pass=8)
        hosts = [c.url_or_handle for c in feed.candidates(set())]
    finally:
        blocklist.reload_learned(None)
    assert "https://bad.ua" not in hosts
    assert "https://good.ua" in hosts and "https://shop.ua" in hosts
```

- [ ] **Step 2: Run — fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_domain_feed.py::test_domain_feed_skips_blocklisted_hosts -v`
Expected: FAIL (bad.ua currently emitted).

- [ ] **Step 3: Implement — DomainFeed filter**

In `crawler/crawler/discovery/domain_feed.py`:
```python
from crawler.discovery.blocklist import is_blocked_host
from crawler.models import SourceCandidate


class DomainFeed:
    def __init__(self, registry, per_pass=8):
        self._registry = registry
        self._per_pass = per_pass

    def candidates(self, known_hosts):
        out = []
        for host in self._registry.top(self._per_pass, known_hosts):
            if is_blocked_host(host):
                continue
            out.append(SourceCandidate(
                name=host, type="website", url_or_handle=f"https://{host}",
                discovered_from_source_id=None,
                discovery_note=f"domain-rating:{host}"))
        return out
```

- [ ] **Step 4: Write failing test (runner site: filter)**

In `crawler/tests/test_runner.py`, add (reuse existing fakes `FakeApi`/`FakeFetcher`/`_rl`/`DomainRegistry`/`SearchState`/`SiteQueryPlanner`/`_MutatingDiscovery` already imported there):
```python
def test_site_query_excludes_blocklisted_registry_hosts(tmp_path):
    from crawler.discovery import blocklist
    api = FakeApi([{"id": 1, "type": "website", "name": "S", "url_or_handle": "http://x"}])
    reg = DomainRegistry(str(tmp_path / "r.json"), clock=lambda: 1.0)
    reg.record("proven.ua", offers=3, errors=0)   # productive, allowed
    reg.record("badnews.ua", offers=3, errors=0)  # productive, will be blocklisted
    state = SearchState(str(tmp_path / "s.json"), clock=lambda: 1.0)
    disc = _MutatingDiscovery()
    blocklist.reload_learned(["badnews.ua"])
    try:
        runner = Runner(api, {"website": FakeFetcher([])}, get_extractor("heuristic"), _rl(),
                        harvester=_RecordingHarvester(), discovery=disc, domain_registry=reg,
                        site_planner=SiteQueryPlanner(terms=("знижка",)),
                        site_state=state, site_query_budget=5)
        runner.run_active()
    finally:
        blocklist.reload_learned(None)
    qs = " ".join(q for call in disc.calls for q in call)
    assert "proven.ua" in qs
    assert "badnews.ua" not in qs
```

- [ ] **Step 5: Run — fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_runner.py::test_site_query_excludes_blocklisted_registry_hosts -v`
Expected: FAIL (badnews.ua present in site: queries).

- [ ] **Step 6: Implement — runner site: filter**

In `crawler/crawler/runner.py`: add import near the top:
```python
from crawler.discovery.blocklist import is_blocked_host
```
In `run_active`, in the site: branch, filter the registry pool:
```python
                reg = [h for h in self._domain_registry.top(self._site_query_budget, known_hosts)
                       if not is_blocked_host(h)]
```
(Replaces the current `reg = self._domain_registry.top(...)` line.)

- [ ] **Step 7: Run — passes + full suite**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_domain_feed.py tests/test_runner.py -q`
then `./.venv/Scripts/python.exe -m pytest -q`
Expected: all green.

- [ ] **Step 8: Commit**
```bash
git add crawler/crawler/discovery/domain_feed.py crawler/crawler/runner.py crawler/tests/test_domain_feed.py crawler/tests/test_runner.py
git commit -m "feat(crawler): drop blocklisted hosts from DomainFeed + site: pool (Track A)"
```

---

### Deploy / live cleanup (post-merge, not a TDD task)
1. Canonical crawler rebuild.
2. One-shot purge in the crawler container (like prior cleanups): with `is_blocked_host` loaded from the API, remove blocklisted hosts from `domain_registry.json`, `brand_domains.json`, `osm_domains.json`, `aggregator_domains.json`, `robots_cache.json`, and `search_state.json` cache candidates.
3. Verify live: the ~10 news hosts → `is_blocked_host`=True; absent from registry top pool; crawler no longer fetches them.

## Self-Review notes
- Spec §"Розширити SEED" → Task 1. §"Не тримати блоклістнуте у пулі" → Task 2 (DomainFeed + site:). §"Жива чистка" → Deploy step. §"Хвіст (кнопка)" → already shipped ([[ubd-reject-block-host]]).
- No placeholders; code shown per step.
- Names consistent: `is_blocked_host`, `DomainFeed.candidates`, `run_active` site: branch.
- No heuristic (curated only), per spec.
