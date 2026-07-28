# Offer headline (business-desc title) + card fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Тайтл офера = стабільний бізнес-опис сайту (хедер-tagline → footer-desc → meta description → промо-fallback), `content_hash` лишається на промо-first-sentence (0 churn); public-картка завжди показує тайтл і всі тематики.

**Architecture:** Crawler `WebsiteFetcher` витягує `site_tagline`; `HeuristicExtractor` ставить його як `title`, але `content_hash` рахує з промо-title (розчеплено). Public `OfferCard` завжди показує `card__dtext` і рендерить усі offer_categories чіпсами. Backend/схема/OfferDetailView не чіпаємо.

**Tech Stack:** Python + pytest (crawler); Vue 3 + Vitest (public).

## Global Constraints

- Crawler baseline **433**; public baseline — прогнати `cd public && npm test` для точного числа (нові додаються зверху). Backend/admin не чіпаємо.
- Crawler тести: `cd crawler && ./.venv/Scripts/python.exe -m pytest -q`. Public: `cd public && npm test`; білд `cd public && npm run build` (обовʼязковий).
- **`content_hash` МАЄ лишитися байт-ідентичним** незалежно від `site_tagline` (рахується з `_title_from(text)`, не з дисплейного title) — регрес-замок проти churn наявних оферів.
- Ланцюг тайтла: `.site-description`/`.tagline`/`[class*='slogan']` → `.tb-footer-desc`/`[class*='footer-desc']` → `<meta name="description">` → `_title_from(text)`.
- UI-копірайт українською.

---

### Task 1: `RawItem.site_tagline` + WebsiteFetcher extraction

**Files:**
- Modify: `crawler/crawler/models.py` (RawItem)
- Modify: `crawler/crawler/fetchers/website.py`
- Test: `crawler/tests/test_website_fetcher.py`

**Interfaces:**
- Produces: `RawItem.site_tagline: str | None`; `_extract_site_tagline(tree) -> str | None`; `WebsiteFetcher.fetch` кладе `site_tagline` на кожен RawItem.

- [ ] **Step 1: Write the failing test**

Append to `crawler/tests/test_website_fetcher.py` (reuse its existing fetch/HTMLParser helpers; if it builds a fake client, mirror that):

```python
def test_site_tagline_prefers_header_then_footer_then_meta():
    from crawler.fetchers.website import _extract_site_tagline
    from selectolax.parser import HTMLParser
    header = HTMLParser('<div class="site-description">Хедер слоган</div>'
                        '<div class="tb-footer-desc">Футер опис</div>'
                        '<meta name="description" content="Мета опис">')
    assert _extract_site_tagline(header) == "Хедер слоган"
    footer = HTMLParser('<div class="tb-footer-desc">Футер опис бізнесу</div>'
                        '<meta name="description" content="Мета опис">')
    assert _extract_site_tagline(footer) == "Футер опис бізнесу"
    meta = HTMLParser('<meta name="description" content="Лише мета опис">')
    assert _extract_site_tagline(meta) == "Лише мета опис"
    assert _extract_site_tagline(HTMLParser('<div>нічого</div>')) is None


def test_site_tagline_capped_and_whitespace_normalized():
    from crawler.fetchers.website import _extract_site_tagline
    from selectolax.parser import HTMLParser
    long = "слово " * 60
    out = _extract_site_tagline(HTMLParser(f'<meta name="description" content="{long}">'))
    assert out is not None and len(out) <= 160 and "  " not in out


def test_fetch_puts_site_tagline_on_items():
    import httpx
    from crawler.fetchers.website import WebsiteFetcher
    html = ('<html><head><meta name="description" content="Опис магазину"></head>'
            '<body><p>Знижка 15% для ветеранів у нашому магазині завжди діє тут.</p></body></html>')
    transport = httpx.MockTransport(lambda req: httpx.Response(200, text=html))
    fetcher = WebsiteFetcher(httpx.Client(transport=transport))
    items, _ = fetcher.fetch({"id": 1, "url_or_handle": "https://biz.example"}, None)
    assert items and items[0].site_tagline == "Опис магазину"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_website_fetcher.py -k "site_tagline or puts_site_tagline" -v`
Expected: FAIL — `_extract_site_tagline` undefined; RawItem has no `site_tagline`.

- [ ] **Step 3: Add `site_tagline` to RawItem**

In `crawler/crawler/models.py`, in the `RawItem` dataclass, after `site_name: str | None = None` (line 21) add:

```python
    site_tagline: str | None = None
```

- [ ] **Step 4: Add extraction to website.py**

