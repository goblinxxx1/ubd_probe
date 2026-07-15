# Offer Dedup & Merge by Target Link Implementation Plan — Track C

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Crawler extracts each offer's `target_url` (where the discount leads); the backend merges crawler offers sharing a normalised `target_url` into one offer with multiple `offer_links` (sources where found); the public site shows all those links.

**Architecture:** `target_url` computed in the heuristic extractor from `RawItem.links` (populated by website + telegram fetchers); a new `offer_links` table holds one row per discovery source; `create_offer` merges on `target_url` for the crawler path; `OfferOut.links` exposes them; public iterates them.

**Tech Stack:** FastAPI/SQLAlchemy/Alembic, Vue 3 + Vitest, crawler `httpx`/selectolax.

## Global Constraints

- **Merge only on the crawler path** (`created_by=crawler`) with a non-null `target_url`; admin offers unaffected.
- **Same normalised `target_url` → merge** (append an `offer_links` row); different → separate; **`None` → separate** (no false collapses).
- **Platform coverage:** `target_url` only from fetchers that fill `RawItem.links` — **website + telegram**. Instagram/Facebook → `target_url=None` → separate (accepted).
- Keep existing `(source_id, content_hash)` guard; keep single `site_url`/`article_url` columns on `offers`.
- `offer_links` is a separate table (not JSON). `target_url` String(1024), indexed, nullable, not backfilled.
- Target heuristic: first link whose host ≠ source host, excluding social hosts (facebook/instagram/t.me/telegram/twitter/x/youtube) and non-http; normalised via crawler `_normalize_url`.
- Backend tests from `backend/` (needs `mysql-container`); crawler from `crawler/`; frontend `npm test`.

## File Structure

- `backend/app/models/offer.py` — `Offer.target_url` + `links` relationship.
- `backend/app/models/offer_link.py` — new `OfferLink` model.
- `backend/alembic/versions/<rev>_offer_links.py` — column + table.
- `backend/app/schemas/offer.py` — `target_url` on `OfferBase`; `OfferOut.links`; `OfferLinkOut`.
- `backend/app/crud/offer.py` — merge logic.
- `crawler/crawler/discovery/passive.py` reuse or `extract/heuristic.py` — `_pick_target`.
- `crawler/crawler/models.py`, `extract/heuristic.py`, `runner.py` — carry `target_url`.
- `public/src/components/OfferCard.vue`, `views/OfferDetailView.vue` — iterate links.

---

### Task C-1: Backend model — target_url + offer_links table + migration

**Files:**
- Create: `backend/app/models/offer_link.py`
- Modify: `backend/app/models/offer.py`
- Modify: `backend/app/models/__init__.py` (export OfferLink)
- Create: `backend/alembic/versions/<rev>_offer_links.py`

**Interfaces:**
- Produces: `Offer.target_url: str|None`; `Offer.links: list[OfferLink]`; `OfferLink(offer_id, provider, site_url, article_url)`.

- [ ] **Step 1: Create `backend/app/models/offer_link.py`**

```python
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class OfferLink(Base):
    __tablename__ = "offer_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    offer_id: Mapped[int] = mapped_column(
        ForeignKey("offers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(512), nullable=False)
    site_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    article_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    offer: Mapped["Offer"] = relationship(back_populates="links")
```

- [ ] **Step 2: Add `target_url` + `links` to `backend/app/models/offer.py`**

After the `image_url` line (in the columns), add:
```python
    target_url: Mapped[str | None] = mapped_column(String(1024), nullable=True, index=True)
```
After the `offer_categories` relationship block, add:
```python
    links: Mapped[list["OfferLink"]] = relationship(
        back_populates="offer", cascade="all, delete-orphan", lazy="selectin"
    )
```
And add the import at the top of `offer.py`:
```python
from app.models.offer_link import OfferLink  # noqa: F401  (relationship target)
```
(If a circular import arises, use a string annotation only and import inside `app/models/__init__.py` ordering instead.)

- [ ] **Step 3: Export `OfferLink` in `backend/app/models/__init__.py`**

Add `OfferLink` to the imports/`__all__` alongside `Offer` (so `Base.metadata` and Alembic see the table).

- [ ] **Step 4: Generate + write the migration**

