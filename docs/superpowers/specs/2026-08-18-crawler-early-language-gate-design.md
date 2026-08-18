# Crawler: early domain-level language gate (A+B)

**Date:** 2026-08-18
**Status:** Design approved (LangBlockStore local variant)
**Track:** foreign-language site budget leak (justcolor.net class)

## Problem

Foreign-language content sites with large sitemaps burn crawl budget **before** the
existing language gate can stop them, and recur every cycle because nothing blocks
them persistently.

### Evidence (justcolor.net, live logs 2026-08-18)

- Not an offer leak: absent from `offers`, `sources`, `suggested_sources`, `blocked_hosts`.
- The waste is at the **walker/sitemap stage**:
  `robots.txt` → `sitemap_index.xml` → **20+ sub-sitemaps** (`coloringpages-sitemap-1..63`),
  each ~3 s polite delay = minutes and dozens of HTTP requests, **then** the first
  content page (`/enfants/thematiques/police/…`, French) finally trips
  `is_non_ukrainian` → `break`.
- The only language gate is `is_non_ukrainian` in `_harvest_one`
  (`crawler/discovery/harvest.py:135`), on **already-fetched content**, i.e. **after**
  `DomainWalker.walk()` has enumerated the whole sitemap tree.
- `break` abandons the domain but does **not** block it → justcolor.net has no
  `blocked_hosts` row → re-walked next cycle from scratch.

### Why the existing gates leak

- `is_foreign_host`: `.net` is a gTLD (UA businesses use it too) → passes.
- content language gate: fires, but only after the sitemap budget is already spent.

### Cheap early signal exists (verified via curl on root)

- `<html lang="en-US">`
- hreflang alternates: `en, fr, es, it, de, pt, zh, ja, x-default` — **no `uk`/`ua`**.