In `crawler/crawler/fetchers/website.py`, after `_extract_site_name` (around line 47) add:

```python
_TAGLINE_SELECTORS = (
    ".site-description", ".tagline", "[class*='slogan']",   # header near-logo tagline
    ".tb-footer-desc", "[class*='footer-desc']",            # footer business description
)


def _cap_tagline(s: str, n: int = 160) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else (s[:n].rsplit(" ", 1)[0] or s[:n])


def _extract_site_tagline(tree) -> str | None:
    for css in _TAGLINE_SELECTORS:
        node = tree.css_first(css)
        if node is not None:
            txt = node.text(separator=" ", strip=True)
            if txt:
                return _cap_tagline(txt)
    node = tree.css_first('meta[name="description"]')
    if node is not None:
        txt = (node.attributes.get("content") or "").strip()
        if txt:
            return _cap_tagline(txt)
    return None
```

Then in `WebsiteFetcher.fetch`, after `site_name = _extract_site_name(tree)` (line 162) add:

```python
            site_tagline = _extract_site_tagline(tree)
```

and in the `RawItem(...)` construction (lines 181-186), add `site_tagline=site_tagline,` alongside `site_name=site_name,`:

```python
                items.append(RawItem(source_id=source["id"], platform="website",
                                     key=key, text=text, url=url, links=links,
                                     logo_url=logo, site_name=site_name,
                                     site_tagline=site_tagline,
                                     locality=locality, has_offer_schema=has_offer,
                                     is_article=is_article,
                                     has_business_schema=has_business))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_website_fetcher.py -v`
Expected: PASS (new + existing).

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/models.py crawler/crawler/fetchers/website.py crawler/tests/test_website_fetcher.py
git commit -m "feat(crawler): extract site_tagline (business desc) in WebsiteFetcher"
```

---

### Task 2: heuristic uses site_tagline for title; content_hash decoupled

**Files:**
- Modify: `crawler/crawler/extract/heuristic.py`
- Test: `crawler/tests/test_heuristic.py`

**Interfaces:**
- Consumes: `RawItem.site_tagline` (Task 1).
- Produces: `OfferCandidate.title = item.site_tagline or _title_from(text)`; `content_hash` computed from `_title_from(text)` (unchanged basis).

- [ ] **Step 1: Write the failing tests**

Append to `crawler/tests/test_heuristic.py` (reuse `_target_cats`, `CategoryIndex`, `RawItem`, `HeuristicExtractor` already imported there):

```python
def test_title_uses_site_tagline_when_present():
    ex = HeuristicExtractor()
    item = RawItem(source_id=1, platform="website", key="k",
                   text="Знижка 15% для ветеранів у нашому магазині",
                   site_tagline="Магазин тактичного спорядження")
    res = ex.extract(item, "P", CategoryIndex(target=[{"id": 10, "slug": "veteran"}], offer=[]))
    assert res is not None
    assert res.title == "Магазин тактичного спорядження"


def test_title_falls_back_to_promo_when_no_tagline():
    ex = HeuristicExtractor()
    item = RawItem(source_id=1, platform="website", key="k",
                   text="Знижка 15% для ветеранів у нашому магазині")
    res = ex.extract(item, "P", CategoryIndex(target=[{"id": 10, "slug": "veteran"}], offer=[]))
    assert res is not None
    assert res.title == "Знижка 15% для ветеранів у нашому магазині"


def test_content_hash_ignores_site_tagline():
    ex = HeuristicExtractor()
    cats = CategoryIndex(target=[{"id": 10, "slug": "veteran"}], offer=[])
    text = "Знижка 15% для ветеранів у нашому магазині"
    a = ex.extract(RawItem(source_id=1, platform="website", key="k", text=text,
                           site_tagline="Опис А"), "P", cats)
    b = ex.extract(RawItem(source_id=1, platform="website", key="k", text=text,
                           site_tagline="Опис Б"), "P", cats)
    assert a.content_hash == b.content_hash          # hash decoupled from tagline (no churn)
    assert a.title == "Опис А" and b.title == "Опис Б"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_heuristic.py -k "site_tagline or falls_back_to_promo or content_hash_ignores" -v`
Expected: FAIL — title currently always `_title_from(text)`.

- [ ] **Step 3: Implement in heuristic.py**

In `crawler/crawler/extract/heuristic.py`, in `HeuristicExtractor.extract`, replace the title line (currently `title = _title_from(text)`, line ~90):

```python
        promo_title = _title_from(text)
        title = (item.site_tagline or "").strip() or promo_title
