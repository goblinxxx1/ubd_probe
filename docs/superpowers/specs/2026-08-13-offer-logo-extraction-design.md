# Design — Offer brand-logo extraction (JSON-LD, SVG-safe)

Date: 2026-08-13
Status: approved (design), pending spec review
Track: crawler + backend + public (own branch off `main`)

## Problem

Some business sites carry their real brand logo as an **SVG** that our current
pipeline never captures. Concrete case: `woodmallcinema.com`.

- The genuine logo is `https://woodmallcinema.com/themes/woodmall/img/logo.svg`,
  exposed in JSON-LD `Organization.logo` and rendered in the header via
  `<i class="logo__icon">` (a CSS/icon render, **no `<img src>`**).
- Our `_extract_logo` ([crawler/crawler/fetchers/website.py:40]) only checks
  `apple-touch-icon → og:image → favicon`. On this site there is no
  apple-touch-icon, so it grabs **`og:image` — a JPEG movie-poster thumbnail**,
  and the SVG brand logo is lost.

SVG display itself is **not** the problem: the frontend renders images via
`<img :src>` ([public/src/components/OfferCard.vue:8],
[public/src/views/OfferDetailView.vue:62]), and browsers render `<img src="x.svg">`
exactly like a JPG. The problem is purely **capture** — the logo lives in a place
we don't look — plus the fact that "logo" and "card hero image" are conflated in
one field today.

## Key finding: `logo_url` is misnamed today

The crawler already has `RawItem.logo_url`, but it does **not** hold a brand logo —
it holds the **hero image** source:

- `_extract_logo(tree, url)` (og:image chain) → `RawItem.logo_url`
  ([website.py:241,272])
- `heuristic.py:151`: `image_url=getattr(item, "logo_url", None)` →
  `OfferCandidate.image_url`
- `payloads.py:16`: `image_url` → backend → `Offer.image_url` → frontend hero.

So the existing `logo_url` is really the card hero. This design renames that path
for clarity and introduces a **separate, genuine** brand-logo field.

## Decision: separate `logo_url` field (not "SVG replaces the photo")

`image_url` is the card hero. Replacing a good `og:image` photo with a small brand
mark would make cards look worse. Keeping a logo AND a good hero requires **two
fields**:

- **hero photo** (`og:image` chain) stays the card image — no regression;
- **brand logo** (SVG-friendly) shown as a small badge/avatar next to the provider
  — SVG is crisp exactly at that small size.

Rejected alternatives:
- *SVG into the same field* — regresses cards where `og:image` is a real photo.
- *SVG only as fallback when no photo* — for woodmall the `og:image` exists, so the
  SVG would never surface; fails the actual ask.

## Components & data flow

### 1. Crawler — website fetcher (`crawler/crawler/fetchers/website.py`)

**Rename the hero path (targeted cleanup):**
- `_extract_logo` → `_extract_image` (unchanged og:image chain:
  `apple-touch-icon → og:image → icon → shortcut icon`).
- `RawItem.logo_url` → `RawItem.image_url`; call site passes `image_url=image`.

**New `_extract_logo(tree, base_url)` — the genuine brand logo, priority order:**
1. **JSON-LD** `logo`: parse every `<script type="application/ld+json">`, walk the
   JSON (object, list, or `@graph`), match nodes whose `@type` is
   `Organization`, `LocalBusiness`, or `WebSite` (case-insensitive; `@type` may be
   a string or a list), take `logo`. `logo` may be a string URL or an object with
   `url`. First valid wins.
2. **Fallback:** `src` from the existing `_LOGO_IMG_SELECTORS`
   (`img[class*=logo]`, `[class*=logo] img`, `[id*=logo] img`,
   `a[class*=brand] img`, `header a img`), first non-empty `src`.
3. **Fallback:** `apple-touch-icon` href (square brand icon).
4. None → `logo_url = None`.

