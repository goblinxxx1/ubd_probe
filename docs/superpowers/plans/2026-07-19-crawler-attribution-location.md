# Crawler attribution + location + card de-dup — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop media/gov/stock/social pages becoming fake providers, fill business city into `Offer.location`, and stop the public card showing title and description as identical text.

**Architecture:** Three coordinated changes on one branch. A new host blocklist + narrowed rules harden `attribution.py`. A new gazetteer plus structured-data extraction in the website fetcher fill `location` (backend + admin already support it). A front-guard in `OfferCard.vue` plus a cleaner crawler title fix the visible duplication.

**Tech Stack:** Python 3.12 (crawler, pytest, httpx.MockTransport, selectolax), Vue 3 + Vitest (public).

## Global Constraints

- Zero-cost, offline, **no cloud LLM** — crawler uses only heuristics/local parsing.
- Crawler tests run offline from `crawler/`; public tests + `npm run build` from `public/`.
- Ukrainian UI copy; communicate in Ukrainian.
- `content_hash` identity semantics are owned by the backend; do not add `location` to it.

---

### Task 1: Host blocklist module

**Files:**
- Create: `crawler/crawler/discovery/blocklist.py`
- Test: `crawler/tests/test_blocklist.py`

**Interfaces:**
- Produces: `is_blocked_host(host: str | None) -> bool`

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_blocklist.py
from crawler.discovery.blocklist import is_blocked_host


def test_exact_media_host_blocked():
    assert is_blocked_host("nv.ua")


def test_subdomain_suffix_blocked():
    assert is_blocked_host("biz.nv.ua")
    assert is_blocked_host("ua.depositphotos.com")


def test_gov_ua_tld_blocked():
    assert is_blocked_host("zakon.rada.gov.ua")
    assert is_blocked_host("nszu.gov.ua")


def test_www_prefix_ignored():
    assert is_blocked_host("www.tiktok.com")


def test_business_host_not_blocked():
    assert not is_blocked_host("yourburger.example")


def test_none_and_empty_not_blocked():
    assert not is_blocked_host(None)
    assert not is_blocked_host("")


def test_lookalike_not_blocked():
    # must not match "nv.ua" as a bare substring
    assert not is_blocked_host("mynv.ua")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crawler && python -m pytest tests/test_blocklist.py -q`
Expected: FAIL — `ModuleNotFoundError: crawler.discovery.blocklist`

- [ ] **Step 3: Write minimal implementation**

```python
# crawler/crawler/discovery/blocklist.py
"""Hosts that must never be attributed as offer providers or offer sources:
news media, government, stock-photo banks, social-video aggregators."""

_MEDIA = {
    "nv.ua", "24tv.ua", "061.ua", "pravda.com.ua", "unian.ua", "tsn.ua",
    "rbc.ua", "censor.net", "obozrevatel.com", "segodnya.ua",
}
_STOCK = {"depositphotos.com", "shutterstock.com", "istockphoto.com", "freepik.com"}
_SOCIAL = {
    "tiktok.com", "youtube.com", "youtu.be", "pinterest.com",
    "twitter.com", "x.com",
}
_BLOCKED = _MEDIA | _STOCK | _SOCIAL


def is_blocked_host(host: str | None) -> bool:
    if not host:
        return False
    host = host.strip().lower().removeprefix("www.")
    if not host:
        return False
    if host == "gov.ua" or host.endswith(".gov.ua"):
        return True
    return any(host == d or host.endswith("." + d) for d in _BLOCKED)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd crawler && python -m pytest tests/test_blocklist.py -q`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/blocklist.py crawler/tests/test_blocklist.py
git commit -m "feat(crawler): host blocklist for media/gov/stock/social"
```

---

### Task 2: Harden attribution

**Files:**
- Modify: `crawler/crawler/discovery/attribution.py` (function `attribute`, add import)
- Test: `crawler/tests/test_attribution.py` (update one, add three)

**Interfaces:**
- Consumes: `is_blocked_host` from Task 1; existing `attribute(item, ctx)`, `PageCtx`.
- Produces: unchanged `attribute` signature; new behavior — blocked page host → `None`; blocked external link ignored; rule 3 requires `offer_block_count <= 1`.

