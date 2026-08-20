# Crawler: query-miner v2 — eager recall + hard reject-exclude — Track A2.v2

**Date:** 2026-08-20
**Status:** Design approved
**Program:** self-learning query loop. Builds on A2 (axis-veto, [[ubd-crawler-query-miner-precision]])
and A1 (admin audit surface, [[ubd-crawler-query-miner-audit-loop]]).
See [[ubd-crawler-query-miner-audience-bug]].

## Problem (verify-by-execution)

The self-learning grid barely grows: a live run of the miner over the production corpus
(832 rows) surfaces only **4 survivors** (`імплантація, зуби, проживання, відпочинок`),
while real services drown below threshold. Root causes, each proven by running the miner:

1. **The contrast is degenerate.** The corpus is **100 % `pass`, 0 `fail`, all
   `snowball=True`** — every row comes from the bootstrap/snowball path; the live-harvest
   FAIL path (`record(item, cand is not None)`) never lands. So `mine()`'s PASS-vs-FAIL
   log-odds has no negative side: `y_fail` is empty, `z` compresses to ~1.0, and generic
   nouns (`грн, день, під, рок, вид, період`) score as high as real services
   (`лікування` z=0.78, `діагностик` z=0.57, `відбілювання` z=0.41). Ranking by `z` is
   noise.
2. **The domain-support floor blocks single-host services.** `query_miner_min_domain_support=3`
   requires a term on ≥3 distinct hosts. A whitening service on one dental site
   (`відбілювання` nh=1) can **never** surface until a 2nd business of that category enters
   the catalog. This defeats eager recall — the moderator wants category terms **now**.
3. **The per-run cap silently caps recall.** `query_miner_max_candidates_per_run=50` sends
   only the top-50 by (degenerate) `z`. Worse: admin-**rejected** terms are re-mined every
   run (the crawler only pulls *approved* terms back, never *rejected*), so rejected
   generics keep occupying cap slots and block deeper real terms from ever reaching the
   moderator.

### What the corpus actually is (why IDF/SetExpan were rejected)

The 48 `pass` hosts are **the already-approved businesses re-crawled** (dentalstudio,
whiteclinic, megaoptika, planetakino, mate.academy, …), dominated by whoever has the most
pages (5 hosts × 40 rows = the per-host cap). Consequences, proven by prototype:

- **IDF-over-hosts is the wrong tool here.** After per-host dedup, support = host count
  `nh`, and `IDF = log(48/nh)` is its inverse — they fight. IDF rewards single-host
  overfit (top-IDF = `матрац, подушка, мужність` — one shop / eligibility boilerplate) and
  does **not** kill generics because they are not host-saturated on 48 hosts (`грн` nh=3).
  Dropped.
- **SetExpan / distributional similarity** on 48 hosts is noise. Dropped (YAGNI).
- **External frequency file** carries a Russian-contamination + maintenance cost. Dropped.

Prototype (rank by cross-host support, no IDF) cleanly sinks single-host boilerplate and
floats category terms — this is the signal we use.

## Goal

Eager recall into the human audit queue: surface category/service terms **immediately**
(including single-host ones), auto-filter only the *obviously* junk, and let the moderator
be the precision gate. Approved terms already feed the grid unlimited; rejected terms must
become a **hard exclude** the crawler respects until the moderator un-blocks them.

**Non-goals:** the admin audit UI itself (A1, unchanged); `compose_service_terms` /
grid-feed (unchanged — approved already unlimited); the soft CLI `query_stoplist` module
(left intact for back-compat, superseded in the admin path).

## Design

Four localized, additive changes. Everything stays behind the human audit gate — it cannot
alter the live grid.

### 1. Ranking: cross-host support, not degenerate `z`

`survivors()` already receives `TermScore.domains` (the PASS host-set, `miner.py:34`) and
already gates on `min_domains`. v2 changes the **sort key** and the **floor**:

- **Sort** by `len({d for d in domains if d})` descending, tiebreak by `pass_count`
  descending, then term (stable). Replaces `-z` ordering.
- `z` stays **computed and stored** on `TermScore`/the candidate (observability + a future
  FAIL-corpus enhancement), but is **not** in the sort key and **no longer gates** — the
  degenerate `z` must neither rank nor filter. The `min_z` gate is removed.

### 2. Floor: surface single-host terms + hapax guard

- `query_miner_min_domain_support`: default **3 → 1** (surface single-host category terms
  immediately). The config key is kept; only the default changes.
- Add an anti-typo **hapax guard**: drop terms with `pass_count < query_miner_min_pass_docs`
  (new config, default **2**) — a term seen in ≥2 offer pages, even on one host. This is a
  *document* floor (pages), distinct from the *host* floor above (`min_domain_support`), so
  it keeps `відбілювання` (many dental pages, 1 host) while dropping one-off tokenizer noise.

### 3. Cap: send everything (bounded by a safety valve)

