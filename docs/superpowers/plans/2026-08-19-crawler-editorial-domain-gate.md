# Crawler Editorial Domain Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Abandon an editorial (news/blog) domain after its first editorial page, using the `is_article`/schema signals already on `RawItem`, so news portals stop burning crawl budget.

**Architecture:** A per-page guard in `ActiveHarvester._harvest_one`, one branch after the language gate: if a fetched page declares itself an article and carries no commercial schema, and the domain has not yet shown a structural (schema-bearing) page, `break` the walk.

**Tech Stack:** Python 3, pytest; Docker Compose.

## Global Constraints

- Ukrainian-only project: no Russian text in code/tests.
- Reuse existing `RawItem.is_article` / `has_offer_schema` / `has_business_schema`; no fetcher change.
- Guard the break with BOTH: `not structural` (domain already showed commercial intent → do not abandon) AND `editorial_gate_enabled`.
- No new store, no walker/backend/DB change. Config mirrors `lang_gate_enabled` (config.py lines 106 / 223 / 362).
- Run crawler tests from `crawler/`: `./.venv/Scripts/python.exe -m pytest ...`.

---

## Task 1: Editorial gate in `_harvest_one`

**Files:**
- Modify: `crawler/crawler/discovery/harvest.py` (`ActiveHarvester.__init__`; new module helper; `_harvest_one` loop)
- Test: `crawler/tests/test_active_harvest.py`

**Interfaces:**
- Consumes: `RawItem.is_article`, `.has_offer_schema`, `.has_business_schema`.
- Produces: `ActiveHarvester(..., editorial_gate_enabled=True)`; a domain whose first non-structural page is editorial is abandoned.

- [ ] **Step 1: Write the failing tests** — append to `crawler/tests/test_active_harvest.py`

```python
def _art_item(text, url="https://news.example/a", article=True, offer=False, business=False):
    return RawItem(source_id=None, platform="website", key="k", text=text, url=url,
                   links=[], site_name="News", has_offer_schema=offer,
                   has_business_schema=business, is_article=article)


def test_editorial_first_page_abandons_domain():
    from crawler.discovery.walker import WalkPlan
    a_url, b_url = "https://izmacity.com/articles/1", "https://izmacity.com/articles/2"

    class PerUrl:
        def __init__(self): self.fetched = []
        def fetch(self, source, k):
            u = source["url_or_handle"]; self.fetched.append(u)
            return [_art_item("Загинув захисник, громада прощається", url=u)], None

    class W:
        def walk(self, cand): return WalkPlan("izmacity.com", [a_url, b_url], 0.0)

    fetcher = PerUrl()
    h = ActiveHarvester(FakeApi(), {"website": fetcher}, GateExtractor(),
                        rate_limiter=None, fetch_budget=10, walker=W())
    h.harvest([_cand(url=a_url)], cats=None, known=set(), summary=_summary())
    assert fetcher.fetched == [a_url]        # abandoned after the first editorial page
    assert True


def test_editorial_page_after_structural_does_not_discard_offer():
    from crawler.discovery.walker import WalkPlan
    shop, blog = "https://shop.ua/sale", "https://shop.ua/blog/post"

    class PerUrl:
        def __init__(self): self.fetched = []
        def fetch(self, source, k):
            u = source["url_or_handle"]; self.fetched.append(u)
            if u == shop:
                return [_art_item("Знижка 20% для військових", url=u,
                                  article=False, business=True)], None
            return [_art_item("Новина блогу про захисників", url=u)], None

    class W:
        def walk(self, cand): return WalkPlan("shop.ua", [shop, blog], 0.0)

    api = FakeApi()
    h = ActiveHarvester(api, {"website": PerUrl()}, GateExtractor(),
                        rate_limiter=None, fetch_budget=10, walker=W())
    h.harvest([_cand(url=shop)], cats=None, known=set(), summary=_summary())
    assert len(api.offers) == 1              # structural page's offer kept; not discarded


def test_article_with_offer_schema_is_not_editorial():
    api = FakeApi()
    item = _art_item("Знижка 20% для військових", offer=True)
    h = ActiveHarvester(api, {"website": FakeFetcher([item])}, GateExtractor(),
                        rate_limiter=None, fetch_budget=5)
    h.harvest([_cand()], cats=None, known=set(), summary=_summary())
    assert len(api.offers) == 1              # has_offer_schema -> not editorial -> processed


def test_editorial_gate_disabled_processes_page():
    api = FakeApi()
    item = _art_item("Знижка 20% для військових")     # is_article, no schema
    h = ActiveHarvester(api, {"website": FakeFetcher([item])}, GateExtractor(),
                        rate_limiter=None, fetch_budget=5, editorial_gate_enabled=False)
    h.harvest([_cand()], cats=None, known=set(), summary=_summary())
    assert len(api.offers) == 1              # gate off -> processed (byte-equivalent)
```

> These reuse the file's existing `FakeApi`, `FakeFetcher`, `GateExtractor`, `_cand`, `_summary`. `GateExtractor` returns an offer for text containing "%", so the structural/offer tests use "20%".

