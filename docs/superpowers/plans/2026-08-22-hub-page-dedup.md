# Hub-page dedup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the crawler re-flooding moderation with duplicates of already-published promos by generalizing the backend apex-dedup branch into a hub-page dedup.

**Architecture:** Backend-only change in `create_offer`. A new pure helper `is_hub_page` (in `dedup.py`) classifies an incoming offer's page as a hub/listing (apex, URL-parent of a peer, or generic-hub slug). Branch 3d's entry guard is widened from apex-only to any hub page, and its magnitude test is tightened from intersection to subset so a hub that introduces a new discount magnitude is NOT collapsed.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, pytest, MySQL.

## Global Constraints

- No Russian-language forms anywhere in code (lexicons/regexes/lists) — UA + neutral-English only. (`skidki`, `akcii`-as-Russian etc. are forbidden; UA transliterations are fine.)
- Canonical offer keys come from `canonicalize_target_url()` → `"host/path[?query]"` (scheme-less, www-less, no trailing slash). All hub logic is pure string work on that key.
- TDD: failing test first, minimal implementation, frequent commits.
- Branch 3c (`is_duplicate_promo`, text-gated) stays as-is. Passive shadow change-detection (branch 2) stays as-is.
- Run backend tests: `cd backend && .venv/Scripts/python.exe -m pytest -q` (needs MySQL `ubd_test`).
- Work on branch `hub-page-dedup` (already created).

---

### Task 1: `is_hub_page` pure helper

**Files:**
- Modify: `backend/app/crud/dedup.py` (append helper + slug set)
- Test: `backend/tests/test_hub_page.py` (create)

**Interfaces:**
- Consumes: nothing (pure string logic).
- Produces: `is_hub_page(incoming_canon: str, peer_canon: str) -> bool` — True when `incoming_canon` is a hub/listing page relative to `peer_canon`: bare apex (no path), a strict URL-parent of `peer_canon`, or its terminal path segment is a generic-hub slug. Also exports `_HUB_SLUGS: frozenset[str]`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_hub_page.py`:

```python
from app.crud.dedup import is_hub_page


def test_apex_is_hub():
    # bare host, no path -> hub regardless of peer
    assert is_hub_page("smartlab.ua", "smartlab.ua/deep/offer") is True


def test_apex_with_query_is_hub():
    # a query string carries no literal '/', so apex detection still holds
    assert is_hub_page("smartlab.ua?ref=x", "smartlab.ua/deep") is True


def test_url_parent_is_hub():
    # incoming is a strict path-ancestor of the peer (whiteclinic case)
    assert is_hub_page("whiteclinic.ua/promotions",
                       "whiteclinic.ua/promotions/znyzhka-10-dlja-uchasnykiv") is True


def test_generic_slug_is_hub():
    # terminal segment is a curated hub word (mebelmarket / m2fit / tovpollar cases)
    assert is_hub_page("mebelmarket.ua/promotions", "mebelmarket.ua/promotion/znyzhka") is True
    assert is_hub_page("m2fit.com.ua/about", "m2fit.com.ua/veteran") is True
    assert is_hub_page("tovpollar.org/category/aktsii", "tovpollar.org/znyzhky-zsu") is True


def test_only_terminal_segment_counts():
    # a deep offer page whose MIDDLE segment is a hub word is NOT a hub
    assert is_hub_page("mebelmarket.ua/promotion/znyzhka-viyskovm",
                       "mebelmarket.ua/promotions") is False


def test_descriptive_offer_slug_is_not_hub():
    assert is_hub_page("smartlab.ua/deep/znyzhka-10-dlja-uchasnykiv",
                       "smartlab.ua/aktsii") is False


def test_siblings_are_not_hub():
    # two deep sibling pages -> neither is a hub of the other (regression guard)
    assert is_hub_page("smartlab.ua/one", "smartlab.ua/two") is False