**Safety (hard requirements):**
- Return a **URL string only** — never inline SVG markup.
- Resolve relative URLs via `urljoin(base_url, val)`.
- **Scheme allowlist:** accept only `http`/`https`. Reject `javascript:`,
  `data:`, and anything else (a shared `_safe_url(base, val)` helper used by both
  `_extract_image` and `_extract_logo`).
- Cap length to the column limit (1024).

`RawItem` gets a new `logo_url` field (the real logo). `logo_alt` is unchanged
(still feeds provider naming).

### 2. Crawler — candidate + payload

- `OfferCandidate` gains `logo_url: str | None = None`
  (`crawler/crawler/models.py`).
- `heuristic.py`: `image_url=item.image_url` (renamed), and new
  `logo_url=getattr(item, "logo_url", None)`.
- `payloads.py`: add `"logo_url": cand.logo_url`.

### 3. Backend

- `Offer` model: new nullable `logo_url: Mapped[str | None]` (`String(1024)`)
  ([backend/app/models/offer.py]).
- **Alembic migration:** add `offers.logo_url` (nullable, no backfill).
- Schemas ([backend/app/schemas/offer.py]): `logo_url` in `OfferOut` (public +
  admin), and accepted in the crawler-create + admin update paths.
- `create_offer` / `update_offer` pass `logo_url` through. No validation beyond
  length; scheme safety is enforced crawler-side and by `<img>` render.
- Admin edit form may set/clear it (optional; low priority — passthrough is enough
  for v1, admin UI field is a nice-to-have, see YAGNI note).

### 4. Frontend (public + admin)

- **Public** `OfferCard.vue` + `OfferDetailView.vue`: render `offer.logo_url` as a
  small brand badge/avatar next to `provider`. If absent → render nothing
  (graceful). Hero `image_url` unchanged.
- Render strictly via `<img :src="offer.logo_url" :alt="offer.provider">`.
  **Never** `v-html` / inline `<svg>`.
- Admin `OfferFormView`: show the logo (read-only preview is enough for v1).

## Error handling / edge cases

- Malformed JSON-LD → skip that `<script>`, continue (never throw).
- `@type` as list, `@graph` wrapper, `logo` as object vs string — all handled.
- Non-http scheme or empty → treated as "no logo", fall through the chain.
- Broken remote logo URL at render time → browser shows nothing; badge is
  best-effort, not required.
- Mixed content: page base is https, `urljoin` keeps https; http-only logos are
  accepted but may be blocked by the browser — acceptable, no crash.

## Testing

- **Crawler** (`test_website_fetcher.py`): JSON-LD string logo; JSON-LD object
  `{url}`; `@graph`/list `@type`; fallback to `<img class=logo>` src; fallback to
  apple-touch-icon; no logo → None; **`javascript:`/`data:` rejected**; relative
  URL resolved. Plus: renamed hero path still returns og:image (`image_url`).
- **Backend** (`test_offer_schema.py` / `test_internal.py`): `logo_url` accepted
  from crawler payload and surfaced in `OfferOut`; migration round-trips.
- **Frontend** (`OfferCard.test.js`): badge renders when `logo_url` set; nothing
  rendered when absent; `src` bound (no `v-html`).

## Security summary (the explicit ask)

1. Only ever store/emit a **URL**; the logo is rendered by `<img :src>`, which
   sandboxes SVG (no script execution).
2. **Never** inline SVG markup anywhere (no `v-html`, no raw `<svg>` injection).
3. Scheme allowlist `http`/`https` at extraction time blocks `javascript:`/`data:`
   payloads from ever reaching the DB or DOM.

## YAGNI / scope

- No downloading/re-hosting logos (store remote URL only).
- No image processing, no dimension detection.
- Admin *editing* of logo is a read-only preview in v1 (passthrough is the value).
- Out of scope: telegram/instagram/facebook fetchers (website-only for now; other
  fetchers set `logo_url=None`, harmless).

## Related

Second, independent feature raised same session — **auto-expiry of offers past
`valid_until`** — has its own spec/track. Not covered here.