- [ ] **Step 1: Update the existing rule-3 test and add new failing tests**

In `crawler/tests/test_attribution.py`, change `test_single_business_page_first_party` to use `offer_block_count=1` (was `2`):

```python
def test_single_business_page_first_party():
    item = _item("Знижка 10% ветеранам", site_name="Shop")
    ctx = PageCtx(cand_type="website", cand_name="Shop",
                  cand_url_or_handle="https://shop.example",
                  brand="Shop", host="shop.example", offer_block_count=1)
    a = attribute(item, ctx)
    assert a.is_first_party and a.provider == "Shop"
```

Append:

```python
def test_rule3_two_blocks_no_longer_first_party():
    item = _item("Знижка 10% ветеранам", site_name="Shop")
    ctx = PageCtx(cand_type="website", cand_name="Shop",
                  cand_url_or_handle="https://shop.example",
                  brand="Shop", host="shop.example", offer_block_count=2)
    assert attribute(item, ctx) is None


def test_blocked_page_host_returns_none():
    item = _item("У нас знижка 10% для УБД", site_name="НВ Бізнес")
    ctx = PageCtx(cand_type="website", cand_name="НВ",
                  cand_url_or_handle="https://biz.nv.ua/x",
                  brand="НВ Бізнес", host="biz.nv.ua", offer_block_count=1)
    assert attribute(item, ctx) is None


def test_blocked_external_link_ignored():
    item = _item("Дивіться відео про знижки військовим",
                 links=["https://vm.tiktok.com/abc"], site_name="Portal")
    ctx = PageCtx(cand_type="website", cand_name="Portal",
                  cand_url_or_handle="https://portal.example",
                  brand="Portal", host="portal.example", offer_block_count=9)
    # tiktok link must not become a provider; nothing else qualifies → None
    assert attribute(item, ctx) is None
```

- [ ] **Step 2: Run tests to verify failures**

Run: `cd crawler && python -m pytest tests/test_attribution.py -q`
Expected: FAIL — `test_rule3_two_blocks_no_longer_first_party`, `test_blocked_page_host_returns_none`, `test_blocked_external_link_ignored` fail (old code still attributes).

- [ ] **Step 3: Implement the attribution changes**

Add import near the top of `attribution.py`:

```python
from crawler.discovery.blocklist import is_blocked_host
```

Replace the body of `attribute` after the telegram branch with:

```python
    # media/gov/stock/social page is never a provider
    if is_blocked_host(ctx.host):
        return None

    low = (item.text or "").lower()
    # 1. first-party via first-person marker (wins over an outbound link)
    if _FIRST_PERSON.search(low) and ctx.brand:
        return _first_party(ctx)
    # 2. third-party via an external business link (skip blocked targets)
    ext = _pick_target(getattr(item, "links", None), item.url or "")
    if ext and not is_blocked_host(_host(ext)):
        host = _host(ext) or ext
        return Attribution(provider=host, is_first_party=False,
                           suggest_type="website", suggest_url_or_handle=_origin(ext),
                           suggest_name=host)
    # 3. first-party via a single-business page (narrowed: essentially one block)
    if ctx.offer_block_count <= 1 and ctx.brand:
        return _first_party(ctx)
    # 4. generic info -> no attributable provider
    return None
```

- [ ] **Step 4: Run the whole attribution suite**

Run: `cd crawler && python -m pytest tests/test_attribution.py -q`
Expected: PASS (all, including the unchanged first-person/third-party/telegram/generic tests)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/attribution.py crawler/tests/test_attribution.py
git commit -m "feat(crawler): block media/gov/stock/social from attribution, narrow rule 3 to N<=1"
```

---

### Task 3: City gazetteer

**Files:**
- Create: `crawler/crawler/discovery/geo.py`
- Test: `crawler/tests/test_geo.py`

**Interfaces:**
- Produces: `find_city(text: str | None) -> str | None` — canonical nominative city name or None.

- [ ] **Step 1: Write the failing test**

```python
# crawler/tests/test_geo.py
from crawler.discovery.geo import find_city


def test_nominative_match():
    assert find_city("Знижка діє у місті Львів") == "Львів"


