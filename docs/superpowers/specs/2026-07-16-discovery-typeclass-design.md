# UBD Discounts — Search Result Type Classification Design — Track D

**Date:** 2026-07-16
**Scope:** Crawler — classify search-discovery results by platform type
**Status:** Approved design, ready for implementation planning
**Branch:** `feat/discovery-typeclass` (cut from `main`)

## Context

Active search discovery (Tracks A/B) turns every result URL into a
`SourceCandidate` with a hardcoded `type="website"`. So a `t.me/channel` found via
search becomes a website candidate; after moderation it becomes a website source,
and the website-fetcher tries to crawl `t.me/channel` as plain HTML instead of the
telegram-fetcher hitting `t.me/s/channel`. Social/utility URLs (`instagram.com/p/…`
posts, `facebook.com/share/…`) also become junk candidates.

Track D adds a small classifier so search results are tagged with the correct
platform type and obvious social junk is filtered — feeding the existing
moderation → source → correct-fetcher pipeline. The main practical win is
**telegram** (t.me is indexed by web search); IG/FB profiles are rarely returned
by web search (closed to indexing) but are handled correctly when they do appear.

## Goals

- A `classify_candidate(url) -> tuple[str, str] | None` helper: returns
  `(type, url_or_handle)` or `None` (invalid or reserved-path junk).
- Both `DuckDuckGoProvider` and `SearxngProvider` use it instead of hardcoding
  `type="website"`; a `None` result is skipped.
- Correct types flow through unchanged (`suggested_sources` already accepts all
  `SourceType`s; fetchers extract handles via their own `_handle_of`).

## Non-Goals

- Backend/admin/public changes — they already accept every source type.
- Deep validation of whether a profile/channel is real or relevant (moderation
  still decides).
- Fetching/verifying the classified URL — classification is URL-shape only.
- Changing the passive-discovery classifier (`passive.py`) — leave it as is.

## Architecture

### Classifier (`crawler/crawler/discovery/providers.py`)

```python
def classify_candidate(url: str) -> tuple[str, str] | None
```
- Normalise the URL first (reuse `_normalize_url`); `None`/invalid → `None`.
- Host-based type (strip a leading `www.`):
  - `t.me`, `telegram.me` → `("telegram", url)`;
  - `instagram.com` → `("instagram", url)` unless the path is a reserved segment
    (`/p/`, `/reel/`, `/reels/`, `/explore/`, `/stories/`, or root `/`) → `None`;
  - `facebook.com`, `fb.com` → `("facebook", url)` unless reserved
    (`/share`, `/sharer`, `/events`, `/photo`, `/watch`, or root `/`) → `None`;
  - anything else → `("website", url)`.
- Returns the normalised URL as `url_or_handle`; fetchers derive the handle via
  their existing `_handle_of`, and `normalize_ref` collapses URL/handle for dedup.

### Providers use it

In each provider's result loop, replace the `_normalize_url` + hardcoded
`type="website"` construction with:
```python
classified = classify_candidate(r.get("href", ""))   # or result["url"] for searxng
if classified is None:
    continue
type_, url_or_handle = classified
out.append(SourceCandidate(
    name=r.get("title") or url_or_handle, type=type_, url_or_handle=url_or_handle,
    discovered_from_source_id=None, discovery_note=f"<provider>: {keyword}"))
```
`name`/`discovery_note` unchanged. The combinator and everything downstream are
untouched.

## Data flow

```
search result URL → classify_candidate
   → None (invalid / social junk)              → skipped
   → ("telegram", url) / ("instagram", …) / … → SourceCandidate(type)
   → suggested_sources (correct type) → moderation → source(type) → matching fetcher
```

## Error handling & edge cases

- Invalid/relative URL → `_normalize_url` returns `None` → `classify_candidate`
  returns `None` → skipped.
- `instagram.com` / `facebook.com` root (no profile) → reserved → `None`.
- Reserved post/share paths → `None` (no junk candidate).
- A telegram deep link like `t.me/s/chan` or `t.me/chan/123` → still `telegram`;
  the fetcher's `_handle_of` extracts the channel.
- Unknown host → `website` (safe default, current behaviour preserved).

## Testing & verification

- `classify_candidate`: `t.me/chan`→telegram; `instagram.com/profile`→instagram;
  `instagram.com/p/abc`→None; `instagram.com`→None; `facebook.com/biz`→facebook;
  `facebook.com/share/x`→None; `https://site.com/x`→website; junk/relative→None.
- Provider (mocked results mixing website + t.me + instagram profile + instagram/p/):
  yields candidates with correct types and drops the reserved one.
- Full crawler suite stays green.
- (Optional) real pass: with a telegram-ish keyword, confirm any `t.me` result
  lands as a `telegram` suggestion; not required (web search may not return one).

## Open decisions (defaulted, override at planning time)

- `url_or_handle` stores the normalised full URL (fetchers extract the handle).
- Reserved paths: IG `/p/ /reel/ /reels/ /explore/ /stories/`; FB `/share /sharer
  /events /photo /watch`; both treat bare root as reserved.
- No new config flag — classification is always on for search providers.
