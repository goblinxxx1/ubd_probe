# Crawler: extractor precision (Track 4)

**Date:** 2026-08-19
**Status:** Design approved (narrow scope: provider + about-page + bare-price)
**Program:** crawler precision fixes (Track 4, final). See [[ubd-crawler-precision-program]].

## Problem

Three concrete extractor false positives in the live queue, each with a precise,
validated root cause:

| # | Queue evidence | Root cause (found in code) |
|---|---|---|
| A | #343 b2bconsult — legal price "252 грн" → `fixed` | `DISCOUNT_CTX` substring `акці` matches "**акці**онерні товариства" (акціонер = shareholder) |
| B | #334 `provider="Footer-logo"`, #344 `provider="wezom-starter-template"` | `_extract_logo_alt` skips only **exact** `_GENERIC_ALTS`; structural alts pass |
| C | #342 gospital `/about-us`, #344 sheriffua `/about` → `free` | FREE branch fires on any free-word + audience co-occurrence, incl. an **about** page's mission text |

## Goals

Kill these three classes precisely, without collateral. Non-goals (deferred, per scope
choice): aggregator content (dom.ria #345/#346), general-promo→audience mis-tagging
(leocard #335).

## Design — three independent fixes

### A. Discount-context homograph guard (`discovery/promo_lexicon.py`)

`DISCOUNT_CTX` currently: `знижк|акці|розпродаж|спецпропоз|промокод|економ|вигід|-\s*\d`.
The bare `акці` matches the shareholder/joint-stock family (акціонер, акціонерні,
акціонерне). Replace `акці` with `акці(?!онер)`:

```python
DISCOUNT_CTX = re.compile(
    r"знижк|акці(?!онер)|розпродаж|спецпропоз|промокод|економ|вигід|-\s*\d",
    re.IGNORECASE)
```

**Validated by execution** (this session): `акці(?!онер)` → False for "акціонерні
товариства", "права акціонера"; True for "акція", "акційна ціна", "акції", "знижка".
("акциз" already fails `акці` — it has и, not і.) Kills #343's fixed offer (its
`DISCOUNT_CTX` hit was "акціонерні" in the title; no other discount context remains, so
`require_discount` drops it).

### B. Structural logo-alt skip (`fetchers/website.py`)

`_extract_logo_alt` compares `alt.lower()` against the exact set `_GENERIC_ALTS`.
Add a token-level guard: split the alt on non-alphanumerics and skip the alt when any
token is a **structural** label (`logo`, `лого`, `footer`, `header`, `template`,
`starter`, `placeholder`, `default`, `icon`, `menu`, `nav`). The existing exact-match
set stays (handles bare "logo"/"image"/"home"). Structural tokens are matched as whole
tokens, **not** substrings, so a real brand like "Home Comfort" or "Logos Bookstore"
is not skipped (`home`/`logos` are not structural tokens; only exact bare `home`/`logo`
were ever generic).

```python
_GENERIC_ALTS = {"logo", "лого", "image", "img", "banner", "банер", "home", "головна"}
# Structural page-scaffold tokens: an alt containing any of these (as a whole token) is a
# template/layout label, not a business name.
_STRUCTURAL_ALT_TOKENS = {"logo", "лого", "footer", "header", "template", "starter",
                          "placeholder", "default", "icon", "menu", "nav"}
_ALT_TOKEN_RE = re.compile(r"[^0-9a-zA-Zа-яА-ЯіїєґІЇЄҐ]+")

def _extract_logo_alt(tree) -> str | None:
    for css in _LOGO_IMG_SELECTORS:
        for node in tree.css(css):
            alt = (node.attributes.get("alt") or "").strip()
            if not alt:
                continue
            low = alt.lower()
            if low in _GENERIC_ALTS:
                continue
            toks = {t for t in _ALT_TOKEN_RE.split(low) if t}
            if toks & _STRUCTURAL_ALT_TOKENS:
                continue
            return _cap_tagline(alt)
    return None
```

Effect: "footer-logo" → {footer, logo} skipped; "wezom-starter-template" →
{wezom, starter, template} skipped; both fall back to `site_name`/`og:site_name`/title.

### C. About/info-page FREE suppression (`extract/heuristic.py`)

The FREE branch (`elif pl.FREE.search(...) and _has_audience_in_text(text)`) is the
weakest signal (free-word + audience anywhere on the page). On an **about** page a
mission statement ("надаємо безкоштовну допомогу … ветеранам") trips it. Suppress FREE
when the page URL is an info/about page; `percent`/`fixed` (which carry an explicit
discount context) are unaffected.

```python
_INFO_PAGE_TOKENS = ("about", "pro-nas", "pro-proekt", "pro-kompani", "o-nas",
                     "o-kompani", "про-нас", "про-проєкт")

def _is_info_page(url: str | None) -> bool:
    return bool(url) and any(tok in url.lower() for tok in _INFO_PAGE_TOKENS)
```

In `extract`, gate the FREE branch:

```python
        elif (pl.FREE.search(pl.FREE_SERVICE.sub(" ", low)) and _has_audience_in_text(text)
              and not _is_info_page(item.url)):
            discount_type = "free"
```

Effect: #342 (`/about-us`) and #344 (`/about`) no longer emit a `free` offer
(`require_discount` then drops them). A genuine free-for-veterans offer lives on an
offer page, not `/about`, so it is unaffected.

## Blast radius

- A: one regex token in `promo_lexicon.py`. B: `_extract_logo_alt` rewrite + one
  constant in `website.py`. C: one helper + one `and` clause in `heuristic.py`.
- No config, no schema, no backend, no wiring. Three isolated, independently testable
  changes.

## Risks

1. **A** — a real promo phrased "акціонерна знижка" would keep matching via `знижк`; a
   promo that ONLY says "акція" for a shareholder-themed offer is implausible. Low.
2. **B** — a brand whose name literally contains a structural token as a whole word
   (e.g. "Icon Studio", "Menu Café") is skipped and falls back to site_name. Rare; the
   fallback is still a reasonable provider. Low.
3. **C** — a legitimate free-for-veterans offer published only on an `/about` page is
   suppressed. Rare (offers live on offer pages); it re-appears if found on any
   non-about page. Low, conservative (only FREE suppressed, not percent/fixed).

## Testing

- A (`crawler/tests/test_promo_lexicon.py` or a heuristic test): `DISCOUNT_CTX` does not
  match "акціонерні товариства"/"права акціонера"; still matches "акція"/"акційна"/
  "акції"/"знижка".
- B (`crawler/tests/test_website_fetcher.py` or a `_extract_logo_alt` unit): "footer-logo"
  and "wezom-starter-template" alts are skipped; a real brand alt ("Смартлаб", "Home
  Comfort") is returned; bare "logo"/"image" still skipped.
- C (`crawler/tests/test_heuristic.py`): a page with free-word + audience on an
  `/about-us` URL yields no offer (`require_discount`); the same text on a `/promo` URL
  yields a `free` offer; percent/fixed offers on an `/about` URL are unaffected.
- End-to-end sanity: re-extraction of #343-like text (fixed price + "акціонерні") →
  no offer; #342/#344-like about text → no offer.

## Rollout

Rebuild crawler container. Reject the existing queue false positives #342, #343, #344
(the gates prevent new ones going forward). Re-evaluate #345/#346 (dom.ria) and #335
(leocard) separately — out of this track's scope.