def test_locative_inflection():
    assert find_city("Наша кав'ярня у Києві") == "Київ"


def test_genitive_inflection():
    assert find_city("Акція для мешканців Одеси") == "Одеса"


def test_multiword_city():
    assert find_city("м. Біла Церква, вул. Шевченка") == "Біла Церква"


def test_no_city_returns_none():
    assert find_city("Знижка для військових") is None
    assert find_city(None) is None
    assert find_city("") is None


def test_word_boundary_avoids_false_match():
    # "рівні" (level) must not match the city Рівне
    assert find_city("сервіс на рівні найкращих") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crawler && python -m pytest tests/test_geo.py -q`
Expected: FAIL — `ModuleNotFoundError: crawler.discovery.geo`

- [ ] **Step 3: Write minimal implementation**

```python
# crawler/crawler/discovery/geo.py
"""Offline gazetteer: map Ukrainian city surface forms to a canonical name.

Precision over recall — only curated cities match, via explicit surface forms
(nominative + common oblique cases) with word boundaries, so inflected mentions
are caught without stemming collisions (e.g. `рівні` != `Рівне`)."""

import re

# canonical -> lowercase surface forms (nominative + common oblique cases)
_CITIES = {
    "Київ": ("київ", "києві", "києва"),
    "Львів": ("львів", "львові", "львова"),
    "Харків": ("харків", "харкові", "харкова"),
    "Одеса": ("одеса", "одесі", "одеси"),
    "Дніпро": ("дніпро", "дніпрі", "дніпра"),
    "Запоріжжя": ("запоріжжя", "запоріжжі"),
    "Вінниця": ("вінниця", "вінниці"),
    "Полтава": ("полтава", "полтаві", "полтави"),
    "Чернігів": ("чернігів", "чернігові", "чернігова"),
    "Черкаси": ("черкаси", "черкасах", "черкас"),
    "Житомир": ("житомир", "житомирі", "житомира"),
    "Суми": ("суми", "сумах"),
    "Рівне": ("рівне", "рівному", "рівного"),
    "Івано-Франківськ": ("івано-франківськ", "івано-франківську", "івано-франківська"),
    "Тернопіль": ("тернопіль", "тернополі", "тернополя"),
    "Луцьк": ("луцьк", "луцьку", "луцька"),
    "Ужгород": ("ужгород", "ужгороді", "ужгорода"),
    "Хмельницький": ("хмельницький", "хмельницькому"),
    "Чернівці": ("чернівці", "чернівцях"),
    "Кропивницький": ("кропивницький", "кропивницькому"),
    "Миколаїв": ("миколаїв", "миколаєві", "миколаєва"),
    "Херсон": ("херсон", "херсоні", "херсона"),
    "Маріуполь": ("маріуполь", "маріуполі", "маріуполя"),
    "Краматорськ": ("краматорськ", "краматорську", "краматорська"),
    "Біла Церква": ("біла церква", "білій церкві", "білої церкви"),
}

# (form, canonical), longest form first so specific forms win
_FORMS = sorted(
    ((form, city) for city, forms in _CITIES.items() for form in forms),
    key=lambda fc: len(fc[0]), reverse=True,
)
_PATTERNS = [(re.compile(r"(?<!\w)" + re.escape(f) + r"(?!\w)"), c) for f, c in _FORMS]


def find_city(text: str | None) -> str | None:
    if not text:
        return None
    low = text.lower()
    for pat, city in _PATTERNS:
        if pat.search(low):
            return city
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd crawler && python -m pytest tests/test_geo.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/geo.py crawler/tests/test_geo.py
git commit -m "feat(crawler): offline Ukrainian city gazetteer"
```

---

### Task 4: RawItem.locality + website fetcher structured locality

**Files:**
- Modify: `crawler/crawler/models.py` (add field to `RawItem`)
- Modify: `crawler/crawler/fetchers/website.py` (add `_extract_locality` + `_locality_from_jsonld`, wire into `fetch`)
- Test: `crawler/tests/test_website_fetcher.py` (add three)

**Interfaces:**
- Produces: `RawItem.locality: str | None` (default `None`); every `RawItem` a website page emits carries the page-level locality.

- [ ] **Step 1: Write the failing tests**

Append to `crawler/tests/test_website_fetcher.py`:

```python
def test_website_locality_from_jsonld():
    html = ('<html><head><script type="application/ld+json">'
            '{"@type":"Restaurant","address":{"@type":"PostalAddress",'
            '"addressLocality":"Львів"}}</script></head><body>'
            '<article><p>Знижка 15% для ветеранів на каву у нас сьогодні.</p>'
            '</article></body></html>')

    def handle(request):
        return httpx.Response(200, text=html)

    f = WebsiteFetcher(httpx.Client(transport=httpx.MockTransport(handle)))
    items, _ = f.fetch({"id": 1, "url_or_handle": "http://x"}, None)
    assert items and all(i.locality == "Львів" for i in items)


