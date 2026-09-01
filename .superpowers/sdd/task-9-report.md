# Task 9 report: config + wiring — isolated sub-search harvester and phase

## Signatures matched (investigation before coding)

- `ActiveHarvester.__init__` (`crawler/discovery/harvest.py:53-62`): confirmed kwargs
  `(api, fetchers, extractor, rate_limiter, fetch_budget=20, walker=None,
  domain_rate_limiter=None, corpus_recorder=None, domain_registry=None,
  hardening_enabled=True, aggregator_min_outbound=3, aggregator_store=None,
  aggregator_max_domains=500, revisit_cooldown_seconds=0, geo_block_store=None,
  media_blocker=None, media_autoblock_crawls=2, lang_block_store=None,
  editorial_gate_enabled=True, source_hint_enabled=True, active_workers=1,
  executor_factory=None, relevance_gate=None, register_directory_host=None)`.
  It already exposes `take_directory_businesses()` and accepts
  `register_directory_host` (committed in Task 5/8) — matched verbatim.
- Main harvester construction site: `crawler/wiring.py:281-298` (was ending at
  `relevance_gate=relevance_gate)`) — added `register_directory_host=api.register_directory_host`.
- `search_pass.provider_for_site_query()` (`crawler/discovery/search_pass.py:189-194`)
  returns `plan.discovery` — an **`ActiveDiscovery`** instance
  (`crawler/discovery/active.py`), whose call shape is `.run(keywords: list[str],
  known: set, pages: dict|None) -> list[SourceCandidate]`, **not** a raw
  `provider(keyword, page)` callable as the brief's snippet assumed. `SubSearch.run`
  calls `self._search(keyword)` (single keyword, positional) — see
  `crawler/discovery/subsearch.py:resolve_business_site`. Adapted with a small wrapper
  in wiring:
  ```python
  def _subsearch_provider(keyword, _disc=site_discovery):
      return _disc.run([keyword], set())
  ```
  `known=set()` is deliberate: the isolated sub-search must not be filtered against
  the main crawl's already-known sources.
- `api_client.py:137` `register_directory_host(host)` — used as-is via
  `api.register_directory_host` (bound method).
- `Runner.run_active` (`crawler/runner.py:217-324`): `cats`, `known`, `summary` are
  all in scope for the whole method body (assigned before the `try:` at lines
  242/244/247/225 respectively) and remain in scope after
  `self._harvester.harvest(candidates, cats, known, summary, known_hosts=known_hosts)`
  inside the same `try` block — confirmed by reading the full method before editing.
  No blocker.

## Isolation grep

```
$ grep -n "domain_registry=None, aggregator_store=None" crawler/wiring.py
320:                domain_registry=None, aggregator_store=None,   # ISOLATION
```

Only one `ActiveHarvester(...)` call site in wiring.py passes `domain_registry=None,
aggregator_store=None` together — the isolated `iso_harvester` built for `SubSearch`.
The main harvester (line ~281) keeps the real `domain_registry`/`aggregator_store`
plus gets the new `register_directory_host=api.register_directory_host` kwarg. No
main-crawl store (registry, aggregator store, or the `corpus_recorder`, which was
also deliberately left out of the isolated harvester) is shared into `iso_harvester`.

## TDD

RED — `./.venv/Scripts/python.exe -m pytest tests/test_runner_subsearch.py -v`
(before implementation): 3 failures, `TypeError: Runner.__init__() got an
unexpected keyword argument 'subsearch'`.

GREEN — after implementing config/runner/wiring:
```
$ ./.venv/Scripts/python.exe -m pytest tests/test_runner_subsearch.py tests/test_runner_discovery.py -v
...
10 passed in 0.14s
```

Full crawler suite:
```
$ ./.venv/Scripts/python.exe -m pytest -q
994 passed in 151.69s (0:02:31)
```

`test_wiring.py` alone (34 tests, includes the sub-search wiring path via real
`build_runner` calls with `search_providers=["duckduckgo"]` configs):
```
$ ./.venv/Scripts/python.exe -m pytest tests/test_wiring.py -q
34 passed in 146.03s (0:02:26)
```

## Test file added