```bash
cd backend && ./.venv/Scripts/alembic.exe revision -m "offer links"
```
In the new file (keep the auto `down_revision`), write:
```python
def upgrade() -> None:
    op.add_column('offers', sa.Column('target_url', sa.String(length=1024), nullable=True))
    op.create_index('ix_offers_target_url', 'offers', ['target_url'])
    op.create_table('offer_links',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('offer_id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=512), nullable=False),
        sa.Column('site_url', sa.String(length=1024), nullable=True),
        sa.Column('article_url', sa.String(length=1024), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['offer_id'], ['offers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_offer_links_offer_id', 'offer_links', ['offer_id'])


def downgrade() -> None:
    op.drop_index('ix_offer_links_offer_id', 'offer_links')
    op.drop_table('offer_links')
    op.drop_index('ix_offers_target_url', 'offers')
    op.drop_column('offers', 'target_url')
```

- [ ] **Step 5: Apply + verify**

```bash
./.venv/Scripts/alembic.exe upgrade head
docker exec mysql-container mysql -uroot -pmy-secret-pw -e "USE ubd; SHOW TABLES LIKE 'offer_links'; SHOW COLUMNS FROM offers LIKE 'target_url';" 2>&1 | grep -v Warning
```
Expected: `offer_links` table exists; `offers.target_url` column exists.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/offer.py backend/app/models/offer_link.py backend/app/models/__init__.py backend/alembic/versions/
git commit -m "feat(backend): offer target_url + offer_links table + migration"
```

---

### Task C-2: Backend — schema + merge CRUD (TDD)

**Files:**
- Modify: `backend/app/schemas/offer.py` (`target_url` on `OfferBase`; `OfferLinkOut`; `OfferOut.links`)
- Modify: `backend/app/crud/offer.py` (merge)
- Create: `backend/tests/test_offer_merge.py`

**Interfaces:**
- Consumes: model from C-1.
- Produces: `create_offer` merges crawler offers by `target_url`; `OfferOut.links: list[OfferLinkOut]`.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_offer_merge.py`

```python
from app.crud import offer as offer_crud
from app.models.enums import CreatedBy, OfferStatus
from app.schemas.offer import OfferCreate


def _offer(target, provider="P", site="https://a/x", article="https://a/x", title="T", val="10"):
    return OfferCreate(type="discount", title=title, provider=provider,
                       discount_type="percent", discount_value=val,
                       site_url=site, article_url=article, target_url=target)


def _create(db, data, source_id):
    return offer_crud.create_offer(db, data, CreatedBy.crawler,
                                   OfferStatus.pending_review, source_id=source_id)


def test_same_target_merges_into_one_offer_with_two_links(db_session):
    a = _create(db_session, _offer("https://biz.example/deal", provider="Agg1",
                                    site="https://agg1", article="https://agg1/p"), 1)
    b = _create(db_session, _offer("https://biz.example/deal", provider="Agg2",
                                    site="https://agg2", article="https://agg2/p"), 2)
    assert a.id == b.id                       # merged — same row
    assert len(a.links) == 2
    providers = {l.provider for l in a.links}
    assert providers == {"Agg1", "Agg2"}


def test_different_target_stays_separate(db_session):
    a = _create(db_session, _offer("https://biz.example/one"), 1)
    b = _create(db_session, _offer("https://biz.example/two"), 2)
    assert a.id != b.id


def test_no_target_stays_separate(db_session):
    a = _create(db_session, _offer(None), 1)
    b = _create(db_session, _offer(None), 2)
    assert a.id != b.id


def test_merge_is_idempotent(db_session):
    a = _create(db_session, _offer("https://biz.example/deal", provider="Agg1",
                                    site="https://agg1", article="https://agg1/p"), 1)
    b = _create(db_session, _offer("https://biz.example/deal", provider="Agg1",
                                    site="https://agg1", article="https://agg1/p"), 1)
    assert a.id == b.id
    assert len(a.links) == 1                   # identical link not stacked
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_offer_merge.py -q
```
Expected: FAIL — `OfferCreate` has no `target_url`; no merge/links.

- [ ] **Step 3: Add schema fields** in `backend/app/schemas/offer.py`

In `OfferBase`, after `article_url`, add:
```python
    target_url: str | None = None
```
and include `target_url` in the existing `@field_validator("site_url", "article_url", ...)` field list → change it to
`@field_validator("site_url", "article_url", "target_url", mode="before")` (both in `OfferBase` and `OfferUpdate`).

