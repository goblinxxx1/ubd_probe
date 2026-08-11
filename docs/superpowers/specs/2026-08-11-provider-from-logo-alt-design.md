# Design — Provider name from logo `alt`

**Date:** 2026-08-11
**Scope:** crawler only (`fetchers/website.py`, `models.py`, `extract/heuristic.py`)

## Problem

The admin "Хто пропонує (провайдер)" field is filled from `OfferCandidate.provider`,
derived as `og:site_name → <title> → <h1>`. On many sites `og:site_name` is absent and
`<title>` is cluttered page-title marketing. Live example — terraincognita.com.ua
`/oplata-dostavka/`:

- `og:site_name` = **absent**
- `<title>` = `"Умови покупок Terra Incognita 💳 Товари для туризму та відпочинку"` (noisy)
- logo `<img alt>` = **"Terra Incognita"** (clean business name)

The logo `alt` is the cleanest provider name and is currently ignored.

## Requirements

1. **Провайдер:** prefer the logo image `alt`, then existing chain. Approved chain:
   **logo `alt` → `og:site_name` → `<title>`**.
2. **Опис:** already correct — `description = cand.body = the discount paragraph`
   (the triggering segment). No change. Verified live.

## Design

### Logo-alt extraction (`fetchers/website.py`)

`_extract_logo_alt(tree) -> str | None`: first non-empty, non-generic `alt` from
logo-scoped selectors, in order:

```
img[class*=logo]  →  [class*=logo] img  →  [id*=logo] img  →
a[class*=brand] img  →  header a img
```

- Scoping to logo containers avoids unrelated `img[alt]` on the page
  (e.g. `alt="Накладений платіж"`, `alt="Meest Пошта"`).
- Skip generic alts: `{logo, лого, image, banner, банер, home, головна}` (case-insensitive).
- Whitespace-normalise + length-cap (reuse `_cap_tagline`).

### Threading (`models.py`)

Add `RawItem.logo_alt: str | None = None` (separate field — `site_name` is also consumed
by `discovery/attribution.py` brand attribution, so it must stay intact).

`WebsiteFetcher.fetch` sets `logo_alt=_extract_logo_alt(tree)` on each item. Other
fetchers (facebook/instagram/telegram) leave the dataclass default `None`.

### Provider derivation (`extract/heuristic.py`)

Change the one line:

```python
display_provider = (item.logo_alt or item.site_name or provider).strip() or provider
```

Because `site_name` itself already falls back `og:site_name → title → h1`, the effective
chain is exactly **logo_alt → og:site_name → title → h1** — matching the approved choice.
The classification blob (`heuristic.py:121`) is unchanged.

## Tests (TDD)

- `_extract_logo_alt` picks the logo-scoped alt; ignores payment/partner `img[alt]`.
- generic alt `"logo"` → `None`.
- `RawItem` carries `logo_alt` after fetch.
- provider precedence: `logo_alt` wins over `site_name`; absent `logo_alt` → `site_name`.
- live proof: terraincognita provider == `"Terra Incognita"`.

## Risk

Ordered logo-scoped selectors + generic skip keep false picks low. `site_name` and all
its consumers are untouched, so the existing provider behaviour remains the fallback.

## Non-goals

No change to "Опис" (already correct), to `site_name`, or to attribution.