`crawler/tests/test_runner_subsearch.py` — three tests, built on the same
fake-harness style as `test_runner_discovery.py`:
1. `test_run_active_runs_subsearch_when_ddg_allowed` — main `FakeHarvester` seeded
   with `_directory_businesses`, `ddg_allowed=True` → `FakeSubSearch.run(...)` called
   with those businesses and `budget=15`.
2. `test_run_active_skips_subsearch_under_backoff` — same setup, `ddg_allowed=False`
   → `FakeSubSearch.ran_with is None` (phase skipped entirely).
3. `test_run_active_skips_subsearch_when_no_directory_businesses` (extra, not in the
   brief) — `ddg_allowed=True` but no directory businesses collected → subsearch not
   invoked, confirms the `if businesses:` guard.

## Files changed

- `crawler/crawler/config.py` — added `subsearch_enabled: bool = True`,
  `subsearch_search_budget: int = 15`, `subsearch_fetch_budget: int = 20` to
  `_RawSettings`, `Config`, and threaded through `from_settings`.
- `crawler/crawler/runner.py` — `Runner.__init__` gained `subsearch=None,
  subsearch_search_budget=15`, stored as `self._subsearch` /
  `self._subsearch_budget`. `run_active`, inside the existing `try` block, after the
  main `harvester.harvest(...)` call: if `ddg_allowed and self._subsearch is not None
  and self._harvester is not None`, pulls `self._harvester.take_directory_businesses()`
  and, if non-empty, calls `self._subsearch.run(businesses, cats, known, summary,
  budget=self._subsearch_budget)`.
- `crawler/crawler/wiring.py` — imports `SubSearch`; main `ActiveHarvester(...)` call
  gets `register_directory_host=api.register_directory_host`; new block after it
  builds `iso_harvester` (isolated `ActiveHarvester`, `domain_registry=None`,
  `aggregator_store=None`, `fetch_budget=config.subsearch_fetch_budget`, reusing
  `fetchers`/`extractor`/`rate_limiter`/`walker`/`domain_rl`/`geo_block_store`/
  `lang_block_store`/`relevance_gate`) and `subsearch = SubSearch(_subsearch_provider,
  iso_harvester)`, gated on `config.subsearch_enabled and search_pass is not None and
  site_discovery is not None`; `Runner(...)` call gets `subsearch=subsearch,
  subsearch_search_budget=config.subsearch_search_budget`.
- `crawler/tests/test_runner_subsearch.py` — new (see above).

## Self-review

- Isolation contract holds: grep confirms exactly one `ActiveHarvester(...)` call
  passes `domain_registry=None, aggregator_store=None` together, and it's the
  sub-search one; the main harvester's registry/aggregator-store wiring is untouched.
  Also deliberately did not pass `corpus_recorder` or `media_blocker` to the isolated
  harvester (both are main-crawl learning/state artifacts; `media_blocker` requires a
  `domain_registry` internally anyway).
- R3 backoff gate: `ddg_allowed` check sits at the very top of the sub-search block in
  `run_active`, mirroring the existing DDG due-walk / site: gates in the same method —
  under backoff the whole phase (including the `take_directory_businesses()` drain) is
  skipped, so directory businesses simply accumulate in the main harvester until a
  DDG-allowed pass runs.
- Budget cap: `self._subsearch_budget` (from `config.subsearch_search_budget`, default
  15) is threaded to `SubSearch.run(..., budget=...)`; `SubSearch.run` itself enforces
  `if searches >= budget: break` (existing Task 4 code, unmodified) — confirmed this
  cap is a *search-count* cap, not a candidate-count cap (dedup by lowercased business
  name happens first, then the budget gates actual searches).
- Backward compatibility: `subsearch=None` default on `Runner.__init__` means every
  existing `Runner(...)` construction (tests and any other caller) is unaffected;
  `self._subsearch is not None` guards the new phase so it's a true no-op when unset.
  `config.subsearch_enabled` (default `True`) gates the wiring build — setting it
  `False` in config means `subsearch stays None` and the phase never fires, no dead
  `iso_harvester` object built either (short-circuit `and`).