def test_empty_incoming_is_not_hub():
    assert is_hub_page("", "smartlab.ua/deep") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_hub_page.py -q`
Expected: FAIL with `ImportError: cannot import name 'is_hub_page'`.

- [ ] **Step 3: Write minimal implementation**

Append to `backend/app/crud/dedup.py`:

```python
# Generic hub/listing terminal slugs (UA + neutral-English only; no Russian forms). A page
# whose LAST path segment is one of these is a storefront/index page, not a specific offer.
_HUB_SLUGS = frozenset({
    "promotions", "promotion", "aktsiyi", "aktsii", "akciyi", "akcia", "akciji",
    "znizhki", "znyzhky", "discounts", "sale", "sales", "offers",
    "propozicii", "propozycii", "category", "categories", "catalog", "katalog",
    "about", "about-us", "pro-nas", "pronas", "main", "home", "index",
})


def _path_only(canon: str) -> str:
    """Drop the query string from a canonicalize_target_url() key -> 'host/path'."""
    return canon.split("?", 1)[0]


def is_hub_page(incoming_canon: str, peer_canon: str) -> bool:
    """True when the incoming offer page is a hub/listing page relative to a peer offer:
    the bare apex (host, no path), a strict URL-parent of the peer, or a page whose terminal
    path segment is a generic-hub slug. Pure string logic over canonicalize_target_url()
    keys ('host/path[?query]'). Only the TERMINAL segment is matched against _HUB_SLUGS, so a
    deep offer page with a hub word mid-path (e.g. /promotion/znyzhka-viyskovm) is not a hub."""
    if not incoming_canon:
        return False
    inc = _path_only(incoming_canon)
    peer = _path_only(peer_canon)
    if "/" not in inc:                       # apex: host only, no path segment
        return True
    if peer.startswith(inc + "/"):           # incoming is a strict path-ancestor of the peer
        return True
    return inc.rsplit("/", 1)[-1] in _HUB_SLUGS   # terminal segment is a generic hub word
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_hub_page.py -q`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/crud/dedup.py backend/tests/test_hub_page.py
git commit -m "feat(backend): is_hub_page helper for hub-page dedup"
```

---

### Task 2: Generalize branch 3d into hub-page dedup in `create_offer`

**Files:**
- Modify: `backend/app/crud/offer.py:12` (import), `backend/app/crud/offer.py:283-319` (branch 3d)
- Test: `backend/tests/test_offer_hub_dedup.py` (create)

**Interfaces:**
- Consumes: `is_hub_page` from Task 1; existing `discount_magnitudes`, `_source_host`, `selectinload`, `Offer`, `CreatedBy`, `OfferStatus`, `datetime`.
- Produces: no new public symbol — behavior change to `create_offer`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_offer_hub_dedup.py`:

```python
from app.crud import offer as offer_crud
from app.models import Offer
from app.models.enums import CreatedBy, OfferStatus
from app.schemas.offer import OfferCreate


def _offer(article, *, val="30", dtype="percent", title="T", site=None, discounts=None):
    host_site = site or ("https://" + article.split("://", 1)[1].split("/", 1)[0])
    return OfferCreate(type="discount", title=title, provider="P",
                       discount_type=dtype, discount_value=val,
                       site_url=host_site, article_url=article, discounts=discounts)


def _create(db, data, *, status=OfferStatus.pending_review, ch=None):
    return offer_crud.create_offer(db, data, CreatedBy.crawler, status,
                                   source_id=None, content_hash=ch)


def test_listing_slug_collapses_onto_deep_peer(db_session):
    # mebelmarket: published deep offer, then /promotions listing with same 8%
    deep = _create(db_session, _offer("https://mebelmarket.ua/promotion/znyzhka-viyskovm",
                                      val="8", title="Deep offer wording"),
                   status=OfferStatus.published, ch="h1")
    hub = _create(db_session, _offer("https://mebelmarket.ua/promotions",
                                     val="8", title="Storefront listing wording"), ch="h2")
    assert hub.id == deep.id                          # collapsed onto the published deep peer
    assert db_session.query(Offer).count() == 1


