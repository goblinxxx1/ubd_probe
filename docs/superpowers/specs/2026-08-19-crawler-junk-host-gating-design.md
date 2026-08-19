# Crawler: junk-host gating (Track 2)

**Date:** 2026-08-19
**Status:** Design approved
**Program:** crawler precision fixes (Track 2 of: C junk-hosts → B queue-dedup → D extractor-precision). Russian gate (was Track 1) deferred — see [[ubd-crawler-precision-program]].

## Problem

Non-business "junk" hosts leak offers into the moderation queue: `uaserials.com`
(pirate streaming — 4 pending offers from movie titles like *"Поліцейська історія…
онлайн безкоштовно"*), `akzent.zp.ua` (regional news), `moreliudei.media` (media
outlet). None sell veteran discounts.

### Why the existing gates don't stop them (investigated first)

- `is_news_host` / `is_low_value_host` are narrow structural gates (tokens
  `news/novyny/gazeta/visti/pravda`; `gov/edu/mil/int`). None of these hosts match.
- **`media_autoblock` already works and WILL catch them** — registry state confirms
  all three are `provider_ever: False`, `media_streak: 1`, `passes: 1`. On the **2nd**
  active crawl (`media_autoblock_crawls = 2`) each is auto-blocked. The gate is not
  broken, just not yet fired.

### The actual gap

The **first** crawl dumps offers before the K=2 behavioral block fires —
`uaserials.com` produced **12 offers in one pass**. So the gap is "obvious junk
crawled once before it is blocked", not "junk never blocked".

### What is NOT a safe fix (validated by execution)

- Entertainment host tokens (`kino`, `film`) would block **`planetakino.ua`** — a
  **published, legitimate** veteran-discount offer (#173, cinema). Cinemas are real
  businesses. Piracy-token curation drifts from the codebase's "structural, not a
  host list" philosophy and is risky. **Rejected.**
- Lowering `media_autoblock_crawls` to 1 would block legitimate small businesses that
  lack schema.org on a single transient crawl. **Rejected.**

The only clean structural signal is the **`.media` TLD**: `.media` domains are
essentially always media outlets. Verified: **0 published offers** are on a `.media`
host, so the gate over-blocks nothing currently live. (`suspilne.media` = public
broadcaster/news — correctly gated; `dumka.media` already seed-blocked.)

## Goals

1. Stop `.media` hosts at the first crawl (pre-fetch gate), self-generalizing to
   future `.media` outlets without a host list.
2. Immediately block the three confirmed offenders and clean their queue offers.
3. Change nothing about the working `media_autoblock`; do not host-block legitimate
   classes (cinemas, hospitals).

Non-goals: entertainment/piracy token gates (unsafe — cinemas); content-based news
detection (that stays with `media_autoblock`); `gospital.itmed.org` (a hospital — its
about-us false positive is an extractor/page-type issue for Track 4, not a host block).

## Design

### Component 1 — `.media` TLD in `is_news_host` (`discovery/host_quality.py`)

Add a media-TLD set and check it first in `is_news_host`:

```python
# TLDs that denote a media outlet regardless of the label (news portals, magazines).
_MEDIA_TLDS = {"media"}

def is_news_host(value: str | None) -> bool:
    """True if the host is a news/media outlet — never an offer source for UBD.
    Matched by a news token in any label OR a media TLD (.media)."""
    host = bare_host(value)
    if not host:
        return False
    labels = host.split(".")
    if labels[-1] in _MEDIA_TLDS:
        return True
    return any(tok in label for label in labels for tok in _NEWS_TOKENS)
```

`is_news_host` is already wired into the harvest pre-fetch gate
(`harvest.py`, alongside `is_foreign_host` / `is_low_value_host` / `is_blocked_host`),
so a `.media` candidate is dropped before any fetch, on the very first encounter. No
new call site.

### Component 2 — seed the confirmed offenders (rollout, not code)

Insert `uaserials.com`, `akzent.zp.ua`, `moreliudei.media` into the backend
`blocked_hosts` table (`status = approved`), the same table `media_autoblock` writes
to (admin-visible, moderator-removable). Once present, the crawler's
`is_blocked_host` (which loads learned blocked hosts) drops them everywhere, and the
backend's create-offer block gate auto-rejects any future offer from them. No wait for
crawl-2.

### Component 3 — clean the existing queue (rollout, not code)

Reject the pending offers already emitted by the three hosts (uaserials ×4, akzent,
moreliudei) so the moderator queue reflects the new gating. Ukrainian-legit hosts in
the same queue (compass-group, smartlab, leocard) are untouched.

## Blast radius

- Code: one constant + one `if` in `host_quality.py`. No new file, no new call site,
  no config, no wiring, no backend/DB schema change.
- Operational (rollout): 3 `blocked_hosts` rows + reject ~6 queue offers.

## Risks

1. **A legitimate `.media` business exists and offers veteran discounts.** None live
   today (0 published on `.media`). If one appears, the moderator removes it from
   `blocked_hosts` (the block is admin-visible and reversible). Low.
2. **Seed is one-off** — new junk hosts still ride the `media_autoblock` crawl-2 path
   (first-crawl leak remains for non-`.media`, non-token junk like `akzent`). Accepted:
   the deep content-level fix is Track 4; this track is host-structural + cleanup only.

## Testing

- `is_news_host`: `moreliudei.media` → True; `suspilne.media` → True; `x.media` → True;
  a legit `.com`/`.ua` business host (`planetakino.ua`, `shop.ua`) → False; existing
  token hosts (`groza-news.info`, `x.novyny.ua`) still → True; empty/None → False.
- Confirm `planetakino.ua` (published cinema) is NOT gated (guards against the rejected
  token approach regressing).

## Rollout

1. Rebuild crawler container (ships the `.media` gate).
2. Seed the three hosts into `blocked_hosts` (approved).
3. Reject the ~6 existing junk offers in the queue.
4. Verify: `is_news_host('moreliudei.media')` True in the running crawler; the three
   hosts no longer fetched on subsequent passes.