Add an `OfferLinkOut` model (near `OfferOut`):
```python
class OfferLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    provider: str
    site_url: str | None
    article_url: str | None
```
In `OfferOut`, add:
```python
    target_url: str | None
    links: list[OfferLinkOut] = []
```

- [ ] **Step 4: Implement merge in `backend/app/crud/offer.py`**

Replace the body of `create_offer` (keep signature) so it computes links + merges. After the existing `(source_id, content_hash)` short-circuit, before building `obj`, add the crawler-merge branch; and always create a first `OfferLink`. Full replacement of the construction section:

```python
    from app.models.offer_link import OfferLink  # local import avoids cycle

    def _mk_link():
        return OfferLink(provider=data.provider, site_url=data.site_url,
                         article_url=data.article_url)

    if created_by == CreatedBy.crawler and data.target_url:
        existing = (db.query(Offer)
                    .filter(Offer.target_url == data.target_url)
                    .first())
        if existing is not None:
            already = any(l.provider == data.provider and l.site_url == data.site_url
                          and l.article_url == data.article_url for l in existing.links)
            if not already:
                existing.links.append(_mk_link())
                db.commit()
                db.refresh(existing)
            return existing

    targets, offers = _load_categories(db, data.target_category_ids, data.offer_category_ids)
    obj = Offer(
        type=data.type, title=data.title, description=data.description, provider=data.provider,
        location=data.location, valid_from=data.valid_from, valid_until=data.valid_until,
        discount_type=data.discount_type, discount_value=data.discount_value,
        site_url=data.site_url, article_url=data.article_url, image_url=data.image_url,
        target_url=data.target_url, source_id=source_id,
        status=status, created_by=created_by, content_hash=content_hash,
        target_categories=targets, offer_categories=offers,
        links=[_mk_link()],
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj
```

(Remove the old `obj = Offer(...)`/`db.add`/`commit`/`refresh`/`return` block being replaced.)

- [ ] **Step 5: Run tests (new + full backend suite)**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_offer_merge.py -q
./.venv/Scripts/python.exe -m pytest -q
```
Expected: 4 new pass; full suite green (existing offer tests still pass — they now also get a `links` row, which doesn't break them).

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/offer.py backend/app/crud/offer.py backend/tests/test_offer_merge.py
git commit -m "feat(backend): merge crawler offers by target_url into offer_links"
```

---

### Task C-3: Crawler — extract target_url (TDD)

**Files:**
- Modify: `crawler/crawler/models.py` (`RawItem.target_url` not needed — computed in extractor; add `OfferCandidate.target_url`)
- Modify: `crawler/crawler/extract/heuristic.py` (`_pick_target` + set `target_url`)
- Modify: `crawler/crawler/runner.py` (`offer_payload` adds `target_url`)
- Create: `crawler/tests/test_target_url.py`

**Interfaces:**
- Consumes: `RawItem.links`, `RawItem.url`, `_normalize_url`.
- Produces: `_pick_target(links, source_url) -> str|None`; `OfferCandidate.target_url`; payload carries it.

- [ ] **Step 1: Write the failing test** — `crawler/tests/test_target_url.py`

```python
from crawler.extract.heuristic import _pick_target


def test_pick_first_external_non_social():
    links = ["https://army.gov.ua/nav", "https://biz.example/deal?utm_source=x",
             "https://facebook.com/biz"]
    # source is army.gov.ua → skip same-host + social, pick biz.example (normalised)
    assert _pick_target(links, "https://army.gov.ua/page") == "https://biz.example/deal"


def test_none_when_only_same_host_or_social():
    links = ["https://army.gov.ua/x", "https://t.me/chan", "https://instagram.com/x"]
    assert _pick_target(links, "https://army.gov.ua/page") is None


def test_none_when_no_links():
    assert _pick_target([], "https://army.gov.ua/page") is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_target_url.py -q
```
Expected: FAIL — `_pick_target` does not exist.

- [ ] **Step 3: Add `target_url` to `OfferCandidate`** in `crawler/crawler/models.py`

After `image_url` in `OfferCandidate`, add:
```python
    target_url: str | None = None
```

- [ ] **Step 4: Add `_pick_target` + set it in `crawler/crawler/extract/heuristic.py`**

