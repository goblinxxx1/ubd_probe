# Crawler cleanup minors — design spec

**Date:** 2026-07-23
**Branch:** `feat/crawler-cleanup-minors` (from `main`)
**Scope:** crawler-only. No backend, no admin, no frontend, no DB. MySQL not required.
**Test gate:** crawler suite (`cd crawler && ./.venv/Scripts/python.exe -m pytest -q`), baseline **350** passing.

## Goal

Retire six accumulated, non-blocking tech-debt items surfaced by prior review waves (mainly the attribution-hardening final review and the domain-rating deferred list), in one coherent cleanup track. Each item is small and independently testable. No new feature behavior is introduced except where a config knob is wired to already-documented intent (item A) and a schema-type matcher is broadened (item B) — both byte-safe at their defaults / guarded against precision regressions.

## Non-goals (explicitly excluded, with reason)

- **Telegram `site_name=None` relevance-gate recall gap** — by-design recall behavior ([[ubd-crawler-precision]] deferred Minor); changing it is a recall feature, not cleanup.
- **`build_page_ctx` computing `outbound_host_count` when hardening is off** — negligible micro-optimization; with item A the value is consumed anyway.
- **domain-rating cosmetics** (`_EMPTY` deep-copy idioms, `cand` naming echo in runner, `registry.record()` outside per-candidate try) — pure cosmetic, no correctness value.
- **Pure duplicative coverage tests** (keyless-401 on GET, non-pending exclusion assert, signals-untouched-after-approve, etc.) — marginal value; not worth the churn.

## Global constraints

- Live moderation gate untouched; deterministic core intact.
- Every item lands via TDD (failing test first) and keeps the full crawler suite green.
- Byte-safe defaults: items A and D must not change behavior for the live input shapes (URLs with a scheme, no port) at their defaults.

---

## Item A — wire `AGGREGATOR_MIN_OUTBOUND` into the live gate

**Problem:** `config.aggregator_min_outbound` (default 3) reaches only the offline `run_host_miner`. The live gate calls `attribute(item, ctx, hardening_enabled=…)` at `crawler/crawler/discovery/harvest.py:91` with the hardcoded default `aggregator_min_outbound=3`. RUN.md implies the env knob governs the live aggregator threshold; today it does not. Flagged Minor in the attribution-hardening final review.

**Change:**
- `ActiveHarvester.__init__` gains `aggregator_min_outbound: int = 3` (default keeps every existing caller/test byte-identical), stored as `self._aggregator_min_outbound`.
- `harvest.py:91` passes `aggregator_min_outbound=self._aggregator_min_outbound` into the `attribute(...)` call.
- `crawler/crawler/wiring.py` passes `config.aggregator_min_outbound` when constructing `ActiveHarvester` (mirroring how `hardening_enabled` is threaded).

**Test:** an `ActiveHarvester` built with a non-default threshold classifies a page whose outbound count sits between the default and the configured value as media/non-media accordingly — proving the configured value (not the hardcoded 3) drives the live classification. Default path unchanged.

**Files:** `harvest.py`, `wiring.py`, `tests/test_active_harvest.py` (+ `tests/test_wiring.py` if wiring is asserted there).

---

## Item B — broaden `_ARTICLE_TYPE` to catch `*Article` subtypes + `Report`

**Problem:** `crawler/crawler/fetchers/website.py:124` `_ARTICLE_TYPE = …(?:NewsArticle|BlogPosting|LiveBlogPosting|\bArticle\b)`. The trailing `\bArticle\b` does not match `TechArticle`/`ScholarlyArticle` (no word boundary between `Tech` and `Article`), and `Report` is not covered. Article detection under-fires for these schema.org subtypes.

**Change:** replace `\bArticle\b` with a plain `Article` substring (which subsumes `TechArticle`, `ScholarlyArticle`, and the already-listed `NewsArticle`) and add `Report`:
`…(?:NewsArticle|BlogPosting|LiveBlogPosting|Report|Article)`.

**Precision note:** `is_media = is_blocked_host OR (is_article AND NOT has_business_schema) OR outbound≥thresh`. A page carrying a physical-business schema (`LocalBusiness`/`Store`/`Restaurant`/`CafeOrCoffeeShop`) is still protected regardless of an Article/Report type, so the broadened matcher cannot re-classify a schema-tagged business page as media. Residual risk (an Article/Report page with no business schema) is the intended catch.

**Test:** positive detection for `TechArticle` and `Report`; existing positives (`NewsArticle`) and the `LocalBusiness`→business-not-article case stay green.

**Files:** `website.py`, `tests/test_website_fetcher.py`.

---