def test_url_parent_collapses_onto_child(db_session):
    # whiteclinic: /promotions is a URL-parent of the published deep offer
    deep = _create(db_session, _offer("https://whiteclinic.ua/promotions/znyzhka-10",
                                      val="10", title="Deep"),
                   status=OfferStatus.published, ch="h1")
    hub = _create(db_session, _offer("https://whiteclinic.ua/promotions",
                                     val="10", title="Listing"), ch="h2")
    assert hub.id == deep.id
    assert db_session.query(Offer).count() == 1


def test_about_slug_collapses(db_session):
    deep = _create(db_session, _offer("https://m2fit.com.ua/veteran", val="15", title="Deep"),
                   status=OfferStatus.published, ch="h1")
    hub = _create(db_session, _offer("https://m2fit.com.ua/about", val="15", title="About us"),
                  ch="h2")
    assert hub.id == deep.id


def test_hub_with_new_magnitude_is_kept(db_session):
    # listing carries BOTH the published 8% AND a new 15% -> subset fails -> new offer surfaces
    deep = _create(db_session, _offer("https://shop.ua/promotion/deal", val="8", title="Deep"),
                   status=OfferStatus.published, ch="h1")
    hub = _create(db_session,
                  _offer("https://shop.ua/promotions", val="8", title="Listing",
                         discounts=[{"discount_type": "percent", "discount_value": "8"},
                                    {"discount_type": "percent", "discount_value": "15"}]),
                  ch="h2")
    assert hub.id != deep.id                          # NOT collapsed: 15% is new
    assert db_session.query(Offer).count() == 2


def test_two_deep_offer_pages_stay_separate(db_session):
    # neither is a hub -> distinct same-% offers preserved (new-candidate protection)
    a = _create(db_session, _offer("https://clinic.ua/dental-10", val="10", title="Dental"),
                status=OfferStatus.published, ch="h1")
    b = _create(db_session, _offer("https://clinic.ua/cosmetology-10", val="10",
                                   title="Cosmetology"), ch="h2")
    assert a.id != b.id
    assert db_session.query(Offer).count() == 2


def test_hub_with_no_same_host_peer_is_kept(db_session):
    hub = _create(db_session, _offer("https://lonely.ua/promotions", val="20"), ch="h1")
    assert db_session.query(Offer).count() == 1
    assert hub.article_url_canonical == "lonely.ua/promotions"


def test_hub_different_magnitude_is_kept(db_session):
    deep = _create(db_session, _offer("https://shop2.ua/promotion/deal", val="30", title="Deep"),
                   status=OfferStatus.published, ch="h1")
    hub = _create(db_session, _offer("https://shop2.ua/promotions", val="10", title="Listing"),
                  ch="h2")
    assert hub.id != deep.id                          # 10% not a subset of 30%
    assert db_session.query(Offer).count() == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_offer_hub_dedup.py -q`
Expected: FAIL — `test_listing_slug_collapses_onto_deep_peer`, `test_about_slug_collapses`, `test_url_parent_collapses_onto_child` fail with `hub.id != deep.id` (two rows), because the current apex-only branch 3d does not fire for pathed hub pages.

- [ ] **Step 3: Add the import**

In `backend/app/crud/offer.py`, change line 12 from:

```python
from app.crud.dedup import normalize_tokens, discount_magnitudes, is_duplicate_promo
```

to:

```python
from app.crud.dedup import normalize_tokens, discount_magnitudes, is_duplicate_promo, is_hub_page
```

- [ ] **Step 4: Generalize branch 3d**

In `backend/app/crud/offer.py`, replace the whole branch 3d block (the comment starting `# 3d) Apex-homepage dedup:` through the end of its `for` loop, currently lines ~283-319) with:

