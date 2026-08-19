# Crawler: editorial (news/blog) domain gate

**Date:** 2026-08-19
**Status:** Design approved (option B)
**Track:** content-news budget leak (izmacity.com class)

## Problem

A city news portal (`izmacity.com`) is walked in full — robots + sitemap + **14
`/articles/` fetches per visit** — yielding **0 offers**. Evidence:

- Host gates all pass: `is_news_host` = False (domain "izmacity" has no news token),
  not foreign / low-value / blocked. Same structural blind spot as `akzent.zp.ua`.
- Every article slug matches `page_is_target` via **audience tokens** in the URL
  (`zahisnik`, `policiy`, `akci`, `viysk`) — the deliberate "audience-as-target"
  feature. A frontline-town news site's slugs are saturated with exactly these words
  ("загинув захисник", "поліція з'ясовує", "акція на підтримку полонених").
- Correctness is already handled: `attribution.py` `is_media = is_article and not
  has_business_schema` drops the offer, so izmacity produces **0 offers**. The residual
  cost is pure **crawl budget** — 14 news fetches per visit until `media_autoblock`
  (behavioural, K=2 zero-structural crawls) blocks the host.

## Key existing asset

The website fetcher **already extracts** the standard editorial signal per page onto
`RawItem`: `is_article` (schema.org `NewsArticle`/`BlogPosting`/`Article` **or**
`og:type=article`), plus `has_offer_schema`, `has_business_schema`. Nothing consumes it
to stop the walk — `attribution` only uses it to drop an individual offer, after the
page is fetched and extracted.

## Goal

Abandon an editorial (news/blog) domain after the **first** editorial page instead of
walking all of it, using the signal already on `RawItem`. Do not abandon a real
merchant domain that merely has a blog page.

Non-goal: host-level persistent block (that is `media_autoblock`'s job; it still fires
after the domain records zero-structural crawls). Non-goal: URL-token exclusion of
`/articles/` (option A, deferred).

## Design

### Per-page editorial gate in `ActiveHarvester._harvest_one`

Mirror the existing per-page language gate (the `is_non_ukrainian` break), one branch
later in the same loop. A page is **editorial** when it declares itself an article and
carries **no** commercial schema:

```
editorial(page) := any(item.is_article)
                   and not any(item.has_offer_schema)
                   and not any(item.has_business_schema)
```

In the loop, after the language check and before `_process_page`:

```python
                if (self._editorial_gate_enabled and not structural
                        and _is_editorial_page(items)):
                    # News/blog portal page with no commercial schema — abandon the whole
                    # domain rather than walk its remaining (all-editorial) pages.
                    break
                if self._process_page(cand, items, cats, known, summary):
                    structural = True
```

Helper (module-level in `harvest.py`):

```python
def _is_editorial_page(items) -> bool:
    if not any(getattr(it, "is_article", False) for it in items):
        return False
    return not any(getattr(it, "has_offer_schema", False)
                   or getattr(it, "has_business_schema", False) for it in items)
```

### Why this is safe (two guards + ordering)

1. **Strict condition** — fires only when the page *explicitly declares* article/blog
   markup AND has no `Offer`/`LocalBusiness`/`Organization` schema. A schema-less small
   business page is `is_article=False` → never caught; a business with Organization
   schema → `has_business_schema=True` → never caught; a merchant blog post carrying an
   `Offer` → `has_offer_schema=True` → never caught.
2. **`not structural` guard** — once any page on the domain has shown commercial schema
   (`structural=True`), a later editorial/blog page no longer abandons the domain (the
   offers are already being captured); it simply is not the break trigger.
3. **Promo-first ordering** — the walker already sorts promo/offer pages ahead of
   generic targets, so a real merchant's offer page is fetched before any blog page; a
   news portal (no promo pages) hits the editorial break on its first target page.

Net: izmacity abandons after ~1–2 fetches (homepage index → first article → break)
instead of 14; `media_autoblock` still blocks the host after K zero-structural crawls.

### Config

`editorial_gate_enabled: bool = True` — kill-switch, wired `_RawSettings` + `Config` +
`from_settings` (mirror `lang_gate_enabled`); passed into `ActiveHarvester`
(`editorial_gate_enabled=True` param, guarding the check).

## Blast radius

- `harvest.py`: one module helper + one guarded `break` branch + one `__init__` flag.
- `config.py`: one bool in three places. `wiring.py`: pass the flag.
- No fetcher change (signals already extracted), no new store, no walker change,
  no backend/DB change.

## Risks

1. **A merchant whose homepage/first target page is `og:type=article` with no schema
   AND whose real offers are deeper** → abandoned before reaching them. Rare (homepages
   are `og:type=website`; the strict no-commercial-schema condition + promo-first order
   narrow it further). If seen, the offer re-appears via another page/host.
2. **A legitimate free-for-veterans offer published only as a schema-less blog post on a
   news site** → not crawled. Acceptable: that is editorial content by construction, and
   the site is a news portal media_autoblock targets anyway.

## Testing (`crawler/tests/test_active_harvest.py`)

- First page editorial (is_article, no offer/business schema) → domain abandoned after
  1 fetch, no offer; subsequent walker URLs never fetched.
- Editorial page **after** a structural (schema-bearing) page → NOT abandoned (the
  `not structural` guard): the structural page's offer is kept, the editorial page is
  just skipped/ends the walk without discarding prior work.
- An `is_article` page that ALSO has `has_offer_schema` → not editorial → processed.
- A non-article page → not editorial → processed normally.
- `editorial_gate_enabled=False` → editorial page processed (byte-equivalent to today).

## Rollout

Rebuild crawler container. No queue cleanup needed (izmacity already yields 0 offers).
Verify izmacity is abandoned after the first article on the next walk (logs show ≤2
`izmacity.com/...` content fetches).
