# Search Harvest-Completion Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the active crawler from orphaning searched-but-unharvested candidates for the full cache TTL (168h), so every business a query finds eventually reaches moderation.

**Architecture:** Decouple three states that are currently conflated — *searched/cached* (DDG answered, don't re-search), *harvested* (candidates actually consumed by the fetch budget), and *grid cursor* (where to resume searching new phrases). Cache entries gain a `harvested` flag. Each active pass **drains** cached-but-unharvested candidates first (no DDG re-search), then searches new due phrases only if fetch-budget remains. After harvest, a phrase is marked `harvested` only when **all** its candidates were consumed. Candidates carry an `origin_key` so the interleaved harvest can be mapped back to phrases.

**Tech Stack:** Python 3.12, pytest, dataclasses, JSON state file (`/data/search_state.json`).

## Global Constraints

- Crawler tests run from `crawler/` with `./.venv/Scripts/python.exe -m pytest -q` on Windows. Use a clean `--basetemp` (the shared pytest tmpdir symlink `pytest-current` throws `PermissionError` on this host): `--basetemp="$env:TEMP/pt"`.
- Backward compatibility: existing `search_state.json` cache entries have **no** `harvested` key. A missing `harvested` MUST be treated as `True` (already done) so the fix does NOT re-drain the entire existing 795-entry cache on first run.
- Freshness (avoid re-hitting DDG) MUST remain keyed on `ts`/TTL exactly as today. This plan never re-searches a fresh phrase.
- No new dependencies. Deterministic; no wall-clock in tests (inject `clock`).
- `SourceCandidate` is a shared dataclass (`crawler/crawler/models.py`); the new field MUST be optional with a default so every existing construction site keeps working.

---

### Task 1: `SourceCandidate.origin_key`

**Files:**
- Modify: `crawler/crawler/models.py` (SourceCandidate dataclass)
- Test: `crawler/tests/test_models.py`

**Interfaces:**
- Produces: `SourceCandidate(..., origin_key: str | None = None)` — a free-form provenance tag. Search sets it to the phrase; other feeds may leave it `None` (out of scope here).

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_models.py
from crawler.models import SourceCandidate

def test_source_candidate_origin_key_optional_default_none():
    c = SourceCandidate(name="Shop", type="website", url_or_handle="https://x.ua")
    assert c.origin_key is None

def test_source_candidate_origin_key_settable():
    c = SourceCandidate(name="Shop", type="website", url_or_handle="https://x.ua",
                        origin_key="стоматологія знижка убд")
    assert c.origin_key == "стоматологія знижка убд"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_models.py -q --basetemp="$env:TEMP/pt1"`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'origin_key'`

- [ ] **Step 3: Add the field**

In `crawler/crawler/models.py`, add to the `SourceCandidate` dataclass, after the existing `discovery_note` field, a new optional field:

```python
    origin_key: str | None = None
```

(Keep it last so positional construction elsewhere is unaffected.)

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_models.py -q --basetemp="$env:TEMP/pt1b"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/models.py crawler/tests/test_models.py
git commit -m "feat(crawler): SourceCandidate.origin_key provenance tag"
```

---

### Task 2: Cache `harvested` flag + SearchState methods

**Files:**
- Modify: `crawler/crawler/discovery/search_state.py:135` (`cache_put`) and add methods after `cache_put`
- Test: `crawler/tests/test_search_state.py`

**Interfaces:**
- Consumes: `SourceCandidate` (Task 1), `self._clock`, `self._key(keyword)`, `self._data["cache"]`, `self._save()`.
- Produces:
  - `cache_put(keyword, candidates)` — unchanged signature; now writes `"harvested": False`.
  - `mark_harvested(keywords: list[str]) -> None` — set `harvested=True` for each key; one `_save()`.
  - `unharvested(ttl_seconds: float) -> list[tuple[str, list[SourceCandidate]]]` — fresh (`ts` within ttl) entries whose `harvested` is falsy, **oldest `ts` first**; each candidate carries `origin_key = <the cache key>`. A missing `harvested` key counts as `True` (already done → NOT returned).

- [ ] **Step 1: Write the failing tests**

```python
# crawler/tests/test_search_state.py  (append)
from crawler.models import SourceCandidate

def _cand(u):
    return SourceCandidate(name=u, type="website", url_or_handle=u)

def test_cache_put_marks_unharvested_and_unharvested_returns_it(tmp_path):
    from crawler.discovery.search_state import SearchState
    clk = [1000.0]
    st = SearchState(str(tmp_path / "s.json"), clock=lambda: clk[0])
    st.cache_put("стоматологія убд", [_cand("https://a.ua"), _cand("https://b.ua")])
    out = st.unharvested(ttl_seconds=10_000)
    assert [k for k, _ in out] == ["стоматологія убд"]
    cands = out[0][1]
    assert [c.url_or_handle for c in cands] == ["https://a.ua", "https://b.ua"]
    assert all(c.origin_key == "стоматологія убд" for c in cands)

def test_mark_harvested_removes_from_unharvested(tmp_path):
    from crawler.discovery.search_state import SearchState
    st = SearchState(str(tmp_path / "s.json"), clock=lambda: 1000.0)
    st.cache_put("шиномонтаж військовим", [_cand("https://a.ua")])
    st.mark_harvested(["шиномонтаж військовим"])
    assert st.unharvested(ttl_seconds=10_000) == []

def test_unharvested_skips_stale_by_ttl(tmp_path):
    from crawler.discovery.search_state import SearchState
    clk = [1000.0]
    st = SearchState(str(tmp_path / "s.json"), clock=lambda: clk[0])
    st.cache_put("окуляри зсу", [_cand("https://a.ua")])
    clk[0] = 1000.0 + 20_000            # now older than ttl
    assert st.unharvested(ttl_seconds=10_000) == []

def test_legacy_entry_without_harvested_key_counts_as_done(tmp_path):
    # An entry written by the OLD code (no "harvested" key) must NOT be re-drained.
    import json
    from crawler.discovery.search_state import SearchState
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"version": 1, "cache": {
        "legacy phrase": {"ts": 1000.0, "candidates": [{"name": "x", "type": "website",
                                                          "url_or_handle": "https://x.ua"}]}}}),
                 encoding="utf-8")
    st = SearchState(str(p), clock=lambda: 1001.0)
    assert st.unharvested(ttl_seconds=10_000) == []