def test_website_locality_from_og_meta():
    html = ('<html><head><meta property="og:locality" content="Одеса"></head>'
            '<body><article><p>Знижка 15% для ветеранів на каву у нас сьогодні.'
            '</p></article></body></html>')

    def handle(request):
        return httpx.Response(200, text=html)

    f = WebsiteFetcher(httpx.Client(transport=httpx.MockTransport(handle)))
    items, _ = f.fetch({"id": 1, "url_or_handle": "http://x"}, None)
    assert items and all(i.locality == "Одеса" for i in items)


def test_website_locality_absent_is_none():
    f = WebsiteFetcher(_client())
    items, _ = f.fetch({"id": 1, "url_or_handle": "http://x"}, None)
    assert items and all(i.locality is None for i in items)
```

- [ ] **Step 2: Run tests to verify failures**

Run: `cd crawler && python -m pytest tests/test_website_fetcher.py -q`
Expected: FAIL — `AttributeError: 'RawItem' object has no attribute 'locality'` / assertion errors.

- [ ] **Step 3: Add the `locality` field to `RawItem`**

In `crawler/crawler/models.py`, in the `RawItem` dataclass, add after `site_name`:

```python
    locality: str | None = None
```

- [ ] **Step 4: Implement locality extraction in the website fetcher**

At the top of `crawler/crawler/fetchers/website.py` add `import json` (with the existing imports). Add these two helpers near `_extract_site_name`:

```python
def _locality_from_jsonld(data) -> str | None:
    if isinstance(data, dict):
        addr = data.get("address")
        if isinstance(addr, dict):
            loc = addr.get("addressLocality")
            if isinstance(loc, str) and loc.strip():
                return loc.strip()
        if isinstance(addr, list):
            for a in addr:
                if isinstance(a, dict):
                    loc = a.get("addressLocality")
                    if isinstance(loc, str) and loc.strip():
                        return loc.strip()
        loc = data.get("addressLocality")
        if isinstance(loc, str) and loc.strip():
            return loc.strip()
        for key in ("@graph", "itemListElement"):
            if key in data:
                found = _locality_from_jsonld(data[key])
                if found:
                    return found
    elif isinstance(data, list):
        for entry in data:
            found = _locality_from_jsonld(entry)
            if found:
                return found
    return None


def _extract_locality(tree) -> str | None:
    for node in tree.css('script[type="application/ld+json"]'):
        raw = node.text()
        if not raw or not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            continue
        loc = _locality_from_jsonld(data)
        if loc:
            return loc
    node = tree.css_first('meta[property="business:contact_data:locality"]')
    if node is not None and node.attributes.get("content"):
        return node.attributes["content"].strip()
    for css in ('meta[property="og:locality"]', 'meta[name="geo.placename"]'):
        node = tree.css_first(css)
        if node is not None and node.attributes.get("content"):
            return node.attributes["content"].strip()
    return None
```

In `WebsiteFetcher.fetch`, after `site_name = _extract_site_name(tree)` add:

```python
            locality = _extract_locality(tree)
```

and add `locality=locality` to the `RawItem(...)` constructor call inside the loop:

```python
                items.append(RawItem(source_id=source["id"], platform="website",
                                     key=key, text=text, url=url, links=links,
                                     logo_url=logo, site_name=site_name,
                                     locality=locality))
