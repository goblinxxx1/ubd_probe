# Page-target word-start matching — design

**Status:** IMPLEMENTED. Track: crawler. Branch: `feat/page-target-precision`.

## Problem

The walker (shared by active harvest, passive re-crawl, and first-crawl) fetches non-promo
pages. Live example: `https://ururu.ua/rozvagy-…-atraktsionah-parku/` (a park-attractions
article) was fetched as a promo target. Root cause: `url_is_promo` / `page_is_target` matched
INCLUDE tokens with a **naive substring** test (`tok in path`), so the promo token `aktsi`
(акція) fired inside `atraktsionah` (атракціон). The module docstring already promises
"word-start стем" matching, but only the *text* matcher (DISCOUNT_CTX regex) honored it — the
*URL* matchers did not. Prior fixes patched this token-by-token (dropped `sale`/`hot`,
slash-anchored EXCLUDE tokens); this replaces the whole class with word-start matching.

## Scope

**Part 1 only (this track).** Word-start-anchored INCLUDE / promo URL matching.

**Part 2 deferred (deliberately NOT done):** "audience token alone should not make a page a
target." Investigation showed audience URL slugs (`/dlya-veteraniv`, `/dsns`, `/pilhy-ubd`)
are targets **by deliberate, test-backed design** (track `1e3f263`; `test_veteran_slugs_are_target`,
`test_security_forces_slugs_are_target`). Dropping them would break that feature and ~15
assertions. The audience-article symptom (`ato.if.ua/marsh-zakhisnikiv`) is a **source-quality**
problem (a veteran-news site should not be a source), not a page-matching one — handle
separately. Left for the user's decision.

## Design (Part 1)

All in `crawler/discovery/promo_lexicon.py`; walker/passive/active inherit via the shared
`page_is_target`.

- New `_seg_hit(path, tokens) -> bool`: a token matches only when it starts a word/segment —
  preceded by start-of-path or one of `/ - _ . +` or space. Tokens may contain their own
  hyphens (`national-guard`). No regex escaping; linear scan with a boundary check.
- `url_is_promo` uses `_seg_hit(path, SEED_URL_TOKENS)`.
- `page_is_target` uses `_seg_hit(path, INCLUDE_TOKENS)` for the URL check (anchor-text and
  EXCLUDE paths unchanged).

Effect: `aktsiya`/`znizhka`/`dlya-veteraniv`/`national-guard`/`dostavka-i-oplata` still match;
`atraktsionah`/`lokatsiyah`/`dyslokatsiya` no longer match `aktsi`. Kills the substring-collision
class without recall loss. Fewer wasted walker fetches → faster passes → first-crawl reaches its
backlog (incl. edclinic) sooner.

## Testing

`test_include_tokens_word_start_anchored`: the ururu URL is not promo/target; boundary-anchored
promo/audience/info/hyphenated slugs still match. Existing veteran/security/info/promo/EXCLUDE
assertions stay green (no behavior change for real slugs). Full crawler suite 651.

## Safety

EXCLUDE matching untouched (its slash-anchored tokens + tests unchanged). Only removes
false-positive INCLUDE matches; no real promo/audience/info slug regresses (verified by the
existing suite). Confined to one module.