Add to imports:
```python
from urllib.parse import urlsplit
from crawler.fetchers.website import _normalize_url
```
Add the helper (module level):
```python
_SOCIAL_HOSTS = ("facebook.com", "instagram.com", "t.me", "telegram.me",
                 "twitter.com", "x.com", "youtube.com", "youtu.be")


def _pick_target(links, source_url: str) -> str | None:
    src_host = urlsplit(source_url or "").netloc.lower().removeprefix("www.")
    for raw in links or []:
        norm = _normalize_url(raw or "")
        if not norm:
            continue
        host = urlsplit(norm).netloc.lower().removeprefix("www.")
        if not host or host == src_host:
            continue
        if any(host == s or host.endswith("." + s) for s in _SOCIAL_HOSTS):
            continue
        return norm
    return None
```
In `HeuristicExtractor.extract`, in the `OfferCandidate(...)` return, add:
```python
            target_url=_pick_target(getattr(item, "links", None), item.url or ""),
```

- [ ] **Step 5: Add `target_url` to the payload** in `crawler/crawler/runner.py`

In `offer_payload`, add:
```python
        "target_url": cand.target_url,
```

- [ ] **Step 6: Run tests (new + full crawler suite)**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_target_url.py -q
./.venv/Scripts/python.exe -m pytest -q
```
Expected: new pass; full crawler suite green.

- [ ] **Step 7: Commit**

```bash
git add crawler/crawler/models.py crawler/crawler/extract/heuristic.py crawler/crawler/runner.py crawler/tests/test_target_url.py
git commit -m "feat(crawler): extract offer target_url from block links"
```

---

### Task C-4: Public — render multiple links (TDD)

**Files:**
- Modify: `public/src/components/OfferCard.vue`
- Modify: `public/src/views/OfferDetailView.vue`
- Modify: `public/tests/components/OfferCard.test.js`

**Interfaces:**
- Consumes: `offer.links: [{provider, site_url, article_url}]`.
- Produces: a link pair per source (fallback to single `site_url`/`article_url`).

- [ ] **Step 1: Write the failing test** — add to `public/tests/components/OfferCard.test.js`

```javascript
  it("renders a link pair per offer_link source", () => {
    const w = mountCard({
      id: 5, type: "discount", title: "T", provider: "X", image_url: null,
      target_categories: [],
      links: [
        { provider: "Agg1", site_url: "https://agg1", article_url: "https://agg1/p" },
        { provider: "Agg2", site_url: "https://agg2", article_url: "https://agg2/p" },
      ],
    });
    const hrefs = w.findAll("a.card__link").map((a) => a.attributes("href"));
    expect(hrefs).toContain("https://agg1");
    expect(hrefs).toContain("https://agg2");
    expect(hrefs).toContain("https://agg1/p");
    expect(hrefs).toContain("https://agg2/p");
  });
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd public && npm test -- OfferCard
```
Expected: FAIL — card still reads single `site_url`/`article_url`.

- [ ] **Step 3: Update `OfferCard.vue`** — replace the `card__links` block with an iteration that prefers `offer.links`, falling back to the single fields:

```html
      <div v-if="sourceLinks.length" class="card__links">
        <template v-for="(l, i) in sourceLinks" :key="i">
          <a v-if="l.site_url" class="card__link" :href="l.site_url"
             target="_blank" rel="noopener">Сайт{{ sourceLinks.length > 1 ? ' ' + (i + 1) : '' }}</a>
          <a v-if="l.article_url" class="card__link" :href="l.article_url"
             target="_blank" rel="noopener">Новина{{ sourceLinks.length > 1 ? ' ' + (i + 1) : '' }}</a>
        </template>
      </div>
```
Add to `<script setup>` (after the `image` computed):
```javascript
const sourceLinks = computed(() =>
  props.offer.links?.length
    ? props.offer.links
    : (props.offer.site_url || props.offer.article_url
        ? [{ site_url: props.offer.site_url, article_url: props.offer.article_url }]
        : [])
);
```

- [ ] **Step 4: Update `OfferDetailView.vue`** — replace the two `site_url`/`article_url` rows with an iteration over `offer.links` (fallback to single). Add a `sourceLinks` computed mirroring the card, and:

```html
      <div v-for="(l, i) in sourceLinks" :key="i" class="detail__row">
        <span class="detail__label">Джерело{{ sourceLinks.length > 1 ? ' ' + (i + 1) : '' }}:</span>
        <a v-if="l.site_url" :href="l.site_url" target="_blank" rel="noopener">Сайт</a>
        <a v-if="l.article_url" :href="l.article_url" target="_blank" rel="noopener" style="margin-left:8px">Сторінка новини</a>
      </div>
