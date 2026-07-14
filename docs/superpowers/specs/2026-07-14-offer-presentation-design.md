# UBD Discounts — Offer Presentation (links, logo, placeholder, font) Design

**Date:** 2026-07-14
**Scope:** Cross-cutting UI/data change (offer model + admin + public + crawler)
**Status:** Approved design, ready for implementation planning
**Branch:** `feat/offer-presentation` (cut from `main`)

## Context

Follow-up polish to the offer model and its presentation, agreed before starting
the search-discovery crawler work. Today an offer has a free-text `contacts`
field (shown as "Контакти:" in public) and an `image_url`. We want offers to
carry structured links (the business site + the specific page the offer came
from), to display the site logo, to restyle the public card, recolour the image
placeholder, and to apply the UAF Memory font on the public site. The crawler
must populate the new fields automatically so auto-created offers are complete.

The database has no real offer content yet (only ephemeral demo/test rows), so
renaming a column is painless.

## Goals

- Replace the free-text `contacts` field with a structured **site link**, and add
  a separate **article/news-page link**. Both optional, both validated as URLs,
  both rendered as clickable links in public (card + detail).
- Public offer **card**: logo on the right, provider ("хто пропонує") on the left.
- Recolour the image **placeholder** to `#4B5320` (army green).
- Apply the **UAF Memory** font across the public site (files already provided by
  the user under `public/src/assets/fonts/`).
- The **crawler** populates `site_url`, `article_url`, and `image_url` (site logo)
  when it creates offers.

## Non-Goals

- Search-based active discovery (DuckDuckGo/SearXNG) — a separate later track.
- Restyling the public **detail** page layout (logo/provider positioning) — only
  the card layout changes now; detail gets the new links but keeps its layout.
- Decorative font cuts (Compact/Narrow/SmallCaps) — only the core family
  (Light/Regular/Medium/Bold/Black) is wired in.
- Semantic/LLM image selection — logo extraction is best-effort heuristic.

## Architecture

### Data model + migration (backend)

- `Offer` model: rename `contacts` (String 512) → **`site_url`** (String 1024,
  nullable); add **`article_url`** (String 1024, nullable). `image_url` already
  exists (String 1024).
- Alembic migration: rename column `contacts`→`site_url` (widen to 1024) and add
  `article_url`. No data migration needed (no real content).

### Schemas + validation (backend)

- `OfferBase`/`OfferCreate`/`OfferUpdate`/`OfferOut`: replace `contacts` with
  `site_url`, add `article_url`.
- URL validation: a shared optional-URL validator — `None`/empty passes; a
  non-empty value must be `http://` or `https://`. Applied to `site_url` and
  `article_url` on create/update; returns 422 on invalid input.

### Admin form

- `OfferFormView`: field "Контакти" → **"Сайт"** (`site_url`); add **"Сторінка
  новини"** (`article_url`). Client-side URL validation with a format hint. The
  offers list view does not surface `contacts`, so no change there.

### Public

- `OfferCard`: layout becomes provider (left) + logo image (right); render
  clickable "Сайт" / "Сторінка новини" links when present
  (`target="_blank" rel="noopener"`).
- `OfferDetailView`: replace the "Контакти:" row with clickable "Сайт" /
  "Сторінка новини" links; layout otherwise unchanged.
- `placeholder.js`: SVG fill `#1f6feb` → `#4B5320`.
- Fonts: add `@font-face` declarations for UAF Memory
  (Light=300, Regular=400, Medium=500, Bold=700, Black=900) referencing the
  `.woff2` files in `public/src/assets/fonts/`, and set the global base
  `font-family: "UAF Memory", system-ui, sans-serif`.

### Crawler (populate new fields)

- `RawItem` already carries `url` (the fetched page URL). `OfferCandidate` gains
  `site_url`, `article_url`, `image_url`.
- `website.py`: when building items, capture `article_url` = the exact offer page
  URL (`item.url`); derive `site_url` = its origin (`scheme://host`); extract
  `image_url` = site logo via heuristic priority `apple-touch-icon` → `og:image`
  → `favicon` (best-effort, may be `None`).
- The extractor/runner carries these onto the `OfferCandidate`; `api_client`
  includes `site_url`/`article_url`/`image_url` in the `/api/internal/offers`
  payload; the backend internal create schema accepts them.
- Dedup unchanged (`content_hash` is computed from text, not URLs).

## Data flow

```
website page → RawItem(url) → logo heuristic → OfferCandidate(site_url, article_url, image_url)
   → POST /api/internal/offers → Offer(site_url, article_url, image_url, status=pending_review)
   → admin moderation → public card (logo right / provider left + links)
```

## Error handling & edge cases

- Missing logo / og:image / favicon → `image_url=None` → public falls back to the
  `#4B5320` placeholder.
- Invalid URL submitted via admin/API → 422 from the URL validator.
- Offer with no links (manual entry) → link rows simply not rendered.
- `site_url` derivation from a page with no host (malformed) → skip `site_url`,
  keep `article_url` if valid.

## Testing & verification

- **backend:** URL validator (valid / invalid / empty-None); schema round-trips
  `site_url`+`article_url`; migration applies cleanly (create_all + alembic head).
- **crawler:** website-fetcher fills `site_url`/`article_url`/`image_url`; logo
  heuristic prefers `apple-touch-icon` over `favicon`; origin derivation correct.
- **public:** card renders logo-right/provider-left and clickable links; detail
  renders links; placeholder is `#4B5320`; UAF Memory applied (computed
  font-family).
- **end-to-end:** point the fixture page at content with a logo + offer → crawler
  pass → offer carries links+logo → visible in admin and public card.

## Open decisions (defaulted, override at planning time)

- Logo heuristic priority: `apple-touch-icon` → `og:image` → `favicon`.
- `site_url` = origin (`scheme://host`) of the offer page; `article_url` = full
  page URL.
- Font weights wired: 300/400/500/700/900 from the core UAF Memory cuts.