- `query_miner_max_candidates_per_run`: default **50 → 0** meaning *unlimited* (mirrors the
  `query_lexicon_max_terms=0` convention). `survivors()` treats `<=0` as no cap. A generous
  hard safety ceiling of 1000 stays in code to avoid a pathological unbounded submit.
- The moderator receives all non-junk candidates at once (the user's "все зразу").

### 4. Reject = hard exclude (backend-driven)

The backend `query_terms` table is already the persistent reject memory
(`upsert_candidates`: "approved/rejected rows are left untouched", `query_term.py:13`).
v2 makes the crawler **read** that memory and exclude rejected terms from mining:

- **Backend** — new internal endpoint `GET /api/internal/query-terms/rejected` mirroring
  `/approved` (`list_rejected_terms` in `crud/query_term.py`, route in `routers/internal.py`).
- **Crawler** — `api_client.list_rejected_query_terms()` mirroring
  `list_approved_query_terms()`.
- **`run_query_miner`** — fetch the rejected set and drop any candidate whose term is in it,
  **before** ranking/cap. Hard exclude, no soft resurface (matches the moderator's mental
  model: blocked stays blocked until un-blocked via the admin UI). The soft
  `query_stoplist` (z-resurface) module is untouched and still applied — it only ever
  affected the dormant CLI path, so keeping it is a no-op for the admin loop.
  - Wiring: `run_query_miner` currently has no API handle. It runs from the runner
    (`_submit_query_candidates`) which does have `self._api`. The rejected set is fetched by
    the runner and passed into `run_query_miner(config, rejected_terms=...)` (default
    `()` — keeps the CLI entry point and tests working without a backend).

### 5. Auto-veto: close the observed junk leaks

Extend `axis_veto._NON_SERVICE` (and ensure audience coverage) with the generics and
eligibility-boilerplate the prototype surfaced — the *systematic* recurring noise, not
borderline terms (those go to the human):

- **Generics:** `грн, день, рік, вид, під, форма, статус, місце, том, комплекс, період,
  пора, час, раз, сума, розмір, кількість` (all verified as noise in the live top-50).
- **Eligibility boilerplate:** `мужність, відданість, службовець, воїн, звитяга, подвиг,
  вдячність` + **close the `ветеран/ветеранка` leak** (the feminine lemma escaped
  `AUDIENCE_FORMS`).
- Conservative by design: only obvious junk. Anything category-ish (`консультація,
  діагностик, обстеження, чистка, курс, обладнання`) is left for the moderator, per the
  eager-recall intent.

## Track 3 constraints (recorded so the SERP-pagination track stays consistent)

v2 grows the grid (more approved services → bigger `{service}{audience}`). This does **not**
break Track 3's existing machinery — `set_grid` wraps modulo the new length
(`search_pass.py:25`) and the cache/freshness is phrase-keyed (`is_fresh(kw)`,
`search_state.py:161`), both resilient to grid changes. But v2 (breadth) and Track 3
(depth-per-phrase) share one budget and one `grid_cursor`, so Track 3 **must**:

1. Key its per-phrase **page cursor by the phrase string** (like the cache), never by the
   positional `grid_cursor` index.
2. Advance pages **yield-driven** (paginate while a phrase harvests new businesses; stop
   when dry) with a page-cap ≈ 3 — not by rotation cadence.
3. Make freshness key on **(phrase, page)**, else a phrase stays "fresh" for the 168 h TTL
   and never advances to page 2.

## Impact / blast radius

- **Additive, byte-eq when OFF:** with defaults unchanged a caller sees identical behavior;
  the new behavior is the changed defaults + the new rejected-exclude (which is empty
  `()` unless a backend supplies rejects).
- **Tests:** no existing test breaks. `test_run_query_miner` (стоматологія/known/veto)
  still passes (PASS-row mining, `known`-exclude kept, veto only extended); the soft
  `query_stoplist` module and its 8 tests are untouched. New tests: support-ranking order,
  floor=1 surfaces single-host, hapax guard drops `pass_count=1`, rejected-exclude drops a
  rejected term, `ветеранка` vetoed, cap=0 = unlimited. Backend: `list_rejected_terms` +
  route test.
- **UKR-only:** all veto additions are Ukrainian lemmas; no Russian anywhere.

## Rollout

Docker-only. Backend rebuild (new endpoint), crawler rebuild (miner + api_client + config).
No migration (uses existing `query_terms` table/statuses). No grid-feed change.

## Tasks (SDD, checkpoint after each)

1. **Backend** — `list_rejected_terms` crud + `GET /api/internal/query-terms/rejected`
   route + test.
2. **Crawler api_client** — `list_rejected_query_terms()` + test.
3. **axis_veto** — extend generics + boilerplate, close `ветеран/ветеранка` leak + test.
4. **run_query_miner + survivors + config** — support-ranking, floor 3→1, hapax guard,
   cap=0-unlimited, rejected-exclude param; runner passes the rejected set + tests.
5. **Verify-by-execution** — rerun the live-corpus prototype through the real pipeline;
   confirm the audit queue matches the approved design. Update memory.