- [ ] **Step 2: Run to verify it fails**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_active_harvest.py -q`
Expected: FAIL — `ActiveHarvester` has no `editorial_gate_enabled`; the editorial page is currently processed (domain not abandoned), so `test_editorial_first_page_abandons_domain` fetches both URLs.

- [ ] **Step 3: Add the helper + constructor flag + gate** — edit `crawler/crawler/discovery/harvest.py`

Add a module-level helper (near the top, after imports):

```python
def _is_editorial_page(items) -> bool:
    """A news/blog page: declares article/blog markup (schema.org NewsArticle/BlogPosting/
    Article or og:type=article) AND carries no commercial schema (Offer/LocalBusiness/
    Organization). Such a page is never an offer source."""
    if not any(getattr(it, "is_article", False) for it in items):
        return False
    return not any(getattr(it, "has_offer_schema", False)
                   or getattr(it, "has_business_schema", False) for it in items)
```

In `ActiveHarvester.__init__`, add the tail parameter and store it:

```python
                 lang_block_store=None, editorial_gate_enabled=True):
```
```python
        self._lang_block_store = lang_block_store
        self._editorial_gate_enabled = editorial_gate_enabled
```

In `_harvest_one`, insert the gate between the `is_non_ukrainian` break and `_process_page`:

```python
                if (self._editorial_gate_enabled and not structural
                        and _is_editorial_page(items)):
                    # News/blog portal page with no commercial schema — abandon the whole
                    # domain rather than walk its remaining (all-editorial) pages.
                    break
                if self._process_page(cand, items, cats, known, summary):
                    structural = True
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_active_harvest.py -q`
Expected: PASS (existing + 4 new).

- [ ] **Step 5: Run the full crawler suite (no regressions)**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/discovery/harvest.py crawler/tests/test_active_harvest.py
git commit -m "feat(crawler): editorial-domain gate — abandon news/blog domains early"
```

---

## Task 2: Config + wiring

**Files:**
- Modify: `crawler/crawler/config.py` (`_RawSettings` ~106, `Config` ~223, `from_settings` ~362 — beside `lang_gate_enabled`)
- Modify: `crawler/crawler/wiring.py` (`ActiveHarvester(...)` construction)
- Test: `crawler/tests/test_config.py`

**Interfaces:**
- Produces: `config.editorial_gate_enabled: bool = True`; wired into `ActiveHarvester(editorial_gate_enabled=config.editorial_gate_enabled)`.

- [ ] **Step 1: Write the failing test** — append to `crawler/tests/test_config.py`

```python
def test_editorial_gate_defaults_on(monkeypatch, tmp_path):
    from crawler.config import load_config
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EDITORIAL_GATE_ENABLED", raising=False)
    assert load_config().editorial_gate_enabled is True


def test_editorial_gate_can_be_disabled(monkeypatch, tmp_path):
    from crawler.config import load_config
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EDITORIAL_GATE_ENABLED", "false")
    assert load_config().editorial_gate_enabled is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_config.py -k editorial -q`
Expected: FAIL — `Config` has no `editorial_gate_enabled`.

- [ ] **Step 3: Add the config field (three places, beside `lang_gate_enabled`)**

In `_RawSettings` (after line 106) and in `Config` (after line 223):

```python
    editorial_gate_enabled: bool = True
```

In `from_settings` (after line 362):

```python
        editorial_gate_enabled=s.editorial_gate_enabled,
```

- [ ] **Step 4: Wire into `ActiveHarvester`** — edit `crawler/crawler/wiring.py`, add to the `ActiveHarvester(...)` call:

```python
                                    lang_block_store=lang_block_store,
                                    editorial_gate_enabled=config.editorial_gate_enabled)
```

- [ ] **Step 5: Run config test + full suite + import check**

Run: `cd crawler && ./.venv/Scripts/python.exe -c "import crawler.wiring" && ./.venv/Scripts/python.exe -m pytest tests/test_config.py -q`
Expected: import OK; config tests PASS.

- [ ] **Step 6: Commit**

```bash
git add crawler/crawler/config.py crawler/crawler/wiring.py crawler/tests/test_config.py
git commit -m "feat(crawler): wire editorial_gate_enabled config into ActiveHarvester"
```

---

## Task 3: Rollout

**Files:** none in-repo.

- [ ] **Step 1: Rebuild + restart crawler**

```bash
docker compose build crawler && docker compose up -d crawler
```

- [ ] **Step 2: Verify izmacity is abandoned early on the next walk**

```bash
docker compose logs --since=30m crawler | grep -c "GET https://izmacity.com/articles"
```
Expected over subsequent passes: ≤ 1–2 article fetches per walk (was 14), then media_autoblock blocks the host after K zero-structural crawls.

---

## Self-Review

**Spec coverage:**
- Per-page editorial gate (`is_article` and no commercial schema) with `not structural` guard → Task 1. ✓
- Strict condition + structural guard + ordering safety → Task 1 tests (offer-schema page processed; editorial-after-structural keeps offer). ✓
- `editorial_gate_enabled` kill-switch (off = byte-equivalent) → Task 1 + Task 2. ✓
- Rollout / verify izmacity → Task 3. ✓

**Placeholder scan:** none.

**Type consistency:** `_is_editorial_page(items) -> bool`; `RawItem.is_article/has_offer_schema/has_business_schema: bool`; `ActiveHarvester(..., editorial_gate_enabled: bool = True)`; `config.editorial_gate_enabled` produced in Task 2, consumed by wiring. Test helpers reuse the file's existing fixtures.
