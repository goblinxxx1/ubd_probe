# Crawler Query-Grid Design (self-growing discovery — v1)

**Date:** 2026-07-21
**Status:** approved (brainstorm) → pending implementation plan
**Track:** first sub-project of "self-growing discovery" (see memory `ubd-crawler-discovery-scaling-brainstorm`).

## Problem

Active discovery queries a **static hand-written list of ~40 phrases** in `SEARCH_KEYWORDS` (`crawler/.env`). Recall is bounded by that list: it never grows, and each pass re-queries largely the same phrases. This is the crawler's single biggest discovery bottleneck.

## Goal (v1 scope)

Replace the static keyword list with a **query grid generated from curated vocabulary axes**, sampled deterministically across passes so it stays within the DDG throttling budget. This is the smallest self-contained slice: no new DB schema, no external data source (OSM), no domain spidering, no LLM.

### Explicitly OUT of v1 (later sub-projects)
- `{intent}{audience}{vertical}` template (needs prioritization to be worth the size).
- Yield-based prioritization / bandit (queries reinforced by conversion).
- Snowball vocabulary mining from found offers.
- Brand → domain → sitemap crawling (the brand *list* is used here only for `{brand}{audience}` DDG queries).
- Cities as a query axis (they stay in `geo.py` for location extraction only).
- Automatic morphology generation and negative-dictionary auto-population.

## Architecture

All changes live in `crawler/`. One new module plus a thin wiring change; extraction/attribution untouched.

### Components

**1. `crawler/crawler/discovery/query_grid.py`** — curated vocabulary + generator (same pattern as `lexicon.py`/`geo.py`: curated Python, deterministic, unit-tested).

- `AUDIENCE_FORMS: tuple[str, ...]` — audience surface phrases (from the 27 curated forms).
- `INTENT_FORMS: tuple[str, ...]` — concrete discount-type surface phrases (abstract/gov-heavy program terms excluded).
- `BRANDS: tuple[str, ...]` — brand names (retail/fuel/pharmacy/tech/clothing/banks/post/telecom).
- `build_grid() -> list[str]` — generates `f"{intent} {audience}"` for every intent×audience, plus `f"{brand} {audience}"` for every brand×audience; lower-cased dedup; **stable deterministic order** (grid[i] is fixed for a given vocabulary).

**2. `QueryGrid` (in the same module)** — deterministic rotation over the grid.

- Holds the full ordered grid (from `build_grid()`).
- `next_batch(n: int, cursor: int) -> tuple[list[str], int]` — returns `n` queries starting at `cursor`, wrapping around the end, and the new cursor (`(cursor + n) % len(grid)`). Full coverage across passes, no repeats until a full cycle completes.

### State

The rotation cursor persists in the existing `search_state.json` (`SEARCH_STATE_PATH`, managed by `discovery/search_state.py`) as a new integer field `grid_cursor` (default 0). No new storage.

### Config

New setting `search_queries_per_pass: int` (env `SEARCH_QUERIES_PER_PASS`, default **40**) — the batch size `n` and the **primary throttling knob**: DDG result-fetches per pass ≈ `n × SEARCH_RESULTS_PER_KEYWORD`, so the default keeps the DDG footprint at roughly today's level.

### Data flow

```
build_grid()  (once per process, deterministic)
   → QueryGrid holds the full ordered list
per pass:
   load grid_cursor from search_state
   → QueryGrid.next_batch(search_queries_per_pass, grid_cursor)
   → advance + persist grid_cursor
   → batch  ∪  static SEARCH_KEYWORDS (manual pins; deduped; may be empty)
   → ActiveDiscovery.run(keywords, known)  → DDG → candidates → ActiveHarvester
```

### Wiring

The per-pass keyword slice is assembled where the runner obtains its keywords (currently `config.search_keywords` fed to `Runner`/`ActiveDiscovery`). The generated batch is **unioned with any static `SEARCH_KEYWORDS`** (backward compatible: a non-empty `SEARCH_KEYWORDS` still contributes as manual pins; an empty one makes the grid the sole source). Cursor read/advance/persist happens once per pass via the existing search-state read/write path.

## Backward compatibility

- If `SEARCH_KEYWORDS` is set, its phrases are unioned into every batch (pins survive).
- If `search_state.json` has no `grid_cursor`, it defaults to 0.
- No schema, endpoint, UI, or extraction change; the precision gates downstream are unchanged and remain the safety net for the broader (noisier) candidate inflow.

## Error handling

- `build_grid()` is pure and total; empty/whitespace vocabulary entries are skipped.
- `next_batch(n, cursor)` clamps `n` to `[1, len(grid)]` and treats an out-of-range or missing cursor as 0 (self-heals a corrupted state file).
- Discovery failures are already isolated per pass in `runner.py` (`active discovery failed: ...`); the grid change does not alter that.

## Testing (offline, deterministic — `cd crawler && ./.venv/Scripts/python.exe -m pytest -q`)

- `build_grid`: count equals `len(INTENT_FORMS)*len(AUDIENCE_FORMS) + len(BRANDS)*len(AUDIENCE_FORMS)` minus exact duplicates; no empty strings; stable order across calls; templates present (`"знижка військові"`, `"OKKO ветерани"`-style).
- `QueryGrid.next_batch`: advances cursor by `n`; wraps at the end; two successive non-overlapping batches cover distinct queries; a full sweep visits every query exactly once before repeating; deterministic for a given cursor.
- cursor clamping: out-of-range/negative/missing cursor → treated as 0.
- union: batch ∪ `SEARCH_KEYWORDS` deduplicates.

## Curated vocabulary (v1)

**AUDIENCE_FORMS (27):** військові, військовослужбовці, військові ЗСУ, ЗСУ, чинні військові, мобілізовані, контрактники, резервісти, ветерани, ветеран, ветеран війни, ветерани АТО, ветерани ООС, УБД, учасники бойових дій, особи з інвалідністю внаслідок війни, родини військових, дружини військових, діти військових, сім'ї УБД, сім'ї загиблих Захисників, члени сімей полеглих, поліцейські, ДСНС, прикордонники, ТРО, Нацгвардія.

**INTENT_FORMS (13):** знижка, безкоштовно, акція, спеціальна пропозиція, бонус, подарунок, кешбек, промокод, сертифікат, компенсація, ваучер, спеціальна ціна, пільгова ціна.
*(Excluded as gov/NGO-noise and not recognised by the discount extractor: грант, партнерська програма, програма підтримки, клубна програма, соціальна програма.)*

**BRANDS (48):** Rozetka, Comfy, Фокстрот, Епіцентр, Нова Лінія, JYSK, EVA, Prostor, Аврора, Копійочка, Сільпо, АТБ, Novus, VARUS, Metro, OKKO, WOG, UPG, SOCAR, БРСМ, KLO, Parallel, Подорожник, АНЦ, Бажаємо здоров'я, Аптека Доброго Дня, Алло, Цитрус, MOYO, Brain, Eldorado, INTERTOP, Colin's, LC Waikiki, Adidas, Puma, New Balance, Megasport, ПриватБанк, monobank, Ощадбанк, ПУМБ, Sense Bank, Райффайзен Банк, Нова пошта, Київстар, Vodafone, lifecell.

Grid size ≈ `13×27 + 48×27 = 351 + 1296 = 1647` queries (after dedup) — cyclable at 40/pass.

## Open questions

None blocking. Vocabulary is curated in-module and can be extended in later passes; the generator and rotation are stable regardless of list size.
