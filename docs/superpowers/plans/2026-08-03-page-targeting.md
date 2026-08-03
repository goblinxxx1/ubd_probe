# Якісний добір сторінок крола (page-targeting) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Замінити вузький `url_is_promo` у DomainWalker на курувану таксономію цільових типів сторінок (URL-слаг + текст лінка, з пріоритетом відсіку), щоб walker (і active search через нього) фетчив лише високоврожайні типи сторінок і відсікав товари/кошик/блог.

**Architecture:** Новий класифікатор `page_is_target`/`is_excluded`/`seed_is_target` у `promo_lexicon.py` (поряд із незмінним `url_is_promo`). Walker перемикає sitemap-фільтр і BFS на нього (BFS: excluded→skip, target→collect, neutral→frontier; `_links` віддає `(url, anchor)`), а seed/candidate-URL фетчиться лише якщо це корінь домену або target. Active search автоматично успадковує зміну (harvester обходить домени тим самим walker'ом); no-walker fallback теж під seed-гейтом.

**Tech Stack:** Python 3, pytest, selectolax (HTML-парсер). Пакет `crawler/crawler/`, тести `crawler/tests/`.

## Global Constraints

- Джерело сигналу: URL-слаг (substring по decoded path, lower) + текст лінка (анкор); **EXCLUDE перемагає INCLUDE**.
- Таксономія **курована в коді**, **без config-ручки**.
- `url_is_promo` та його наявні тести (`test_promo_url_filter.py`, `test_promo_lexicon.py`) — **не змінювати** (промо = підмножина target).
- Seed/candidate-URL фетчиться-як-ціль лише якщо `is_domain_root(url)` (path у `("", "/")`) **або** `page_is_target(url)`. Passive (корінь) — незмінний.
- Якість тримає downstream discount-гейт; `page_cap`/politeness/sitemap_max_docs/bfs_max_* — не чіпати.
- Тести крола (з `crawler/`): `./.venv/Scripts/python.exe -m pytest -q` (без мережі/БД).
- TDD, часті коміти, українською.

---

### Task 1: Класифікатор `page_is_target` + таксономія

**Files:**
- Modify: `crawler/crawler/discovery/promo_lexicon.py` (додати після `url_is_promo`, ~рядок 62)
- Test: `crawler/tests/test_page_types.py`

**Interfaces:**
- Consumes: наявні `SEED_URL_TOKENS`, `urlsplit`, `unquote` (уже імпортовані у promo_lexicon).
- Produces:
  - `is_excluded(url: str) -> bool` — path містить EXCLUDE-токен.
  - `page_is_target(url: str, anchor_text: str | None = None) -> bool` — не excluded і (INCLUDE-слаг у path або анкор-сигнал).
  - `seed_is_target(url: str) -> bool` — корінь домену (`path in ("", "/")`) або `page_is_target(url)`.

- [ ] **Step 1: Write the failing test**

Create `crawler/tests/test_page_types.py`:

```python
from crawler.discovery import promo_lexicon as pl


# --- INCLUDE by URL slug ---
def test_veteran_slugs_are_target():
    for u in ("https://s.ua/viyskovym", "https://s.ua/dlya-veteraniv",
              "https://s.ua/zsu", "https://s.ua/army-discount",
              "https://s.ua/%D0%B2%D1%96%D0%B9%D1%81%D1%8C%D0%BA%D0%BE%D0%B2%D0%B8%D0%BC"):
        assert pl.page_is_target(u) is True, u


def test_info_slugs_are_target():
    for u in ("https://s.ua/kontakty", "https://s.ua/contact",
              "https://s.ua/dostavka-i-oplata", "https://s.ua/delivery",
              "https://s.ua/about", "https://s.ua/pro-nas",
              "https://s.ua/loyalty", "https://s.ua/bonus",
              "https://s.ua/faq", "https://s.ua/korysna-informaciya"):
        assert pl.page_is_target(u) is True, u


def test_promo_slugs_still_target():
    assert pl.page_is_target("https://s.ua/sale") is True
    assert pl.page_is_target("https://s.ua/akcii") is True


# --- INCLUDE by anchor text (opaque URL) ---
def test_anchor_text_makes_opaque_url_target():
    assert pl.page_is_target("https://s.ua/page/12",
                             "Знижка для військовослужбовців") is True
    assert pl.page_is_target("https://s.ua/p2", "Корисна інформація") is True
    assert pl.page_is_target("https://s.ua/p3", "Випадковий текст") is False


# --- EXCLUDE wins over INCLUDE ---
def test_exclude_beats_include():
    assert pl.page_is_target("https://s.ua/product/sale-shoes") is False
    assert pl.page_is_target("https://s.ua/koshyk") is False
    assert pl.page_is_target("https://s.ua/blog/znizhka-viyskovym") is False
    assert pl.is_excluded("https://s.ua/product/1") is True
    assert pl.is_excluded("https://s.ua/about") is False


# --- neutral ---
def test_neutral_is_not_target():
    assert pl.page_is_target("https://s.ua/random/page") is False


# --- no false positives from substring matching ---
def test_no_substring_false_positives():
    assert pl.page_is_target("https://pharmacy.ua/catalog") is False   # 'army' vs pharmacy
    assert pl.page_is_target("https://s.ua/help/how") is False         # '/p/' vs '/help/'
    assert pl.page_is_target("https://s.ua/vintage") is False          # 'tag' vs vintage


# --- seed gate ---
def test_seed_is_target_root_always():
    assert pl.seed_is_target("https://s.ua") is True          # empty path
    assert pl.seed_is_target("https://s.ua/") is True         # '/'


def test_seed_is_target_path_gated():
    assert pl.seed_is_target("https://s.ua/kontakty") is True
    assert pl.seed_is_target("https://s.ua/product/1") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_page_types.py -q`
Expected: FAIL — `AttributeError: module 'crawler.discovery.promo_lexicon' has no attribute 'page_is_target'`.

- [ ] **Step 3: Write minimal implementation**

In `crawler/crawler/discovery/promo_lexicon.py`, add after `url_is_promo` (after ~line 62). Note `re`, `json`, `urlsplit`, `unquote` are already imported at top of the file (verify; `url_is_promo` already uses `urlsplit`/`unquote`).

```python
# --- page-type targeting (superset of promo; drives DomainWalker page selection) ---

# High-yield info/veteran page-type slugs (promo slugs come from SEED_URL_TOKENS).
_PAGE_TYPE_TOKENS: tuple[str, ...] = (
    # для військових / ветеранів
    "viysk", "viyskov", "viyskovosluzhb", "military", "army", "zsu",
    "veteran", "zahisnik", "zakhisnik", "defender",
    # контакти
    "kontakt", "contact",
    # доставка й оплата
    "dostavka", "oplata", "delivery", "payment", "shipping",
    # про нас
    "pro-nas", "pro_nas", "pronas", "pro-kompaniyu", "about", "o-nas", "o_nas",
    # лояльність / бонусна програма
    "loyaln", "loyalty", "bonus", "club",
    # faq / корисна інформація
    "faq", "pytannya", "pitannya", "korysn", "korisn", "useful",
    # кирилиця (decoded percent-encoded paths)
    "військов", "ветеран", "захисник", "контакт", "доставка", "оплата",
    "про-нас", "лояльн", "бонус", "корисн", "питання",
)

INCLUDE_TOKENS: tuple[str, ...] = SEED_URL_TOKENS + _PAGE_TYPE_TOKENS

# Low-yield page types — never fetch as target, never traverse into (BFS).
EXCLUDE_TOKENS: tuple[str, ...] = (
    "/product", "/tovar", "/goods", "/item", "/p/",
    "cart", "koshyk", "checkout", "basket", "order",
    "account", "login", "signin", "register", "cabinet", "kabinet",
    "profile", "wishlist",
    "blog", "news", "novyny", "search", "poshuk", "filter", "/tag", "privacy", "cookie",
)

# Link-anchor-text signals (lowercased substrings) for opaque URLs.
INCLUDE_ANCHORS: tuple[str, ...] = (
    "військов", "ветеран", "зсу", "захисник", "убд",
    "знижка для військовослужбовц", "контакт", "доставка", "оплата",
    "про нас", "про компанію", "лояльн", "бонусна програма", "клуб",
    "корисна інформація", "питання", "акці", "знижк",
)


def is_excluded(url: str) -> bool:
    path = unquote(urlsplit(url or "").path).lower()
    return any(t in path for t in EXCLUDE_TOKENS)


def page_is_target(url: str, anchor_text: str | None = None) -> bool:
    if is_excluded(url):
        return False                                    # EXCLUDE wins
    path = unquote(urlsplit(url or "").path).lower()
    if any(t in path for t in INCLUDE_TOKENS):
        return True
    if anchor_text and any(a in anchor_text.lower() for a in INCLUDE_ANCHORS):
        return True
    return False


def seed_is_target(url: str) -> bool:
    """A seed/candidate URL is fetched-as-target iff it is the domain root or a target."""
    return unquote(urlsplit(url or "").path) in ("", "/") or page_is_target(url)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_page_types.py -q`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/promo_lexicon.py crawler/tests/test_page_types.py
git commit -m "feat(crawler): page-type targeting classifier (page_is_target/is_excluded/seed_is_target)"
```

---

### Task 2: Walker — sitemap+BFS на `page_is_target`, анкор-сигнал, EXCLUDE-skip

**Files:**
- Modify: `crawler/crawler/discovery/walker.py` (import ~рядок 12; `walk` ~57-61; `_bfs` ~85-107; `_links` ~109-126)
- Test: `crawler/tests/test_walker.py` (доповнити)

**Interfaces:**
- Consumes: `page_is_target`, `is_excluded` (Task 1).
- Produces: walker sitemap-фільтр і BFS використовують `page_is_target`; `_links` повертає `list[tuple[str, str]]` = `(absolute_url, anchor_text)`; BFS: excluded→skip, target(url|анкор)→collect, neutral→frontier.

- [ ] **Step 1: Write the failing test**

Append to `crawler/tests/test_walker.py`:

```python
def test_info_pages_are_targeted_from_sitemap(monkeypatch):
    monkeypatch.setattr(walker_mod, "collect_sitemap_urls",
                        lambda *a, **k: ["https://shop.ua/kontakty",
                                         "https://shop.ua/product/1",
                                         "https://shop.ua/dostavka-i-oplata",
                                         "https://shop.ua/blog/post"])
    policy = FakePolicy(FakeRobots(sitemaps=["https://shop.ua/s.xml"]))
    w = DomainWalker(client=object(), robots=policy, rate_limiter=NoWait(),
                     domain_page_cap=10, bfs_trigger_min=1)
    plan = w.walk(_cand())
    assert "https://shop.ua/kontakty" in plan.urls          # info page targeted
    assert "https://shop.ua/dostavka-i-oplata" in plan.urls
    assert "https://shop.ua/product/1" not in plan.urls     # excluded
    assert "https://shop.ua/blog/post" not in plan.urls     # excluded


def test_bfs_collects_target_by_anchor_and_skips_excluded(monkeypatch):
    monkeypatch.setattr(walker_mod, "collect_sitemap_urls", lambda *a, **k: [])

    class HtmlResp:
        text = ('<a href="/page/12">Знижка для військовослужбовців</a>'
                '<a href="/product/9">Товар</a>'
                '<a href="/kontakty">Контакти</a>')
        content = None
        status_code = 200
        def raise_for_status(self): pass

    class HtmlClient:
        def get(self, url, **kw): return HtmlResp()

    policy = FakePolicy(FakeRobots())
    w = DomainWalker(client=HtmlClient(), robots=policy, rate_limiter=NoWait(),
                     bfs_trigger_min=3, bfs_max_pages=1, domain_page_cap=10)
    plan = w.walk(_cand())
    assert "https://shop.ua/page/12" in plan.urls           # target by anchor text
    assert "https://shop.ua/kontakty" in plan.urls          # target by slug
    assert "https://shop.ua/product/9" not in plan.urls     # excluded, not collected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_walker.py::test_info_pages_are_targeted_from_sitemap tests/test_walker.py::test_bfs_collects_target_by_anchor_and_skips_excluded -q`
Expected: FAIL — info/anchor pages not in `plan.urls` (walker still on `url_is_promo`).

- [ ] **Step 3: Write minimal implementation**

In `crawler/crawler/discovery/walker.py`:

(a) Replace the import line (~12):

```python
from crawler.discovery.promo_lexicon import (  # re-export url_is_promo for callers/tests
    is_excluded, page_is_target, seed_is_target, url_is_promo)
```

(b) In `walk`, replace the `collect_sitemap_urls(...)` call's `promo_filter` and the `promo = [...]` line (~57-61):

```python
            found = collect_sitemap_urls(
                sm_urls, self._client, self._rl, domain, delay, self._sitemap_max_docs,
                promo_filter=lambda u: _same_domain(u, domain) and page_is_target(u),
                promo_target=self._page_cap)
            promo = [u for u in found if _same_domain(u, domain) and page_is_target(u)]
```

(c) Replace `_bfs` (~85-107):

```python
    def _bfs(self, homepage, domain, robots, delay) -> list[str]:
        found: list[str] = []
        seen: set[str] = set()
        frontier = [homepage]
        fetched = 0
        for _ in range(self._bfs_max_depth):
            nxt: list[str] = []
            for page in frontier:
                if fetched >= self._bfs_max_pages:
                    return found
                if not robots.can_fetch(page):
                    continue
                fetched += 1
                for link, anchor in self._links(page, domain, delay):
                    if link in seen:
                        continue
                    seen.add(link)
                    if is_excluded(link):
                        continue                        # hard skip: no collect, no traverse
                    if page_is_target(link, anchor):
                        found.append(link)
                    else:
                        nxt.append(link)                # neutral -> traverse deeper
            frontier = nxt
        return found
```

(d) Replace `_links` return (~118-126) to yield `(url, anchor)` pairs:

```python
        out: list[tuple[str, str]] = []
        for a in tree.css("a"):
            href = a.attributes.get("href")
            if not href:
                continue
            absolute = urljoin(url, href)
            if _same_domain(absolute, domain):
                out.append((absolute.split("#")[0], a.text() or ""))
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_walker.py -q`
Expected: PASS (наявні walker-тести + 2 нові). Наявний `test_sitemap_path_filters_promo_homepage_first_and_caps` лишається зеленим (sale/promo — target; product/blog — excluded).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/walker.py crawler/tests/test_walker.py
git commit -m "feat(crawler): walker targets page-types via page_is_target (sitemap+BFS+anchor)"
```

---

### Task 3: Walker — seed-гейт кандидат-URL (`_finalize`)

**Files:**
- Modify: `crawler/crawler/discovery/walker.py` (`_finalize` ~70-83)
- Test: `crawler/tests/test_walker.py` (доповнити)

**Interfaces:**
- Consumes: `seed_is_target` (Task 1; імпорт уже доданий у Task 2).
- Produces: `_finalize` включає `homepage` лише якщо `seed_is_target(homepage)` (корінь домену або target). Promo-URL із домену — незмінні.

- [ ] **Step 1: Write the failing test**

Append to `crawler/tests/test_walker.py`:

```python
def test_seed_gate_root_candidate_is_kept(monkeypatch):
    monkeypatch.setattr(walker_mod, "collect_sitemap_urls",
                        lambda *a, **k: ["https://shop.ua/sale"])
    policy = FakePolicy(FakeRobots(sitemaps=["https://shop.ua/s.xml"]))
    w = DomainWalker(client=object(), robots=policy, rate_limiter=NoWait(),
                     domain_page_cap=10, bfs_trigger_min=1)
    plan = w.walk(_cand("https://shop.ua"))                 # root candidate (passive)
    assert plan.urls[0] == "https://shop.ua"                # root always fetched


def test_seed_gate_product_candidate_url_is_dropped(monkeypatch):
    monkeypatch.setattr(walker_mod, "collect_sitemap_urls",
                        lambda *a, **k: ["https://shop.ua/sale"])
    policy = FakePolicy(FakeRobots(sitemaps=["https://shop.ua/s.xml"]))
    w = DomainWalker(client=object(), robots=policy, rate_limiter=NoWait(),
                     domain_page_cap=10, bfs_trigger_min=1)
    plan = w.walk(_cand("https://shop.ua/product/12"))      # active non-target candidate
    assert "https://shop.ua/product/12" not in plan.urls    # candidate URL not fetched
    assert "https://shop.ua/sale" in plan.urls              # domain still walked
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_walker.py::test_seed_gate_product_candidate_url_is_dropped -q`
Expected: FAIL — `https://shop.ua/product/12` present (homepage always prepended).

- [ ] **Step 3: Write minimal implementation**

In `crawler/crawler/discovery/walker.py`, replace `_finalize` (~70-83):

```python
    def _finalize(self, homepage, promo, robots) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for url in [homepage, *promo]:
            if url == homepage and not seed_is_target(homepage):
                continue                                # active non-target candidate: skip seed
            if not robots.can_fetch(url):
                continue
            key = normalize_ref("website", url)
            if key in seen:
                continue
            seen.add(key)
            out.append(url)
            if len(out) >= self._page_cap:
                break
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_walker.py -q`
Expected: PASS (усі walker-тести; `test_disallowed_homepage_yields_no_urls` і `test_walk_never_raises` — незмінні, бо root passes seed-gate / except-fallback повертає `[homepage]` окремо).

- [ ] **Step 5: Commit**

```bash
git add crawler/crawler/discovery/walker.py crawler/tests/test_walker.py
git commit -m "feat(crawler): walker seed-gate — fetch candidate URL only if root or target"
```

---

### Task 4: Harvester — seed-гейт у no-walker fallback

**Files:**
- Modify: `crawler/crawler/discovery/harvest.py` (import ~рядок 5-9; `_plan` ~64-69)
- Test: `crawler/tests/test_active_harvest.py` (доповнити)

**Interfaces:**
- Consumes: `seed_is_target` (Task 1).
- Produces: `_plan` у гілці без walker повертає `[]` (не фетчити) для website-кандидата, що не root і не target; root/target — як раніше `[cand.url_or_handle]`. Walker-гілка незмінна.

- [ ] **Step 1: Write the failing test**

Append to `crawler/tests/test_active_harvest.py`:

```python
def test_no_walker_drops_non_target_candidate(monkeypatch):
    import crawler.discovery.harvest as h
    monkeypatch.setattr(h, "resolve_offer_categories", lambda *a, **k: [])
    monkeypatch.setattr(h, "attribute",
                        lambda item, ctx, **kw: type("A", (), {
                            "provider": "shop.ua", "suggest_url_or_handle": None,
                            "suggest_type": "website", "suggest_name": "Shop"})())

    class PlatformRL:
        def wait(self, platform): pass

    fetcher = _Fetcher()
    harv = ActiveHarvester(_Api(), {"website": fetcher}, _Extractor(), rate_limiter=PlatformRL())
    summary = {"offers": 0, "suggestions": 0, "errors": 0}
    cand = SourceCandidate(name="Shop", type="website",
                           url_or_handle="https://shop.ua/product/12")
    harv.harvest([cand], cats=object(), known=set(), summary=summary)
    assert fetcher.urls == []                              # non-target candidate not fetched
```

(Reuse the module-level `_Fetcher`, `_Extractor`, `_Api`, `SourceCandidate` already imported/defined in this test file.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_active_harvest.py::test_no_walker_drops_non_target_candidate -q`
Expected: FAIL — `fetcher.urls == ["https://shop.ua/product/12"]` (fallback fetches it).

- [ ] **Step 3: Write minimal implementation**

In `crawler/crawler/discovery/harvest.py`, add import (near ~line 5, with the other `crawler.discovery` imports):

```python
from crawler.discovery.promo_lexicon import seed_is_target
```

Replace `_plan` (~64-69):

```python
    def _plan(self, cand):
        """(urls, domain, delay) for a candidate. Website candidates expand via the walker;
        without a walker, a website candidate is fetched only if root-or-target (seed gate)."""
        if self._walker is not None and cand.type == "website":
            plan = self._walker.walk(cand)
            return plan.urls, plan.domain, plan.crawl_delay
        if cand.type == "website" and not seed_is_target(cand.url_or_handle):
            return [], None, None
        return [cand.url_or_handle], None, None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_active_harvest.py -q`
Expected: PASS (наявні + 1 новий). `test_walker_none_keeps_single_homepage_fetch` лишається зеленим (кандидат `https://shop.ua` = root → fetched).

- [ ] **Step 5: Run full crawler suite**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — усі наявні + нові. `url_is_promo`-тести (`test_promo_url_filter.py`, `test_promo_lexicon.py`) зелені без змін.

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/discovery/harvest.py crawler/tests/test_active_harvest.py
git commit -m "feat(crawler): harvester no-walker fallback honors seed-gate"
```

---

## Post-implementation

- Requesting-code-review (opus whole-branch) перед merge.
- Жива Docker-перевірка: на реальному домені walker повертає інфо/цільові URL (контакти/доставка/про-нас/військові), не товарні; active-search прохід фетчить менше сторінок.
- Merge (ff) у `main`, push, оновити пам'ять.

## Self-Review (виконано)

**Spec coverage:** класифікатор+таксономія (Task 1) · walker sitemap+BFS+анкор+EXCLUDE-skip (Task 2) · seed-гейт walker (Task 3) · active search / no-walker fallback (Task 4) · `url_is_promo` збережено (Global Constraints + Task 2 re-export) · якість downstream / межі (Global Constraints). Усі секції спеки мають таск.

**Placeholder scan:** плейсхолдерів немає; токен-списки й код наведено дослівно.

**Type consistency:** `page_is_target(url, anchor_text=None)->bool`, `is_excluded(url)->bool`, `seed_is_target(url)->bool` (Task 1) вжиті однаково в Tasks 2–4; `_links -> list[tuple[str,str]]` узгоджено між `_links` і `_bfs` (Task 2).