def test_unharvested_oldest_first(tmp_path):
    from crawler.discovery.search_state import SearchState
    clk = [1000.0]
    st = SearchState(str(tmp_path / "s.json"), clock=lambda: clk[0])
    st.cache_put("phrase-old", [_cand("https://old.ua")])
    clk[0] = 2000.0
    st.cache_put("phrase-new", [_cand("https://new.ua")])
    assert [k for k, _ in st.unharvested(ttl_seconds=10_000)] == ["phrase-old", "phrase-new"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_search_state.py -q -k "unharvested or harvested or legacy" --basetemp="$env:TEMP/pt2"`
Expected: FAIL — `AttributeError: 'SearchState' object has no attribute 'unharvested'`

- [ ] **Step 3: Implement the flag + methods**

In `crawler/crawler/discovery/search_state.py`, change `cache_put` (line ~135) to write the flag:

```python
    def cache_put(self, keyword: str, candidates: list[SourceCandidate]) -> None:
        self._data["cache"][self._key(keyword)] = {
            "ts": self._clock(),
            "harvested": False,
            "candidates": [{"name": c.name, "type": c.type, "url_or_handle": c.url_or_handle}
                           for c in candidates],
        }
        self._save()
```

Add directly after `cache_put`:

```python
    def mark_harvested(self, keywords: list[str]) -> None:
        cache = self._data["cache"]
        touched = False
        for kw in keywords:
            entry = cache.get(self._key(kw))
            if entry is not None and not entry.get("harvested", True):
                entry["harvested"] = True
                touched = True
        if touched:
            self._save()

    def unharvested(self, ttl_seconds: float) -> list[tuple[str, list["SourceCandidate"]]]:
        now = self._clock()
        rows = []
        for key, entry in self._data["cache"].items():
            if entry.get("harvested", True):          # missing key == legacy == done
                continue
            if now - entry.get("ts", 0.0) >= ttl_seconds:
                continue
            rows.append((entry.get("ts", 0.0), key, entry.get("candidates", [])))
        rows.sort(key=lambda r: r[0])                 # oldest ts first
        out = []
        for _ts, key, raw in rows:
            out.append((key, [SourceCandidate(name=c["name"], type=c["type"],
                                              url_or_handle=c["url_or_handle"],
                                              discovered_from_source_id=None,
                                              discovery_note=f"ddg-cache: {key}",
                                              origin_key=key)
                              for c in raw]))
        return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_search_state.py -q --basetemp="$env:TEMP/pt2b"`
Expected: PASS (all, including the pre-existing cache tests)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/search_state.py crawler/tests/test_search_state.py
git commit -m "feat(crawler): cache harvested flag + unharvested/mark_harvested (legacy=done)"
```

---

### Task 3: Harvest returns how far it got (`stop_index`)

**Files:**
- Modify: `crawler/crawler/discovery/harvest.py:40-84` (`harvest`)
- Test: `crawler/tests/test_harvest.py`

**Interfaces:**
- Produces: `harvest(candidates, cats, known, summary, known_hosts=None) -> int`. Returns the number of leading candidates the pass **examined** — i.e. the loop position where it stopped. Everything in `candidates[:stop_index]` was either fetched or deliberately gate-skipped (both = done); `candidates[stop_index:]` was never touched (budget break). Returns `len(candidates)` when the whole list was processed. Callers that ignore the return value are unaffected.

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_harvest.py  (append; reuse this file's existing fakes/fixtures)
def test_harvest_returns_stop_index_at_budget(monkeypatch):
    # Build a harvester with fetch_budget=2 and 5 fetchable website candidates.
    from crawler.discovery.harvest import Harvester
    from crawler.models import SourceCandidate

    class _F:  # fetcher that yields no items (fetch counts against budget anyway)
        def fetch(self, src, key): return [], key

    cands = [SourceCandidate(name=f"c{i}", type="website",
                             url_or_handle=f"https://biz{i}.ua") for i in range(5)]
    h = Harvester(api=_FakeApi(), fetchers={"website": _F()}, extractor=_NoopExtractor(),
                  rate_limiter=_NoDelayRL(), fetch_budget=2, walker=None, registry=None,
                  revisit_cooldown=0, hardening_enabled=True)
    summary = {"sources": 0, "offers": 0, "suggestions": 0, "expired": 0, "errors": 0}
    stop = h.harvest(cands, cats=_EmptyCats(), known=set(), summary=summary)
    assert stop == 2            # examined 2, then budget break before the 3rd

def test_harvest_returns_len_when_all_processed():
    from crawler.discovery.harvest import Harvester
    from crawler.models import SourceCandidate

    class _F:
        def fetch(self, src, key): return [], key

    cands = [SourceCandidate(name="c", type="website", url_or_handle="https://biz.ua")]
    h = Harvester(api=_FakeApi(), fetchers={"website": _F()}, extractor=_NoopExtractor(),
                  rate_limiter=_NoDelayRL(), fetch_budget=10, walker=None, registry=None,
                  revisit_cooldown=0, hardening_enabled=True)
    summary = {"sources": 0, "offers": 0, "suggestions": 0, "expired": 0, "errors": 0}
    assert h.harvest(cands, cats=_EmptyCats(), known=set(), summary=summary) == 1
```

> Note for the implementer: `_FakeApi`, `_NoopExtractor`, `_NoDelayRL`, `_EmptyCats` — if these helpers don't already exist in `test_harvest.py`, define minimal versions: `_FakeApi` with a no-op `submit_offer`/`submit_suggestion`; `_NoopExtractor.extract` returns `None`; `_NoDelayRL.wait(*a)` does nothing; `_EmptyCats` is any object (unused when extractor returns None). Check the top of the existing `test_harvest.py` first and reuse whatever is there.

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_harvest.py -q -k stop_index --basetemp="$env:TEMP/pt3"`
Expected: FAIL — `assert None == 2` (harvest currently returns `None`)

- [ ] **Step 3: Return the stop index**

In `crawler/crawler/discovery/harvest.py`, change the `harvest` loop header and add the return. Replace the `for cand in candidates:` loop (line ~43) so it enumerates and captures the break position, and `return` it:

```python
    def harvest(self, candidates, cats, known, summary, known_hosts=None) -> int:
        known_hosts = known_hosts or set()
        used = 0
        stop = 0
        for idx, cand in enumerate(candidates):
            if used >= self._budget:
                return idx                    # budget break: idx..end untouched
            stop = idx + 1
            # ... existing body unchanged (gates use `continue`, fetch does `used += 1`) ...
        return stop
```

Keep the entire existing loop body (foreign/low-value/blocked/cooldown/known/host-skip `continue`s, `used += 1`, `_harvest_one`, `registry.record`) exactly as-is between the `stop = idx + 1` line and the end of the loop. Only the `for` header, the early `return idx`, and the final `return stop` change.

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_harvest.py -q --basetemp="$env:TEMP/pt3b"`
Expected: PASS (all existing harvest tests still pass — they ignore the return value)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/harvest.py crawler/tests/test_harvest.py
git commit -m "feat(crawler): harvest returns stop index (examined prefix length)"
```

---

### Task 4: SearchPass drains unharvested first, tags candidates

**Files:**
- Modify: `crawler/crawler/discovery/search_pass.py:28-44` (`run`)
- Test: `crawler/tests/test_search_pass.py`

**Interfaces:**
- Consumes: `state.unharvested(ttl)` and `SourceCandidate.origin_key` (Tasks 1-2); existing `_collect_due`, `plan.discovery.run`, `state.grid_cursor`, `state.set_grid_cursor`, `plan.succeeded()`.
- Produces: `run(known)` returns a candidate list that **starts with** all currently-unharvested cached candidates (each tagged `origin_key`), followed by freshly-searched new-phrase candidates (also tagged `origin_key = phrase`). Drained phrases are NOT re-searched (no DDG). The grid cursor still advances over the newly-searched due phrases only.

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_search_pass.py  (append; reuse existing _State/_Discovery fakes)
def test_run_drains_unharvested_before_searching(tmp_path):
    from crawler.discovery.search_pass import SearchPass
    from crawler.discovery.search_state import SearchState
    from crawler.models import SourceCandidate

    st = SearchState(str(tmp_path / "s.json"), clock=lambda: 1000.0)
    # a prior pass cached a phrase's candidates but never harvested them
    st.cache_put("імплантація знижка військовим",
                 [SourceCandidate(name="giorno", type="website",
                                  url_or_handle="https://giorno-dentale.com")])

    class _Disc:
        def __init__(self): self.searched = []
        def run(self, keywords, known):
            self.searched += keywords
            return [SourceCandidate(name="new", type="website", url_or_handle="https://new.ua")]

    disc = _Disc()
    from crawler.discovery.providers import SearchProviderPlan
    plan = SearchProviderPlan(name="ddg", discovery=disc, include_pins=False,
                              succeeded=lambda: True)
    grid = _grid_of(["імплантація знижка військовим", "phraseB", "phraseC"])  # helper in this file
    sp = SearchPass([plan], st, grid, block_size=2, static_keywords=None,
                    ttl_seconds=10_000)
    out = sp.run(known=set())

    urls = [c.url_or_handle for c in out]
    # drained candidate comes FIRST, and its phrase was NOT re-searched
    assert urls[0] == "https://giorno-dentale.com"
    assert out[0].origin_key == "імплантація знижка військовим"
    assert "імплантація знижка військовим" not in disc.searched
```

> `_grid_of` / `_State` / provider fakes: reuse the helpers already at the top of `test_search_pass.py`; if `_grid_of` doesn't exist, build a `QueryGrid(list)` from `crawler.discovery.query_grid`.

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_search_pass.py -q -k drains --basetemp="$env:TEMP/pt4"`
Expected: FAIL — drained candidate not returned (currently `run` only searches due phrases)

- [ ] **Step 3: Implement drain-first**

In `crawler/crawler/discovery/search_pass.py`, replace `run` (lines 28-44) with:

```python
    def run(self, known) -> list[SourceCandidate]:
        out: list[SourceCandidate] = []
        size = len(self._grid)
        if size == 0 or not self._plans:
            return out
        plan = self._plans[0]
        # 1) DRAIN: re-surface cached-but-unharvested candidates (no DDG re-search).
        if self._ttl > 0:
            for _kw, cands in self._state.unharvested(self._ttl):
                out.extend(cands)
        # 2) SEARCH new due phrases (fresh phrases are skipped by _collect_due / cache).
        cursor = self._state.grid_cursor
        if self._ttl > 0:
            batch, new_cursor = self._collect_due(cursor, size)
        else:
            batch, new_cursor = self._grid.next_batch(self._bs, cursor)
        pins = self._pins if plan.include_pins else []
        keywords = merge_queries(batch, pins)
        searched = plan.discovery.run(keywords, known)
        for c in searched:
            if c.origin_key is None and c.discovery_note and ": " in c.discovery_note:
                c.origin_key = c.discovery_note.split(": ", 1)[1]
        out.extend(searched)
        if plan.succeeded():
            self._state.set_grid_cursor(new_cursor)
        return out
```

> Rationale: freshly-searched candidates carry `discovery_note="ddg:{backend}: {keyword}"`; we lift the keyword into `origin_key` when the provider didn't set it. Drained candidates already carry `origin_key` from `unharvested`.

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_search_pass.py -q --basetemp="$env:TEMP/pt4b"`
Expected: PASS (all, including existing search_pass tests)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/search_pass.py crawler/tests/test_search_pass.py
git commit -m "feat(crawler): search pass drains unharvested candidates before searching new phrases"
```

---

### Task 5: run_active marks fully-consumed phrases harvested

**Files:**
- Modify: `crawler/crawler/runner.py:118-146` (feed collection + harvest call in `run_active`)
- Test: `crawler/tests/test_runner.py`

**Interfaces:**
- Consumes: `harvest(...) -> int` (Task 3), `SourceCandidate.origin_key` (Task 1), `search_pass._state.mark_harvested` (Task 2).
- Produces: after harvest, run_active computes, for every search `origin_key` present in `candidates`, whether **all** of that key's candidates sit at positions `< stop_index`; those keys are passed to `mark_harvested`. Phrases straddling `stop_index` stay unharvested and are re-drained next pass.

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_runner.py  (append)
def test_run_active_marks_only_fully_consumed_phrases(monkeypatch):
    from crawler.models import SourceCandidate
    marked = {}

    # search pass returns 3 candidates: phraseA (pos0,1), phraseB (pos2)
    class _SP:
        _state = type("S", (), {"mark_harvested": staticmethod(lambda ks: marked.setdefault("ks", list(ks)))})()
        def run(self, known):
            return [SourceCandidate(name="a1", type="website", url_or_handle="https://a1.ua", origin_key="phraseA"),
                    SourceCandidate(name="a2", type="website", url_or_handle="https://a2.ua", origin_key="phraseA"),
                    SourceCandidate(name="b1", type="website", url_or_handle="https://b1.ua", origin_key="phraseB")]

    class _Harv:
        def harvest(self, candidates, cats, known, summary, known_hosts=None):
            return 2                      # examined first 2 (both phraseA), stopped before phraseB

    runner = _runner_with(search_pass=_SP(), harvester=_Harv())  # helper: build Runner with these
    runner.run_active()
    assert marked["ks"] == ["phraseA"]    # phraseB straddles the budget -> NOT marked
```

> `_runner_with` — construct a `Runner` (see `crawler/crawler/runner.py` `__init__`) with the fake search_pass + harvester and all other collaborators `None`, `api=_FakeApi([])`, `domain_feed=None`, etc. Reuse `FakeApi`/`_rl` already in `test_runner.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_runner.py -q -k fully_consumed --basetemp="$env:TEMP/pt5"`
Expected: FAIL — `KeyError: 'ks'` (run_active never calls `mark_harvested`)

- [ ] **Step 3: Wire the mark-back**

In `crawler/crawler/runner.py` `run_active`, capture the harvest return and mark fully-consumed phrases. Replace the `if candidates:` harvest block (line ~144) with:

```python
            if candidates:
                stop = self._harvester.harvest(candidates, cats, known, summary,
                                               known_hosts=known_hosts)
                self._mark_consumed_search_phrases(candidates, stop)
```

Add this helper method to `Runner` (near `run_active`):

```python
    def _mark_consumed_search_phrases(self, candidates, stop_index) -> None:
        """Mark a search phrase harvested only when ALL its candidates were examined
        (position < stop_index). Phrases straddling the fetch-budget stay unharvested
        so the next pass drains their remainder — no candidate is orphaned."""
        state = getattr(self._search_pass, "_state", None)
        if state is None or not hasattr(state, "mark_harvested"):
            return
        last_pos: dict[str, int] = {}
        for i, c in enumerate(candidates):
            key = getattr(c, "origin_key", None)
            if key is not None:
                last_pos[key] = i
        done = [k for k, pos in last_pos.items() if pos < stop_index]
        if done:
            state.mark_harvested(done)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_runner.py -q --basetemp="$env:TEMP/pt5b"`
Expected: PASS (all existing runner tests still pass — harvest return was previously ignored)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/runner.py crawler/tests/test_runner.py
git commit -m "feat(crawler): mark fully-consumed search phrases harvested after budget-bounded harvest"
```

---

### Task 6: End-to-end regression — no orphaning across a budget-cut

**Files:**
- Test: `crawler/tests/test_search_orphaning.py` (create)

**Interfaces:**
- Consumes: everything above — real `SearchState`, `SearchPass`, `Harvester`, `Runner`.

- [ ] **Step 1: Write the failing-then-passing regression test**

```python
# crawler/tests/test_search_orphaning.py
from crawler.discovery.search_state import SearchState
from crawler.discovery.search_pass import SearchPass
from crawler.models import SourceCandidate

def test_over_budget_candidates_survive_to_next_pass(tmp_path):
    st = SearchState(str(tmp_path / "s.json"), clock=lambda: 1000.0)
    # phrase P found 3 businesses last pass; the fetch budget only reached 1 of them.
    st.cache_put("P", [SourceCandidate(name=f"biz{i}", type="website",
                                       url_or_handle=f"https://biz{i}.ua") for i in range(3)])
    # pass 1: harvest consumed only the first candidate (stop_index=1) -> phrase NOT fully done
    last_pos = {}
    cands = [c for _, cs in st.unharvested(10_000) for c in cs]
    for i, c in enumerate(cands):
        last_pos[c.origin_key] = i
    done = [k for k, pos in last_pos.items() if pos < 1]   # stop_index = 1
    st.mark_harvested(done)
    assert done == []                                     # 3 candidates, only 1 examined
    # pass 2: the phrase is STILL unharvested -> its candidates re-surface (no re-search)
    assert [k for k, _ in st.unharvested(10_000)] == ["P"]
    assert len(st.unharvested(10_000)[0][1]) == 3
```

- [ ] **Step 2: Run it**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_search_orphaning.py -q --basetemp="$env:TEMP/pt6"`
Expected: PASS (this proves the invariant end-to-end; if it fails, an earlier task regressed)

- [ ] **Step 3: Full crawler suite**

Run: `./.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp="$env:TEMP/ptfull" -o addopts=""`
Expected: PASS (all)

- [ ] **Step 4: Commit**

```bash
git add crawler/tests/test_search_orphaning.py
git commit -m "test(crawler): regression — over-budget search candidates survive to next pass"
```

---

## Self-Review

**Spec coverage:** P1 (cache-fresh-at-search) → Tasks 2+4 (drain re-surfaces cached-unharvested; freshness untouched so no re-search). P2 (grid cursor) → unchanged by design (Task 4 rationale: cursor governs new-search only; drain handles the rest). P3 (budget starves search) → Task 3+5 (over-budget candidates are no longer orphaned; they drain next pass; search is no longer silently dropped). Back-compat → Task 2 legacy test. Every listed requirement maps to a task.

**Out of scope (sibling plan):** feed cursors P4/P5 (`brand_feed`/`osm_feed`/`aggregator_feed`/`site_query` advancing before harvest). They **recycle** every full rotation (bounded, not 168h), so they are a separate, lower-severity plan reusing this plan's `stop_index` primitive: each feed exposes `peek()`/`commit(n)` and run_active advances each feed's cursor only by the count of its candidates at positions `< stop_index`. Not implemented here.

**Placeholder scan:** none — every code step is concrete.

**Type consistency:** `origin_key: str | None` (Task 1) is read in Tasks 2/4/5; `unharvested(ttl) -> list[tuple[str, list[SourceCandidate]]]` (Task 2) consumed in Task 4; `harvest(...) -> int` (Task 3) consumed in Task 5; `mark_harvested(list[str])` (Task 2) called in Task 5. Consistent.

**Known remaining cost (documented, acceptable):** a phrase straddling the fetch-budget re-surfaces its *whole* candidate list next pass; already-fetched candidates from it are cheaply re-skipped by the harvest `known`/registry revisit-cooldown gates (no re-fetch, no re-offer). This trades a few idempotent gate-checks for zero orphaning — the correct trade given DDG is the scarce resource, not local gate checks.