```

- [ ] **Step 5: Run tests**

```bash
npm test -- OfferCard
npm test
```
Expected: new case passes; full public suite green (the earlier single-link test still passes via fallback).

- [ ] **Step 6: Commit**

```bash
git add public/src/components/OfferCard.vue public/src/views/OfferDetailView.vue public/tests/components/OfferCard.test.js
git commit -m "feat(public): render all offer_links (multi-source) with single-link fallback"
```

---

### Task C-5: End-to-end verification (Docker)

**Files:**
- Modify: `docker/fixture/index.html` (link its offer to a target URL); optionally add a second fixture page.

- [ ] **Step 1: Give the fixture offer a target link**

In `docker/fixture/index.html`, inside the `<article>`, add an anchor to an external target:
```html
    <a href="https://biz.example/veterans-deal">Умови акції</a>
```
(External host ≠ `fixture`, non-social → becomes `target_url`.)

- [ ] **Step 2: Rebuild + migrate + run**

```bash
docker compose up -d --build backend        # applies the offer_links migration
docker compose build crawler
docker compose --profile crawler run --rm --entrypoint python backend -m app.demo_seed
docker compose --profile crawler run --rm crawler 2>&1 | grep "crawl summary"
docker compose exec -T db mysql -uroot -pmy-secret-pw \
  -e "USE ubd; SELECT id, LEFT(target_url,40) FROM offers WHERE target_url IS NOT NULL; SELECT offer_id, provider FROM offer_links;" 2>&1 | grep -v Warning
```
Expected: the offer has a non-null `target_url`; an `offer_links` row exists.

- [ ] **Step 3: Verify merge with a second source**

Add a second demo source that serves the same target link (or re-run demo_seed pointing a second fixture at the same `target_url`), run the crawler again, and confirm the offer count for that `target_url` stays 1 while `offer_links` gains a second row.
```bash
docker compose exec -T db mysql -uroot -pmy-secret-pw \
  -e "USE ubd; SELECT target_url, COUNT(*) FROM offers WHERE target_url IS NOT NULL GROUP BY target_url; SELECT COUNT(*) FROM offer_links;" 2>&1 | grep -v Warning
```
Expected: one offer per `target_url`; `offer_links` count reflects the number of sources.

- [ ] **Step 4: Confirm in public** — approve the offer in admin (`:8082`), open public (`:8080`), confirm the card shows the link(s).

- [ ] **Step 5: Commit**

```bash
git add docker/fixture/index.html
git commit -m "test(infra): fixture target link for offer-merge end-to-end"
```

---

## Self-Review

**Spec coverage:**
- Crawler extracts `target_url` (first external non-social link) → Task C-3. ✅
- Merge crawler offers by `target_url` → Task C-2. ✅
- `offer_links` table (one row per source) → Task C-1 (model) + C-2 (populated on create/merge). ✅
- Public shows all links → Task C-4. ✅
- Offers without `target_url` stay separate → Task C-2 (branch guarded by `data.target_url`). ✅
- Platform coverage (website+telegram fill links; IG/FB → None) → inherent to C-3 (`_pick_target` reads `item.links`). ✅
- Merge only crawler path; admin unaffected → Task C-2 (`created_by == CreatedBy.crawler`). ✅
- Existing `(source_id, content_hash)` guard kept → Task C-2 (short-circuit retained). ✅
- Non-goals (segmentation, fuzzy, manual/retroactive merge) → not implemented. ✅

**Placeholder scan:** No TBD/TODO; every code step has full code; migration/verify use exact commands. The one conditional note (circular-import fallback in C-1 Step 2) states the concrete alternative. ✅

**Type consistency:** `target_url` name matches across model (C-1), schema `OfferBase`/`OfferOut` (C-2), crud (C-2), crawler `OfferCandidate`+payload (C-3). `OfferLink(provider, site_url, article_url)` matches `_mk_link()` (C-2), `OfferLinkOut` (C-2), and the public `links[]` shape (C-4). `_pick_target(links, source_url)` matches its test (C-3 Step 1) and call site (C-3 Step 4). `offer_payload` key `target_url` matches `InternalOfferCreate`→`OfferCreate`→`OfferBase.target_url`. ✅
