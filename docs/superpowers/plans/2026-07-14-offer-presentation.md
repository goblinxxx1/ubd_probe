# Offer Presentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the offer `contacts` field with structured, validated `site_url` + `article_url` links; show the site logo and restyle the public card (logo right / provider left); recolour the placeholder to `#4B5320`; apply the UAF Memory font on public; and have the crawler populate the new fields.

**Architecture:** Backend model+migration+schema change flows outward to admin form, public card/detail, and the crawler. `contacts` → `site_url` (URL), plus a new `article_url`; both optional and URL-validated. Crawler derives `site_url` (page origin), `article_url` (page URL) and `image_url` (site logo, best-effort heuristic).

**Tech Stack:** FastAPI/SQLAlchemy/Alembic (backend), Vue 3 + Element Plus + Vitest (admin), Vue 3 + Less + Vitest (public), httpx/selectolax (crawler).

## Global Constraints

- `contacts` is **renamed** to `site_url` (widen to String 1024); `article_url` is **new** (String 1024, nullable). Both optional.
- URL rule: `None`/empty allowed; a non-empty value must start with `http://` or `https://` — else 422 (backend) / inline error (admin).
- Public **card** layout changes (logo right / provider left) + links; public **detail** gets the links but keeps its layout.
- Placeholder colour is exactly `#4B5320`.
- Font family name is exactly `"UAF Memory"`; weights wired 300/400/500/700/900 from `public/src/assets/fonts/UAFMemory-{Light,Regular,Medium,Bold,Black}.woff2` (already present).
- Logo heuristic priority: `apple-touch-icon` → `og:image` → `favicon`. Best-effort; `None` when absent.
- Do NOT reproduce or embed font glyph data in the plan/code — only `@font-face` references to the existing `.woff2` files.
- Backend tests run from `backend/` with `mysql-container` up (`ubd_test`); crawler tests from `crawler/`; frontend `npm test` (Vitest, API mocked).

---

### Task 1: Backend — model + migration (contacts→site_url, +article_url)

**Files:**
- Modify: `backend/app/models/offer.py:29` (the `contacts` column)
- Create: `backend/alembic/versions/<newrev>_offer_links.py`

**Interfaces:**
- Produces: `Offer.site_url: str|None` (String 1024), `Offer.article_url: str|None` (String 1024). `Offer.contacts` no longer exists.

- [ ] **Step 1: Rename + add columns in the model**

In `backend/app/models/offer.py`, replace the `contacts` line (29):

```python
    site_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    article_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
```

(Leave `image_url` on the next line as-is.)

- [ ] **Step 2: Generate a migration skeleton**

Run (from `backend/`, `mysql-container` up):
```bash
./.venv/Scripts/alembic.exe revision -m "offer links"
```
Expected: a new file `backend/alembic/versions/<newrev>_offer_links.py` with empty `upgrade`/`downgrade`.

- [ ] **Step 3: Write the migration body**

Edit the generated file's `upgrade`/`downgrade` (keep the auto-generated `revision`/`down_revision` header — `down_revision` must be `'c04d4e4207e6'`):

```python
def upgrade() -> None:
    op.alter_column('offers', 'contacts',
                    new_column_name='site_url',
                    existing_type=sa.String(length=512),
                    type_=sa.String(length=1024),
                    existing_nullable=True)
    op.add_column('offers', sa.Column('article_url', sa.String(length=1024), nullable=True))


def downgrade() -> None:
    op.drop_column('offers', 'article_url')
    op.alter_column('offers', 'site_url',
                    new_column_name='contacts',
                    existing_type=sa.String(length=1024),
                    type_=sa.String(length=512),
                    existing_nullable=True)
```

- [ ] **Step 4: Apply and verify the migration**