- Adapter correctness (the one place I deviated from the brief's exact code, since the
  brief's `provider_for_site_query()` return-shape assumption didn't match reality):
  wrapped `ActiveDiscovery.run([keyword], set())` as a `search(keyword)`-shaped
  callable. Verified against `crawler/discovery/subsearch.py`'s
  `resolve_business_site`, which calls `search(keyword)` and expects back a plain list
  of `SourceCandidate`-like objects with `.type`/`.url_or_handle` — `ActiveDiscovery.run`
  returns exactly that. `known=set()` is intentional (isolated pass, no cross-filtering
  against the main crawl's known sources) — documented inline in the wiring comment.
  This wrapper's `site_discovery` reference is captured **once at wiring/build time**
  (not re-resolved per pass), same as the existing static `discovery =
  search_pass.provider_for_site_query()` fallback line a few lines above it in
  `build_runner` — consistent with existing wiring style. A live pass-to-pass health
  swap (SearXNG failover) isn't picked up by the sub-search leg, but since the whole
  phase is skipped whenever `ddg_allowed=False` (global backoff) anyway, this is a
  minor edge case, not a correctness bug for R3's stated requirement.
- No changes needed to `SubSearch`/`ActiveHarvester`/`api_client.py` — all three were
  already correct/complete from prior tasks (4, 5, 8) and matched the brief's
  interfaces exactly except for the `provider_for_site_query()` return shape noted
  above.

## Concerns

- The isolated `iso_harvester` is built whenever `search_pass is not None` and a site
  discovery provider is available — independent of whether the **main** `harvester`
  itself got built (it needs `active_fetch_budget > 0` and at least one feed). If the
  main harvester ends up `None`, `subsearch` is still constructed but simply never
  invoked (`run_active` returns early when `self._harvester is None`). Harmless
  (construction does no I/O), just a small amount of wasted object construction in
  that edge configuration — not worth an extra guard given existing wiring style
  tolerates similar minor waste elsewhere (e.g., `discovery` fallback var built even
  when unused in the `ddg_allowed` site-leg branch).
- Sub-search's own internal error handling is unchanged Task-4 code (each business
  resolve is wrapped in `try/except` inside `SubSearch.run`), so nothing new to review
  there.

## Final-review defect fix: memory leak under backoff

**Issue**: The sub-search phase gated the entire block (including queue drain) on three conditions:
`ddg_allowed and self._subsearch is not None and self._harvester is not None`. During persistent
DDG backoff (ddg_allowed=False) or when subsearch provider is unavailable, `take_directory_businesses()`
was never called, so the queue grew unbounded for the lifetime of the long-running crawler loop.

**Fix** (commit `39efe5f`):
- Moved `take_directory_businesses()` outside the DDG guard — drain happens unconditionally
  whenever harvester exists (`if self._harvester is not None`).
- Gate ONLY the `.run()` call: `if businesses and ddg_allowed and self._subsearch is not None`.
- Draining-and-discarding under backoff is correct (per-run "forget" semantics, no persistence).

**Test coverage**: Updated `test_runner_subsearch.py`:
- `test_run_active_skips_subsearch_under_backoff` — now verifies queue is drained even
  when subsearch is skipped: `assert main_hv._directory_businesses == []` after run with
  `ddg_allowed=False`.
- Added `test_run_active_drains_queue_when_no_subsearch_provider` — verifies queue drains
  when provider is `None` (subsearch=None constructor param).
- Updated `_RecordingHarvester` test double in `test_runner.py` to implement
  `take_directory_businesses()` (returns `[]`), fixing 2 pre-existing test failures.

**Test results**:
```
$ ./.venv/Scripts/python.exe -m pytest tests/test_runner_subsearch.py -v
tests/test_runner_subsearch.py::test_run_active_runs_subsearch_when_ddg_allowed PASSED
tests/test_runner_subsearch.py::test_run_active_skips_subsearch_under_backoff PASSED
tests/test_runner_subsearch.py::test_run_active_skips_subsearch_when_no_directory_businesses PASSED
tests/test_runner_subsearch.py::test_run_active_drains_queue_when_no_subsearch_provider PASSED
4 passed in 0.13s

$ ./.venv/Scripts/python.exe -m pytest -q
995 passed in 157.04s (0:02:37)
```

**Files changed**: `crawler/crawler/runner.py`, `crawler/tests/test_runner.py` (1 line),
`crawler/tests/test_runner_subsearch.py` (3 new tests + 1 assertion added to existing test).