```

And in the `OfferCandidate(...)` construction, change the `content_hash` argument (currently `content_hash=content_hash(title, provider, text)`, line ~101) to use `promo_title`:

```python
            content_hash=content_hash(promo_title, provider, text),
```

(Leave `title=title,` as-is — it now carries the display headline. Everything else unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_heuristic.py -v`
Expected: PASS (new + existing — existing tests build RawItem without site_tagline, so title == promo, content_hash unchanged).

- [ ] **Step 5: Run full crawler suite (churn-guard regression)**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest -q`
Expected: all green — baseline 433 + Task 1 + Task 2 new tests. (Any test asserting a specific `content_hash` or `title` on tagline-less RawItems must be unaffected — title still == promo when no tagline.)

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/extract/heuristic.py crawler/tests/test_heuristic.py
git commit -m "feat(crawler): offer title from site_tagline; content_hash stays on promo title"
```

---

### Task 3: public OfferCard — always show dtext + all category chips

**Files:**
- Modify: `public/src/components/OfferCard.vue`
- Test: `public/tests/components/OfferCard.test.js`

**Interfaces:**
- Consumes: `offer.title` (now business-desc), `offer.offer_categories`.

- [ ] **Step 1: Write the failing tests**

Append these `it(...)` blocks inside `describe("OfferCard", ...)` in `public/tests/components/OfferCard.test.js`:

```javascript
  it("renders all offer_categories as chips", () => {
    const w = mountCard({
      id: 11, type: "discount", title: "Бізнес-опис", provider: "P", description: "d",
      image_url: null, target_categories: [],
      offer_categories: [{ id: 2, name: "Кафе" }, { id: 3, name: "Спорт" }],
    });
    expect(w.text()).toContain("Кафе");
    expect(w.text()).toContain("Спорт");
  });

  it("always shows card__dtext when title is present, even if description repeats it", () => {
    const w = mountCard({
      id: 12, type: "discount", title: "Знижка для ЗСУ", provider: "P",
      description: "Знижка для ЗСУ та ще купа тексту опису", image_url: null,
      target_categories: [], offer_categories: [],
    });
    expect(w.find(".card__dtext").exists()).toBe(true);
    expect(w.get(".card__dtext").text()).toBe("Знижка для ЗСУ");
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd public && npx vitest run tests/components/OfferCard.test.js`
Expected: FAIL — dtext hidden when description starts with title (showTitle dedup); second offer_category not rendered (meta uses `[0]`).

- [ ] **Step 3: Implement in OfferCard.vue**

1. Replace the `meta` computed (lines 15-17) so it no longer includes the category — location only:

```javascript
const meta = computed(() => props.offer.location || "");
```

2. Remove the `showTitle` computed (lines 18-25) entirely (and the local `norm` helper it defines).

3. Change the `card__dtext` span (line 37) from `v-if="showTitle"` to `v-if="offer.title"`:

```html
      <span v-if="offer.title" class="card__dtext">{{ offer.title }}</span>
```

4. Add a "Тематика" chips block after the `card__whom` block (after line 50), mirroring it:

```html
    <div v-if="offer.offer_categories?.length" class="card__whom">
      <div class="card__whom-label">Тематика</div>
      <div class="card__chips">
        <span v-for="c in offer.offer_categories" :key="c.id" class="chip">{{ c.name }}</span>
      </div>
    </div>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd public && npx vitest run tests/components/OfferCard.test.js`
Expected: PASS (new + existing OfferCard tests).

- [ ] **Step 5: Full public suite + build**

Run: `cd public && npm test`
Expected: all green (baseline + new).

Run: `cd public && npm run build`
Expected: build succeeds.

- [ ] **Step 6: Commit**

```bash
git add public/src/components/OfferCard.vue public/tests/components/OfferCard.test.js
git commit -m "feat(public): OfferCard always shows headline + all category chips"
```

---

## Self-Review

**Spec coverage:**
- Компонент A (site_tagline chain + RawItem + heuristic title + content_hash decouple) → Tasks 1–2 ✅
- Компонент B (OfferCard always-dtext + category chips) → Task 3 ✅
- content_hash churn-guard → Task 2 `test_content_hash_ignores_site_tagline` + full-suite run ✅
- OfferDetailView non-scope (already correct) ✅

**Placeholder scan:** конкретний код/тести в кожному кроці; плейсхолдерів нема.

**Type consistency:** `site_tagline`, `_extract_site_tagline`, `_cap_tagline`, `promo_title` — узгоджені між Tasks 1–2; `offer.title`/`offer_categories` — стандартні public-поля.