```python
    # 3d) Hub-page dedup (generalizes the old apex-only branch): a hub/listing page — the bare
    #     apex, a URL-parent of a peer, or a generic-hub slug (/promotions, /category/aktsii,
    #     /about, …) — surfaces a promo already covered by a more specific deep offer on the same
    #     host. Its generic wording defeats 3c's text gate, so collapse it onto an existing
    #     same-host non-shadow non-expired offer (deep pages preferred), bump last_seen, and never
    #     insert. SUBSET (not intersection): the incoming hub's magnitudes must all be covered by
    #     the peer, so a hub that introduces a NEW magnitude the peer lacks is NOT collapsed and
    #     the genuinely new promo still reaches moderation.
    if crawler and not blocked and canon_article and data.discount_type is not None:
        host = (_source_host(getattr(data, "site_url", None))
                or _source_host(getattr(data, "article_url", None)))
        new_mags = discount_magnitudes(getattr(data, "discounts", None),
                                       data.discount_type, data.discount_value)
        if host and new_mags:
            cands = (db.query(Offer)
                     .options(selectinload(Offer.discounts))
                     .filter(Offer.created_by == CreatedBy.crawler,
                             Offer.status != OfferStatus.expired,
                             Offer.supersedes_offer_id.is_(None))
                     .all())

            def _rank(c):
                ca = c.article_url_canonical or ""
                return (0 if "/" in ca else 1, c.id)   # deep peers first, then lowest id

            for c in sorted(cands, key=_rank):
                peer_canon = c.article_url_canonical or ""
                if peer_canon == canon_article:
                    continue                            # same page → branches 1/3b own it
                c_host = _source_host(c.site_url) or _source_host(c.article_url)
                if c_host != host:
                    continue
                if not is_hub_page(canon_article, peer_canon):
                    continue                            # only a hub/listing page collapses here
                c_mags = discount_magnitudes(c.discounts, c.discount_type, c.discount_value)
                if new_mags <= c_mags:                  # subset: peer covers all incoming mags
                    c.last_seen_at = datetime.utcnow()
                    db.commit()
                    db.refresh(c)
                    return c
```

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_offer_hub_dedup.py -q`
Expected: PASS (7 passed).

- [ ] **Step 6: Run the existing apex-dedup tests to verify no regression**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_offer_apex_dedup.py -q`
Expected: PASS (5 passed) — apex remains a hub; single-magnitude subset == intersection; two deep pages stay separate; shadow never a target.

- [ ] **Step 7: Run the full dedup/offer suite to verify no wider regression**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -q -k "offer or dedup or hub"`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/crud/offer.py backend/tests/test_offer_hub_dedup.py
git commit -m "feat(backend): hub-page dedup — collapse listing pages onto deep peers"
```

---

## Self-Review

**Spec coverage:**
- Collapse rule (hub + magnitude subset) → Task 2 branch. ✅
- `is_hub_page` (apex / url-parent / generic slug) → Task 1. ✅
- New-magnitude-on-hub protection (subset) → Task 2 `test_hub_with_new_magnitude_is_kept`. ✅
- Distinct deep offers preserved → Task 2 `test_two_deep_offer_pages_stay_separate` + apex-suite regression. ✅
- Shadow / change-detection untouched → branch 2 unedited; `supersedes_offer_id.is_(None)` filter kept. ✅
- No Russian forms → `_HUB_SLUGS` UA + English only (Global Constraints). ✅
- Backend-only, reuse 3d scaffold → Task 2 edits one branch. ✅
- 4 real cases → Task 2 tests (mebelmarket slug, whiteclinic url-parent, m2fit about; tovpollar covered by the `aktsii` terminal-slug case in Task 1's `is_hub_page` unit test). ✅

**Placeholder scan:** none — all steps carry full code and exact commands.

**Type consistency:** `is_hub_page(str, str) -> bool` defined in Task 1, imported and called with `(canon_article, peer_canon)` in Task 2. `_HUB_SLUGS` frozenset. Magnitude sets from `discount_magnitudes` compared with `<=` (frozenset subset). Consistent.

Note: no DB migration, no API/schema change, no crawler change — the fix is create-time dedup logic only. Existing queue duplicates are not retro-collapsed (cleared by the moderator; not re-created after the fix).