```

- [ ] **Step 5: Run the website fetcher suite**

Run: `cd crawler && python -m pytest tests/test_website_fetcher.py -q`
Expected: PASS (existing + 3 new)

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/models.py crawler/crawler/fetchers/website.py crawler/tests/test_website_fetcher.py
git commit -m "feat(crawler): extract page-level business locality (JSON-LD/og/geo)"
```

---

### Task 5: Offer location + concise title in the extractor

**Files:**
- Modify: `crawler/crawler/models.py` (add `location` to `OfferCandidate`)
- Modify: `crawler/crawler/extract/heuristic.py` (`_title_from`, set `location`)
- Modify: `crawler/crawler/payloads.py` (`offer_payload` includes `location`)
- Test: `crawler/tests/test_heuristic.py` (add four), `crawler/tests/test_payloads.py` (create)

**Interfaces:**
- Consumes: `find_city` (Task 3); `RawItem.locality` (Task 4).
- Produces: `OfferCandidate.location: str | None`; `offer_payload(cand)["location"]`; `title` is a concise headline (first sentence, ≤80 chars on a word boundary).

- [ ] **Step 1: Write the failing tests**

Append to `crawler/tests/test_heuristic.py`:

```python
def test_location_from_structured_locality():
    it = RawItem(source_id=1, platform="website", key="k",
                 text="Знижка 20% для ветеранів у кафе", locality="Львів")
    cand = get_extractor("heuristic").extract(it, "Кафе", CATS)
    assert cand.location == "Львів"


def test_location_from_gazetteer_fallback():
    cand = get_extractor("heuristic").extract(
        _item("Знижка 20% для ветеранів у нашому кафе в Одесі"), "Кафе", CATS)
    assert cand.location == "Одеса"


def test_location_none_when_absent():
    cand = get_extractor("heuristic").extract(
        _item("Знижка 20% для ветеранів"), "Кафе", CATS)
    assert cand.location is None


def test_title_is_concise_headline():
    text = ("Знижка 20% для ветеранів. Пропозиція діє у нашому кафе протягом "
            "усього місяця на всі напої та десерти без винятку сьогодні.")
    cand = get_extractor("heuristic").extract(_item(text), "Кафе", CATS)
    assert cand.title == "Знижка 20% для ветеранів."
    assert cand.body == text  # description keeps the full text
```

Create `crawler/tests/test_payloads.py`:

```python
from datetime import date

from crawler.models import OfferCandidate
from crawler.payloads import offer_payload


def test_offer_payload_includes_location():
    cand = OfferCandidate(source_id=None, title="T", provider="P", body="B",
                          location="Львів")
    assert offer_payload(cand)["location"] == "Львів"


def test_offer_payload_location_defaults_none():
    cand = OfferCandidate(source_id=None, title="T", provider="P", body="B")
    assert offer_payload(cand)["location"] is None
```

- [ ] **Step 2: Run tests to verify failures**

Run: `cd crawler && python -m pytest tests/test_heuristic.py tests/test_payloads.py -q`
Expected: FAIL — `OfferCandidate` has no `location`; `title` assertion mismatch; payload missing `location`.

- [ ] **Step 3: Add `location` to `OfferCandidate`**

In `crawler/crawler/models.py`, in `OfferCandidate`, add after `body`:

```python
    location: str | None = None
```

- [ ] **Step 4: Update the extractor**

In `crawler/crawler/extract/heuristic.py` add imports:

```python
from crawler.discovery.geo import find_city
```

Replace `_title_from` with a concise-headline version:

```python
_SENT_END = re.compile(r"(?<=[.!?…])\s")


def _title_from(text: str) -> str:
    t = text.strip()
    if not t:
        return t
    first = t.splitlines()[0]
    m = _SENT_END.search(first)
    if m:
        first = first[:m.start() + 1]
    if len(first) > 80:
        first = first[:80].rsplit(" ", 1)[0] or first[:80]
    return first.strip()
```

In `HeuristicExtractor.extract`, add `location` to the returned `OfferCandidate(...)`:

```python
            location=item.locality or find_city(text),
```

(place it alongside the other keyword args, e.g. right after `body=text,`).

- [ ] **Step 5: Add `location` to the offer payload**