**Caveat from research:** search engines do not trust `<html lang>` alone (sites lie;
Google detects language from content — [Google docs](https://developers.google.com/search/docs/specialty/international/localized-versions),
[ahrefs](https://ahrefs.com/blog/hreflang)). So `lang` is a supporting signal, not a
verdict; the trustworthy signal is the **content Cyrillic ratio**, with hreflang used
only to confirm no Ukrainian version exists.

## Goals

1. Abandon a foreign-language domain **before** enumerating its sitemap (stop the waste
   on first contact).
2. **Persistently** block the host so it never re-walks (survives process restart).
3. Zero regression for legitimate Ukrainian sites (conservative rule).

Non-goal: replacing the content-level `is_non_ukrainian` gate — it stays as a backstop.

## Design (A + B, shared LangBlockStore)

### Shared component — `LangBlockStore` (new)

`crawler/discovery/lang_block.py`, a direct mirror of
`crawler/discovery/geo_block.py`:

- Local `/data/lang_blocked_hosts.json` (no backend dependency), like the RU/BY geo store.
- `load()` and every `add()` push the set into `discovery.blocklist` (via a
  `blocklist.reload_lang_blocked(...)` registry slot, mirroring `reload_geo_blocked`) so
  `is_blocked_host` respects it everywhere (harvest pre-fetch gate, walk, feeds,
  attribution) immediately and on subsequent runs.
- Semantics = geo: a crawler policy ("we crawl Ukraine only"), not a moderator-facing
  behavioral block — so it stays out of the admin `blocked_hosts` table to avoid
  auto-noise there.

Both A and B write to this one store.

### A — early root gate (in `DomainWalker.walk()`, before `collect_sitemap_urls`)

At the start of `walk()`, after resolving `domain` and robots, fetch the homepage HTML
once (reuse `self._client`, already used by `_bfs`) and evaluate:

```
root_text   = visible text of homepage
hreflang    = set of hreflang codes parsed from <link rel="alternate" hreflang=...>
foreign     = is_non_ukrainian(root_text)  AND  not ({"uk","ua"} ∩ hreflang_langs)
```

- Decision is driven by the **reliable content signal** `is_non_ukrainian(root_text)`;
  hreflang only vetoes the block when a Ukrainian alternate exists. `<html lang>` is
  informational (logged), never sufficient on its own — sidesteps the "lang lies" problem.
- If `foreign` → return `WalkPlan(domain, urls=[], crawl_delay=delay, foreign=True)`
  **without** calling `collect_sitemap_urls` or `_bfs`.
- Else proceed exactly as today (`foreign=False`).
- Thin/JS-rendered root (root_text under `min_alpha=15`) → `is_non_ukrainian` False →
  `foreign` False → **not** blocked (deliberately conservative; B still covers it later).
- On any fetch/parse error → `foreign=False` (never block on uncertainty).

`WalkPlan` gains a `foreign: bool = False` field.

### Block wiring (in `ActiveHarvester`)

`ActiveHarvester` gains `lang_block_store=None` (constructor + wiring), mirroring the
existing `geo_block_store` injection.

- **A:** `_plan` already calls `walk()`. Surface `plan.foreign` up to `_harvest_one`
  (return the plan / add to the returned tuple). When `foreign` and
  `lang_block_store is not None`: `lang_block_store.add(host)`; skip all page
  processing; return `structural=False`. (Symmetric to the RU/BY handling at
  `harvest.py:58-61`.)
- **B:** at the existing content gate (`harvest.py:135`), when `is_non_ukrainian(...)`
  trips during page walk, also `lang_block_store.add(host)` before `break`.

Once added, the runtime blocklist means the domain is skipped by the `is_blocked_host`
pre-fetch gate on the very next candidate, and by `load()` on future runs.

### Config

- `lang_gate_enabled: bool = True` — single kill-switch. When off, the `LangBlockStore`
  is not wired (passed as `None`): A does not run its root gate, and B's `add()` is a
  no-op guarded by `lang_block_store is not None`. When on, both A and B are active.
- `lang_blocked_hosts_path: str = "/data/lang_blocked_hosts.json"`.
- Thresholds reuse `is_non_ukrainian` defaults (`min_ratio=0.3`, `min_alpha=15`).

## Data flow (per active candidate)

```
harvest() pre-fetch gates (incl. is_blocked_host → now catches lang-blocked hosts)
  → _plan → walker.walk()
       ├─ fetch homepage, parse hreflang + text
       ├─ foreign? → WalkPlan(urls=[], foreign=True)         [A]
       └─ else → sitemap/BFS as today
  → _harvest_one
       ├─ plan.foreign → lang_block_store.add(host); return  [A]
       └─ per page: is_non_ukrainian → lang_block_store.add(host); break  [B]
```

## Blast radius

- `walk()` adds **+1 root fetch per walked domain**. For UA sites this is the homepage
  we would fetch anyway; for a foreign site it saves 20+ sitemap requests. Net win.
- New module `lang_block.py`; one new `blocklist` registry slot; `WalkPlan.foreign`;
  `ActiveHarvester` gains one dependency + two `add()` call sites; one config path + flag.
- No backend/DB/admin change.

## Risks

1. **JS-rendered root with no static text** → not blocked by A (conservative). Accepted;
   B backstops it after one crawl. justcolor.net is static HTML → unaffected.
2. **`<html lang>` unreliability** → sidestepped by making content Cyrillic ratio the
   deciding signal; `lang` is never load-bearing.
3. **False block of a UA site** → requires predominantly non-Cyrillic root text AND no
   `uk`/`ua` hreflang; a real UA site fails both. Conservative by construction.

## Testing

- `lang_block.py`: mirror `test` coverage of geo_block (add/load/push, URL→host, idempotent).
- walker: foreign root (non-Cyrillic text, no uk hreflang) → `foreign=True`, `urls=[]`,
  no sitemap fetch; Cyrillic root → `foreign=False`, normal plan; non-Cyrillic root but
  `hreflang` contains `uk` → `foreign=False`; thin root → `foreign=False`; fetch error →
  `foreign=False`.
- harvest: `plan.foreign` → `lang_block_store.add(host)` called, page processing skipped;
  content gate `is_non_ukrainian` during walk → `add(host)` then break; store `None` →
  no crash.
- integration: a lang-blocked host is skipped by the `is_blocked_host` pre-fetch gate on
  the next candidate.

## Rollout

Rebuild crawler container. Optionally seed `lang_blocked_hosts.json` with
`justcolor.net` so it drops immediately without waiting for a re-encounter.