```bash
./.venv/Scripts/alembic.exe upgrade head
docker exec mysql-container mysql -uroot -pmy-secret-pw -e "USE ubd_test; DESCRIBE offers;" 2>&1 | grep -Ei "site_url|article_url|contacts"
```
Expected: `site_url` and `article_url` present, `contacts` absent. (If `ubd_test` isn't migrated, run against it or use the app DB — point is the columns exist.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/offer.py backend/alembic/versions/
git commit -m "feat(backend): offer site_url/article_url columns + migration"
```

---

### Task 2: Backend — schemas, URL validator, CRUD (TDD)

**Files:**
- Modify: `backend/app/schemas/offer.py`
- Modify: `backend/app/crud/offer.py:30` (the `create_offer` Offer(...) construction)
- Create: `backend/tests/test_offer_urls.py`

**Interfaces:**
- Consumes: model fields from Task 1.
- Produces: `OfferBase`/`OfferUpdate`/`OfferOut` carry `site_url`/`article_url` (no `contacts`); non-empty non-URL values raise 422.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_offer_urls.py`

```python
import pytest
from pydantic import ValidationError

from app.schemas.offer import OfferCreate


def _base(**over):
    data = dict(type="discount", title="T", provider="P",
                discount_type="percent", discount_value="10")
    data.update(over)
    return data


def test_valid_urls_accepted():
    o = OfferCreate(**_base(site_url="https://ex.com", article_url="http://ex.com/a"))
    assert o.site_url == "https://ex.com"
    assert o.article_url == "http://ex.com/a"


def test_empty_urls_become_none():
    o = OfferCreate(**_base(site_url="", article_url=None))
    assert o.site_url is None
    assert o.article_url is None


def test_non_url_rejected():
    with pytest.raises(ValidationError):
        OfferCreate(**_base(site_url="not-a-url"))
```

- [ ] **Step 2: Run test to verify it fails**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_offer_urls.py -q
```
Expected: FAIL — `OfferCreate` still has `contacts`, no `site_url`/validator.

- [ ] **Step 3: Update schemas + validator** in `backend/app/schemas/offer.py`

Add the import at the top (merge into the existing pydantic import line):
```python
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
```

In `OfferBase`, replace the `contacts: str | None = None` line (20) with:
```python
    site_url: str | None = None
    article_url: str | None = None
```
and add this validator inside `OfferBase` (above `_check`):
```python
    @field_validator("site_url", "article_url", mode="before")
    @classmethod
    def _optional_url(cls, v):
        if v is None or v == "":
            return None
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("must be an http:// or https:// URL")
        return v
```

In `OfferUpdate`, replace its `contacts: str | None = None` line (52) with the same two fields, and add the identical `@field_validator(...)` block.

In `OfferOut`, replace its `contacts: str | None` line (70) with:
```python
    site_url: str | None
    article_url: str | None
```

- [ ] **Step 4: Update CRUD construction** in `backend/app/crud/offer.py`

Replace `contacts=data.contacts, image_url=data.image_url,` (line 30) with:
```python
        site_url=data.site_url, article_url=data.article_url, image_url=data.image_url,
```
(`update_offer` uses generic `setattr` from `model_dump(exclude_unset=True)`, so it needs no change.)

- [ ] **Step 5: Run tests (new + full backend suite)**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_offer_urls.py -q
./.venv/Scripts/python.exe -m pytest -q
```
Expected: new file passes; full suite green (any pre-existing test that referenced `contacts` must be updated to `site_url` — search `grep -rn contacts tests/` and fix).

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/offer.py backend/app/crud/offer.py backend/tests/test_offer_urls.py
git commit -m "feat(backend): site_url/article_url schema + URL validation"
```

---

### Task 3: Admin — form fields «Сайт» / «Сторінка новини» + validation (TDD)

**Files:**
- Modify: `admin/src/components/OfferForm.vue` (fromInitial + template fields)
- Modify: `admin/src/utils/offerForm.js` (validateOffer + buildOfferPayload)
- Create/Modify: `admin/src/utils/__tests__/offerForm.spec.js` (or the existing test file for offerForm)

**Interfaces:**
- Consumes: backend schema from Task 2.
- Produces: form emits `site_url`/`article_url`; invalid URLs blocked client-side.

- [ ] **Step 1: Write the failing test** — `admin/src/utils/__tests__/offerForm.spec.js`

```javascript
import { describe, it, expect } from "vitest";
import { validateOffer, buildOfferPayload } from "@/utils/offerForm";

const base = { title: "T", provider: "P", type: "discount" };

describe("offer url fields", () => {
  it("payload carries site_url/article_url, not contacts", () => {
    const p = buildOfferPayload({ ...base, site_url: "https://ex.com", article_url: "" });
    expect(p.site_url).toBe("https://ex.com");
    expect(p.article_url).toBe(null);
    expect("contacts" in p).toBe(false);
  });

  it("rejects a non-URL site", () => {
    expect(validateOffer({ ...base, site_url: "nope" })).toContain(
      "«Сайт» має починатися з http:// або https://"
    );
  });

  it("accepts empty urls", () => {
    expect(validateOffer({ ...base, site_url: "", article_url: "" })).toEqual([]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `admin/`):
```bash
npm test -- offerForm
```
Expected: FAIL — `buildOfferPayload` still emits `contacts`; no URL validation.

- [ ] **Step 3: Update `admin/src/utils/offerForm.js`**

Add a helper + URL checks to `validateOffer` (before `return errors;`):
```javascript
  const urlBad = (v) => v && !/^https?:\/\//.test(v);
  if (urlBad(form.site_url)) errors.push("«Сайт» має починатися з http:// або https://");
  if (urlBad(form.article_url)) errors.push("«Сторінка новини» має починатися з http:// або https://");
```
In `buildOfferPayload`, replace `contacts: form.contacts || null,` with:
```javascript
    site_url: form.site_url || null,
    article_url: form.article_url || null,
```

- [ ] **Step 4: Update `admin/src/components/OfferForm.vue`**

In `fromInitial`, replace `contacts: o?.contacts || "",` (27) with:
```javascript
    site_url: o?.site_url || "",
    article_url: o?.article_url || "",
```
In the template, replace the `<el-form-item label="Контакти">` block (102–104) with:
```html
    <el-form-item label="Сайт">
      <el-input v-model="form.site_url" placeholder="https://…" />
    </el-form-item>
    <el-form-item label="Сторінка новини">
      <el-input v-model="form.article_url" placeholder="https://…" />
    </el-form-item>
```

- [ ] **Step 5: Run tests**

```bash
npm test -- offerForm
npm test
```
Expected: offerForm spec passes; full admin suite green (fix any test still referencing `contacts`).

- [ ] **Step 6: Commit**

```bash
git add admin/src/components/OfferForm.vue admin/src/utils/offerForm.js admin/src/utils/__tests__/offerForm.spec.js
git commit -m "feat(admin): Сайт/Сторінка новини fields with URL validation"
```

---

### Task 4: Public — card restyle + links + detail links + placeholder colour (TDD)

**Files:**
- Modify: `public/src/components/OfferCard.vue`
- Modify: `public/src/views/OfferDetailView.vue:67`
- Modify: `public/src/utils/placeholder.js:9`
- Create: `public/src/components/__tests__/OfferCard.spec.js` (if a test dir exists; else co-locate per repo convention)

**Interfaces:**
- Consumes: `offer.site_url`, `offer.article_url`, `offer.image_url`, `offer.provider` from the API.
- Produces: card with provider (left) + logo (right) + optional links; detail with links; `#4B5320` placeholder.

- [ ] **Step 1: Write the failing test** — `public/src/components/__tests__/OfferCard.spec.js`

```javascript
import { describe, it, expect } from "vitest";
import { mount, RouterLinkStub } from "@vue/test-utils";
import OfferCard from "@/components/OfferCard.vue";

const offer = {
  id: 1, title: "T", provider: "Кафе", type: "discount",
  site_url: "https://cafe.example", article_url: "https://cafe.example/news",
  target_categories: [],
};

function mountCard(o = offer) {
  return mount(OfferCard, {
    props: { offer: o },
    global: { stubs: { RouterLink: RouterLinkStub, OfferBadge: true } },
  });
}

describe("OfferCard links", () => {
  it("renders Сайт + Сторінка новини links when present", () => {
    const w = mountCard();
    const hrefs = w.findAll("a.card__link").map((a) => a.attributes("href"));
    expect(hrefs).toContain("https://cafe.example");
    expect(hrefs).toContain("https://cafe.example/news");
  });

  it("omits links when absent", () => {
    const w = mountCard({ ...offer, site_url: null, article_url: null });
    expect(w.findAll("a.card__link").length).toBe(0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `public/`):
```bash
npm test -- OfferCard
```
Expected: FAIL — no `.card__link` anchors exist yet.

- [ ] **Step 3: Recolour the placeholder** in `public/src/utils/placeholder.js`

Replace `fill="#1f6feb"` (line 9) with `fill="#4B5320"`.

- [ ] **Step 4: Restyle `public/src/components/OfferCard.vue`**

The card root is currently a `<router-link>` (an `<a>`), so nested link `<a>`s would be invalid. Change the root to a `<div>`, keep an inner `router-link` for navigation, and add the external links separately. Replace the whole `<template>` with:

```html
<template>
  <div class="card">
    <router-link class="card__nav" :to="{ name: 'offer', params: { id: offer.id } }">
      <div class="card__media">
        <img :src="image" alt="" />
        <OfferBadge :offer="offer" class="card__badge" />
      </div>
      <h3 class="card__title">{{ offer.title }}</h3>
    </router-link>
    <div class="card__body">
      <div class="card__head">
        <div class="card__provider">{{ offer.provider }}</div>
        <img class="card__logo" v-if="offer.image_url" :src="offer.image_url" alt="" />
      </div>
      <div v-if="offer.location" class="card__location">{{ offer.location }}</div>
      <div class="card__links">
        <a v-if="offer.site_url" class="card__link" :href="offer.site_url"
           target="_blank" rel="noopener">Сайт</a>
        <a v-if="offer.article_url" class="card__link" :href="offer.article_url"
           target="_blank" rel="noopener">Сторінка новини</a>
      </div>
      <div v-if="offer.target_categories?.length" class="card__tags">
        <span v-for="t in offer.target_categories" :key="t.id" class="tag">{{ t.name }}</span>
      </div>
    </div>
  </div>
</template>
```

Add these style rules inside the existing `<style scoped lang="less">` block (keep the current rules; adjust `.card` colour reset stays):

```less
.card__nav { display: block; color: @text; }
.card__nav:hover { text-decoration: none; }
.card__head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.card__logo { width: 40px; height: 40px; object-fit: contain; border-radius: 6px; flex: none; }
.card__links { margin-top: 8px; display: flex; gap: 12px; }
.card__link { font-size: 13px; }
```

(`provider` sits on the left of `.card__head`, logo on the right — matching the spec.)

- [ ] **Step 5: Add detail links** in `public/src/views/OfferDetailView.vue`

Replace the `contacts` row (line 67):
```html
      <div v-if="offer.contacts" class="detail__row"><span class="detail__label">Контакти:</span> {{ offer.contacts }}</div>
```
with:
```html
      <div v-if="offer.site_url" class="detail__row">
        <span class="detail__label">Сайт:</span>
        <a :href="offer.site_url" target="_blank" rel="noopener">{{ offer.site_url }}</a>
      </div>
      <div v-if="offer.article_url" class="detail__row">
        <span class="detail__label">Сторінка новини:</span>
        <a :href="offer.article_url" target="_blank" rel="noopener">{{ offer.article_url }}</a>
      </div>
```

- [ ] **Step 6: Run tests**

```bash
npm test -- OfferCard
npm test
```
Expected: OfferCard spec passes; full public suite green (fix any test referencing `contacts`/old card markup).

- [ ] **Step 7: Commit**

```bash
git add public/src/components/OfferCard.vue public/src/views/OfferDetailView.vue public/src/utils/placeholder.js public/src/components/__tests__/OfferCard.spec.js
git commit -m "feat(public): card logo-right/provider-left + links, #4B5320 placeholder"
```

---

### Task 5: Public — UAF Memory font

**Files:**
- Create: `public/src/styles/fonts.less`
- Modify: the public entry that loads global styles (`public/src/main.js` — confirm where global Less is imported) + a global `font-family` rule
- Add (already on disk): `public/src/assets/fonts/UAFMemory-{Light,Regular,Medium,Bold,Black}.woff2`

**Interfaces:**
- Produces: `"UAF Memory"` available and applied as the base font.

- [ ] **Step 1: Create `public/src/styles/fonts.less`**

```less
@font-face { font-family: "UAF Memory"; font-weight: 300; font-style: normal; font-display: swap;
  src: url("@/assets/fonts/UAFMemory-Light.woff2") format("woff2"); }
@font-face { font-family: "UAF Memory"; font-weight: 400; font-style: normal; font-display: swap;
  src: url("@/assets/fonts/UAFMemory-Regular.woff2") format("woff2"); }
@font-face { font-family: "UAF Memory"; font-weight: 500; font-style: normal; font-display: swap;
  src: url("@/assets/fonts/UAFMemory-Medium.woff2") format("woff2"); }
@font-face { font-family: "UAF Memory"; font-weight: 700; font-style: normal; font-display: swap;
  src: url("@/assets/fonts/UAFMemory-Bold.woff2") format("woff2"); }
@font-face { font-family: "UAF Memory"; font-weight: 900; font-style: normal; font-display: swap;
  src: url("@/assets/fonts/UAFMemory-Black.woff2") format("woff2"); }

body { font-family: "UAF Memory", system-ui, sans-serif; }
```

> If `@/` doesn't resolve inside `url()` for the project's Vite/Less setup, use a relative path (`../assets/fonts/UAFMemory-Regular.woff2`). Verify by checking the built CSS references the font.

- [ ] **Step 2: Import the font stylesheet globally**

Find where global styles are loaded (check `public/src/main.js` for a `import "./styles/..."` line, or `App.vue`'s `<style>`), and add:
```javascript
import "./styles/fonts.less";
```
If there is no global style import yet, add it in `public/src/main.js` alongside the app bootstrap.

- [ ] **Step 3: Verify the font builds and applies**

```bash
npm run build
```
Expected: build succeeds and emits the woff2 files as assets (grep the `dist/assets` output for `UAFMemory`). If a dev preview is used, computed `font-family` on `body` includes `"UAF Memory"`.

- [ ] **Step 4: Commit (including the font files)**

```bash
git add public/src/styles/fonts.less public/src/main.js public/src/assets/fonts/
git commit -m "feat(public): apply UAF Memory font"
```

---

### Task 6: Crawler — populate site_url / article_url / logo image_url (TDD)

**Files:**
- Modify: `crawler/crawler/models.py` (`RawItem`, `OfferCandidate`)
- Modify: `crawler/crawler/fetchers/website.py` (extract logo, set item fields)
- Modify: `crawler/crawler/extract/heuristic.py` (carry fields onto candidate)
- Modify: `crawler/crawler/runner.py:9` (`offer_payload`)
- Create: `crawler/tests/test_offer_links.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `OfferCandidate.site_url/article_url/image_url`; `offer_payload` includes them; `website.py` fills `RawItem.logo_url` + provides page URL.

- [ ] **Step 1: Write the failing test** — `crawler/tests/test_offer_links.py`

```python
import httpx

from crawler.fetchers.website import WebsiteFetcher, _extract_logo, _origin

PAGE = ('<html><head>'
        '<link rel="apple-touch-icon" href="/touch.png">'
        '<link rel="icon" href="/favicon.ico">'
        '</head><body><article>'
        'Знижка 20% для ветеранів. Діє до 31.12.2026. Завітайте до кафе.'
        '</article></body></html>')


def _client():
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=PAGE)))


def test_origin_derivation():
    assert _origin("https://shop.example.com/news/1") == "https://shop.example.com"


def test_logo_prefers_apple_touch_icon():
    from selectolax.parser import HTMLParser
    tree = HTMLParser(PAGE)
    assert _extract_logo(tree, "https://shop.example.com").endswith("/touch.png")


def test_website_item_has_page_url_and_logo():
    f = WebsiteFetcher(_client())
    items, _ = f.fetch({"id": 1, "type": "website",
                        "url_or_handle": "https://shop.example.com/news"}, None)
    assert items and items[0].url == "https://shop.example.com/news"
    assert items[0].logo_url.endswith("/touch.png")
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `crawler/`):
```bash
./.venv/Scripts/python.exe -m pytest tests/test_offer_links.py -q
```
Expected: FAIL — `_extract_logo`/`_origin` and `RawItem.logo_url` don't exist.

- [ ] **Step 3: Add fields to `crawler/crawler/models.py`**

In `RawItem`, add after `url` (line 18):
```python
    logo_url: str | None = None
```
In `OfferCandidate`, add after `content_hash` (line 33):
```python
    site_url: str | None = None
    article_url: str | None = None
    image_url: str | None = None
```

- [ ] **Step 4: Add logo extraction + origin to `crawler/crawler/fetchers/website.py`**

Add imports at the top:
```python
from urllib.parse import urljoin, urlsplit
```
Add module-level helpers (below `_BLOCK_TAGS`):
```python
def _origin(url: str) -> str:
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}" if p.scheme and p.netloc else ""


def _extract_logo(tree, base_url: str) -> str | None:
    # priority: apple-touch-icon -> og:image -> favicon (rel~=icon)
    for css, attr in (('link[rel="apple-touch-icon"]', "href"),
                      ('meta[property="og:image"]', "content"),
                      ('link[rel="icon"]', "href"),
                      ('link[rel="shortcut icon"]', "href")):
        node = tree.css_first(css)
        if node is not None:
            val = node.attributes.get(attr)
            if val:
                return urljoin(base_url, val)
    return None
```
In `fetch`, after `tree = HTMLParser(resp.text)` (line 26), compute the logo once:
```python
            logo = _extract_logo(tree, url)
```
and set it on each item — change the `RawItem(...)` construction (lines 41–42) to include `logo_url=logo`:
```python
                items.append(RawItem(source_id=source["id"], platform="website",
                                     key=key, text=text, url=url, links=links,
                                     logo_url=logo))
```

- [ ] **Step 5: Carry fields onto the candidate in `crawler/crawler/extract/heuristic.py`**

Add an import at the top:
```python
from urllib.parse import urlsplit
```
In `HeuristicExtractor.extract`, in the `OfferCandidate(...)` return (lines 62–74), add three fields (compute origin from `item.url`):
```python
            site_url=(f"{urlsplit(item.url).scheme}://{urlsplit(item.url).netloc}"
                      if item.url else None),
            article_url=item.url,
            image_url=getattr(item, "logo_url", None),
```

- [ ] **Step 6: Include fields in the payload — `crawler/crawler/runner.py`**

In `offer_payload` (add before the closing `}`):
```python
        "site_url": cand.site_url,
        "article_url": cand.article_url,
        "image_url": cand.image_url,
```

- [ ] **Step 7: Run tests (new + full crawler suite)**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_offer_links.py -q
./.venv/Scripts/python.exe -m pytest -q
```
Expected: new file passes; full crawler suite green.

- [ ] **Step 8: Commit**

```bash
git add crawler/crawler/models.py crawler/crawler/fetchers/website.py crawler/crawler/extract/heuristic.py crawler/crawler/runner.py crawler/tests/test_offer_links.py
git commit -m "feat(crawler): populate site_url/article_url + site-logo image_url"
```

---

### Task 7: End-to-end verification in Docker

**Files:**
- Modify: `docker/fixture/index.html` (add a logo link so the demo shows an image)

**Interfaces:**
- Consumes: everything from Tasks 1–6.

- [ ] **Step 1: Give the fixture a logo**

In `docker/fixture/index.html`, add inside `<head>`:
```html
  <link rel="apple-touch-icon" href="https://dummyimage.com/120x120/4b5320/ffffff.png&text=UBD">
```
(Any reachable image URL works; it only needs to populate `image_url`. If the compose network is offline, use a `data:` URI instead so no external fetch is needed.)

- [ ] **Step 2: Rebuild images and run the demo end-to-end**

```bash
docker compose up -d --build backend
docker compose --profile crawler run --rm --entrypoint python backend -m app.demo_seed
docker compose --profile crawler run --rm --build crawler
docker compose exec -T db mysql -uroot -pmy-secret-pw \
  -e "USE ubd; SELECT id, site_url, article_url, LEFT(image_url,40) AS logo, status FROM offers;" 2>&1 | grep -v Warning
```
Expected: the offer row now has non-null `site_url` (`http://fixture`), `article_url` (`http://fixture/`), and `image_url` (the logo), `status=pending_review`.

- [ ] **Step 3: Visually confirm in public**

Rebuild `public` + `admin`, approve the offer in admin (`:8082`), and confirm the public card (`:8080`) shows provider left / logo right + the links, and the UAF Memory font is applied.
```bash
docker compose up -d --build public admin
```

- [ ] **Step 4: Commit**

```bash
git add docker/fixture/index.html
git commit -m "test(infra): fixture logo for end-to-end offer-links demo"
```

---

## Self-Review

**Spec coverage:**
- `contacts`→`site_url` + `article_url`, migration → Task 1. ✅
- URL validation → Task 2. ✅
- Admin fields «Сайт»/«Сторінка новини» → Task 3. ✅
- Public card logo-right/provider-left + links (card+detail) → Task 4. ✅
- Placeholder `#4B5320` → Task 4 Step 3. ✅
- UAF Memory font → Task 5. ✅
- Crawler populates site_url/article_url/logo → Task 6. ✅
- End-to-end → Task 7. ✅
- Non-goals (search discovery, detail-layout restyle, decorative cuts) → not touched. ✅

**Placeholder scan:** No TBD/TODO. Two integration points are flagged with how to confirm (font `url()` path in Task 5 Step 1; global-style import location in Task 5 Step 2) rather than left vague — acceptable because the exact file is environment-dependent and the check is stated. All code shown inline.

**Type consistency:** `site_url`/`article_url` names match across model (Task 1), schema (Task 2), CRUD (Task 2), admin payload (Task 3), public bindings (Task 4), and crawler payload (Task 6). `RawItem.logo_url` (Task 6 Step 3) matches its use in `website.py` (Step 4) and `heuristic.py` (Step 5). `offer_payload` keys match the backend schema field names. Helper names `_origin`/`_extract_logo` are defined (Task 6 Step 4) before their test use (Step 1). ✅