In `crawler/crawler/payloads.py`, in `offer_payload`, add:

```python
        "location": cand.location,
```

(place it next to `"provider": cand.provider,`).

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd crawler && python -m pytest tests/test_heuristic.py tests/test_payloads.py -q`
Expected: PASS

- [ ] **Step 7: Run the full crawler suite**

Run: `cd crawler && python -m pytest -q`
Expected: PASS (all previously-passing tests + new ones)

- [ ] **Step 8: Commit**

```bash
git add crawler/crawler/models.py crawler/crawler/extract/heuristic.py crawler/crawler/payloads.py crawler/tests/test_heuristic.py crawler/tests/test_payloads.py
git commit -m "feat(crawler): fill Offer.location and emit a concise title"
```

---

### Task 6: Public card — hide duplicate title

**Files:**
- Modify: `public/src/components/OfferCard.vue` (compute `showTitle`, guard `card__dtext`)
- Test: `public/tests/components/OfferCard.test.js` (add three)

**Interfaces:**
- Produces: `card__dtext` renders only when the title is not a leading duplicate of the description.

- [ ] **Step 1: Write the failing tests**

Append inside the `describe("OfferCard", ...)` block in `public/tests/components/OfferCard.test.js`:

```javascript
  it("hides the discount-title when it equals the description", () => {
    const w = mountCard({
      id: 10, type: "discount", title: "Знижка 20% для ветеранів",
      provider: "P", description: "Знижка 20% для ветеранів",
      image_url: null, target_categories: [],
    });
    expect(w.find(".card__dtext").exists()).toBe(false);
  });

  it("hides the discount-title when the description starts with it", () => {
    const w = mountCard({
      id: 11, type: "discount", title: "Знижка 20%",
      provider: "P", description: "Знижка 20% для ветеранів у нашому кафе",
      image_url: null, target_categories: [],
    });
    expect(w.find(".card__dtext").exists()).toBe(false);
  });

  it("shows the discount-title when it is distinct from the description", () => {
    const w = mountCard({
      id: 12, type: "discount", title: "на все меню",
      provider: "P", description: "Крафтова бургерна у центрі міста",
      image_url: null, target_categories: [],
    });
    expect(w.get(".card__dtext").text()).toBe("на все меню");
  });
```

- [ ] **Step 2: Run tests to verify failures**

Run: `cd public && npx vitest run tests/components/OfferCard.test.js`
Expected: FAIL — the first two (dtext still rendered).

- [ ] **Step 3: Implement the front-guard**

In `public/src/components/OfferCard.vue` `<script setup>`, add a computed after `meta`:

```javascript
const showTitle = computed(() => {
  const t = (props.offer.title || "").trim();
  if (!t) return false;
  const d = (props.offer.description || "").trim();
  if (!d) return true;
  const norm = (s) => s.toLowerCase().replace(/\s+/g, " ");
  return !norm(d).startsWith(norm(t));
});
```

In the template, change the `card__dtext` line from `v-if="offer.title"` to `v-if="showTitle"`:

```html
      <span v-if="showTitle" class="card__dtext">{{ offer.title }}</span>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd public && npx vitest run tests/components/OfferCard.test.js`
Expected: PASS (existing + 3 new)

- [ ] **Step 5: Full public test + build (scoped-Less regressions escape Vitest)**

Run: `cd public && npx vitest run && npm run build`
Expected: all tests PASS; build succeeds.

- [ ] **Step 6: Commit**

```bash
git add public/src/components/OfferCard.vue public/tests/components/OfferCard.test.js
git commit -m "fix(public): hide offer card title when it duplicates the description"
```

---

## Final verification (after all tasks)

- [ ] `cd crawler && python -m pytest -q` — all green.
- [ ] `cd public && npx vitest run && npm run build` — all green, build OK.
- [ ] (Optional, if MySQL container up) `cd backend && python -m pytest -q` — unchanged, still green.
- [ ] Update memory `ubd-crawler-discovery-redesign.md` with the attribution-precision + location outcome; note remaining follow-ups (news Telegram channels; IG/FB).
- [ ] Merge to `main` per workflow (see `superpowers:finishing-a-development-branch`).