## Item C — `int(outbound_hosts)` None-guard in `host_miner`

**Problem:** `crawler/crawler/learn/host_miner.py` does `int(r.get("outbound_hosts", 0))` in two spots; an explicit `outbound_hosts=None` in a row raises `TypeError`. Task-4 corpus always writes an int, so this is latent, but the miner also consumes hand-built/legacy rows.

**Change:** `int(r.get("outbound_hosts") or 0)` in both spots.

**Test:** a row with `outbound_hosts=None` is aggregated without raising (treated as 0).

**Files:** `host_miner.py`, `tests/test_host_miner.py`.

---

## Item D — consolidate the bare-host normalization idiom (main item)

**Problem:** the bare-host derivation is copy-pasted across the crawler in three semantic variants:
- **Plain** `urlsplit(url or "").netloc.lower().removeprefix("www.")` — `attribution._host` (→`None` on empty), `labeler._host` (→`""`), `corpus._outbound_count` (inline, ×2), `extract/heuristic.py` (inline, ×2), `discovery/providers.py` (inline), and the bare-string form `h.strip().lower().removeprefix("www.")` in `blocklist` (×2) and `host_vetoes` (protected set).
- **Thorough** — `brand_feed._host` and `walker._host` additionally strip userinfo (`@`) and port (`:`).
- **Dual-mode** — `run_host_miner._bare_host` prepends `//` so scheme-less inputs also resolve (added by the attribution fix wave).

**Design:** one shared helper `crawler/crawler/util/hosts.py::bare_host(value: str | None) -> str` implemented as the **thorough + dual-mode superset**: prepend `//` when the value has no scheme, take `urlsplit(...).netloc`, strip userinfo and port, lowercase, strip a leading `www.`, return `""` on empty/invalid.

**Why the superset is safe:** for the live input shape (a URL with a scheme and no port), the superset returns a byte-identical result to every existing variant. It differs only by (a) also stripping ports/userinfo — strictly more correct, and (b) resolving scheme-less inputs to their host instead of `""` — which is exactly what the bare-string call sites (`blocklist`, `host_vetoes`, `run_host_miner`) already relied on.

**Call-site contract preservation:** each module keeps its current return contract via a thin wrapper, not by changing consumers:
- `attribution._host`, `brand_feed._host` → `return bare_host(url) or None` (preserve `str | None`).
- `labeler._host`, `walker._host` → `return bare_host(url)` (preserve `str`).
- inline idioms (`corpus`, `heuristic`, `providers`) and bare-string idioms (`blocklist`, `host_vetoes`) → call `bare_host(...)` directly.
- `run_host_miner._bare_host` → delegate to `bare_host` (or replace usages).

**Acceptance:** the full crawler suite (350) stays green with zero behavioral test changes. If any existing test encodes port-bearing or scheme-less-returns-`""` behavior, that is a real semantic conflict to surface (not silently override).

**Tests:** dedicated `tests/test_hosts.py` for `bare_host`: scheme'd URL, `www.` strip, port strip, userinfo strip, scheme-less input, empty/`None`→`""`.

**Files:** new `crawler/crawler/util/hosts.py` (+ `util/__init__.py` if the package doesn't exist), `attribution.py`, `brand_feed.py`, `labeler.py`, `walker.py`, `corpus.py`, `extract/heuristic.py`, `discovery/providers.py`, `blocklist.py`, `host_vetoes.py`, `learn/run_host_miner.py`, new `tests/test_hosts.py`.

---

## Item E — move mid-file import to the top in `test_blocklist.py`

**Problem:** the attribution track added a module-level import mid-file in `crawler/tests/test_blocklist.py` (cosmetic, flagged Task-3 Minor).

**Change:** move it into the top import block. No behavior change; covered by the existing `test_blocklist` suite.

**Files:** `crawler/tests/test_blocklist.py`.

---

## Item F — tie-break test for `DomainRegistry.top()`

**Problem:** `DomainRegistry.top()` sorts by `(-score, host)` but the host tiebreaker on equal scores is untested (domain-rating deferred Minor).

**Change:** add a test with two hosts of equal score asserting deterministic ordering by host. Test-only; no production change.

**Files:** the domain-registry test module (`tests/test_domain_registry.py` or wherever `DomainRegistry` is tested).

---

## Sequencing

Independent items, each its own TDD task. Suggested order: E (trivial) → C → B → A → F → D (D last, as the broadest change, so earlier items are already settled). Item D is the only cross-module refactor; all others touch 1–2 files.

## Testing

Per-item TDD (failing test first) + full crawler suite green after each. Final gate: full crawler suite (≥ 350 + new tests), no regressions. No backend/admin/frontend suites involved.
