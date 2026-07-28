# Admin edit: links-синк + «Зберегти і опублікувати» Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Правки «Сайт»/«Сторінка новини» в адмінці доходять до public (`update_offer` синкає `offer_links`), і зі сторінки редагування можна одразу «Зберегти і опублікувати».

**Architecture:** Backend `update_offer` після застосування payload синкає рядок(и) `offer_links` (public рендерить лінки, не offer-колонки). Admin: `OfferForm` дістає кнопку + івент `submit-publish`, `OfferFormView` робить `update`→`publish`.

**Tech Stack:** FastAPI/SQLAlchemy + pytest (backend, MySQL :3306); Vue 3 + Element Plus + Vitest (admin).

## Global Constraints

- Backend baseline **122**; admin baseline **102**; нові тести зверху. Crawler не чіпаємо.
- Backend тести: `cd backend && ./.venv/Scripts/python.exe -m pytest -q` (потребує `mysql-container` на :3306 — вже піднято).
- Admin тести: `cd admin && npm test`; білд: `cd admin && npm run build` (обовʼязковий).
- UI-копірайт українською.
- Links-синк: 0 лінків → створити; 1 → оновити; >1 → оновити той, де `site_url==old_site AND article_url==old_article`, інші не чіпати.
- Кнопка «Зберегти і опублікувати» видима лише коли `initial.id` є І `initial.status !== "published"`.

---

### Task 1: `update_offer` синкає `offer_links` (backend)

**Files:**
- Modify: `backend/app/crud/offer.py` (`update_offer`, lines 198-221)
- Test: `backend/tests/test_offer_update_links.py`

**Interfaces:**
- Consumes: `OfferUpdate`, `OfferLink`, `create_offer`.
- Produces: `update_offer` синкає `offer.links` при зміні `provider`/`site_url`/`article_url`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_offer_update_links.py`:

```python
from app.crud import offer as offer_crud
from app.models import Offer
from app.models.offer_link import OfferLink
from app.models.enums import CreatedBy, OfferStatus
from app.schemas.offer import OfferCreate, OfferUpdate


def _create(db, **over):
    base = dict(type="discount", title="T", provider="P", discount_type="percent",
                discount_value="10", site_url="https://old-site", article_url="https://old-article",
                target_url="https://biz/deal")
    base.update(over)
    return offer_crud.create_offer(db, OfferCreate(**base), CreatedBy.crawler, OfferStatus.pending_review)


def test_update_syncs_single_link(db_session):
    o = _create(db_session)
    assert len(o.links) == 1
    offer_crud.update_offer(db_session, o.id,
                            OfferUpdate(site_url="https://new-site", article_url="https://new-article"))
    db_session.refresh(o)
    assert len(o.links) == 1
    assert o.links[0].site_url == "https://new-site"
    assert o.links[0].article_url == "https://new-article"


def test_update_creates_link_when_none(db_session):
    o = Offer(type="discount", title="T", description="", provider="P",
              status=OfferStatus.pending_review, created_by=CreatedBy.admin,
              site_url="https://old-site", article_url="https://old-article")
    db_session.add(o); db_session.commit(); db_session.refresh(o)
    assert len(o.links) == 0
    offer_crud.update_offer(db_session, o.id, OfferUpdate(site_url="https://new-site"))
    db_session.refresh(o)
    assert len(o.links) == 1
    assert o.links[0].site_url == "https://new-site"


def test_update_multilink_syncs_only_matching(db_session):
    o = _create(db_session)                      # 1 link at old-site/old-article
    o.links.append(OfferLink(provider="Other", site_url="https://other-site",
                             article_url="https://other-article"))
    db_session.commit(); db_session.refresh(o)
    assert len(o.links) == 2
    offer_crud.update_offer(db_session, o.id,
                            OfferUpdate(site_url="https://new-site", article_url="https://new-article"))
    db_session.refresh(o)
    matched = [l for l in o.links if l.site_url == "https://new-site"]
    other = [l for l in o.links if l.provider == "Other"]
    assert len(matched) == 1 and matched[0].article_url == "https://new-article"
    assert len(other) == 1 and other[0].site_url == "https://other-site"   # untouched
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_offer_update_links.py -v`
Expected: FAIL — links not synced (single-link test: link keeps old-site; no-link test: 0 links).

- [ ] **Step 3: Implement link-sync in `update_offer`**

In `backend/app/crud/offer.py`, replace the `update_offer` body (lines 198-221) with:

```python
def update_offer(db: Session, offer_id: int, data: OfferUpdate) -> Offer:
    from app.models.offer_link import OfferLink  # local import avoids cycle
    obj = get_offer(db, offer_id)
    old_site, old_article = obj.site_url, obj.article_url
    payload = data.model_dump(exclude_unset=True)
    target_ids = payload.pop("target_category_ids", None)
    offer_ids = payload.pop("offer_category_ids", None)
    for field, value in payload.items():
        setattr(obj, field, value)
    if "target_url" in payload:
        obj.target_url_canonical = canonicalize_target_url(obj.target_url)
    # Public renders offer.links (offer_links table), not the offer-level columns — keep the
    # offer's link(s) in sync so admin edits to provider/site_url/article_url reach the public site.
    if any(k in payload for k in ("provider", "site_url", "article_url")):
        if not obj.links:
            obj.links.append(OfferLink(provider=obj.provider, site_url=obj.site_url,
                                       article_url=obj.article_url))
        elif len(obj.links) == 1:
            link = obj.links[0]
            link.provider, link.site_url, link.article_url = obj.provider, obj.site_url, obj.article_url
        else:
            for link in obj.links:
                if link.site_url == old_site and link.article_url == old_article:
                    link.provider, link.site_url, link.article_url = obj.provider, obj.site_url, obj.article_url
                    break
    if target_ids is not None:
        obj.target_categories = _load_categories(db, target_ids, [])[0]
    if offer_ids is not None:
        obj.offer_categories = _load_categories(db, [], offer_ids)[1]
    if obj.valid_from and obj.valid_until and obj.valid_until < obj.valid_from:
        raise validation_error("valid_until must be on or after valid_from")
    if obj.discount_type in (DiscountType.percent, DiscountType.fixed):
        if obj.discount_value is None:
            raise validation_error("discount_value required for percent/fixed discounts")
    else:
        if obj.discount_value is not None:
            raise validation_error("discount_value must be empty unless discount_type is percent/fixed")
    db.commit()
    db.refresh(obj)
    return obj
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_offer_update_links.py -v`
Expected: PASS (all 3).

- [ ] **Step 5: Run offer regression (merge/update canonical)**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_offer_merge.py -v`
Expected: PASS (`test_update_recomputes_canonical_only_on_target_change` etc. unaffected).

- [ ] **Step 6: Commit**

```bash
git add backend/app/crud/offer.py backend/tests/test_offer_update_links.py
git commit -m "fix(backend): update_offer syncs offer_links so admin edits reach public"
```

---

### Task 2: Кнопка «Зберегти і опублікувати» (admin)

**Files:**
- Modify: `admin/src/components/OfferForm.vue`
- Modify: `admin/src/views/OfferFormView.vue`
- Test: `admin/tests/components/OfferForm.test.js`, `admin/tests/views/OfferFormView.test.js`

**Interfaces:**
- Consumes: `offers.publish(id)` (existing in `admin/src/api/offers.js`).
- Produces: `OfferForm` emits `submit-publish` (payload) + exposes `canPublish`/`submitPublish`; `OfferFormView.onSubmitPublish` does `update`→`publish`.

- [ ] **Step 1: Write the failing tests**

Append to `admin/tests/components/OfferForm.test.js` (inside the `describe("OfferForm", ...)` block):

```javascript
  it("shows publish only for a non-published existing offer", () => {
    const base = { global: { plugins: [ElementPlus] } };
    const pub = mount(OfferForm, { props: { initial: { id: 5, status: "published", target_categories: [], offer_categories: [] } }, ...base });
    expect(pub.vm.canPublish).toBe(false);
    const pend = mount(OfferForm, { props: { initial: { id: 5, status: "pending_review", target_categories: [], offer_categories: [] } }, ...base });
    expect(pend.vm.canPublish).toBe(true);
    const fresh = mount(OfferForm, { props: { initial: null }, ...base });
    expect(fresh.vm.canPublish).toBeFalsy();
  });

  it("emits submit-publish with a built payload when valid", () => {
    const wrapper = mount(OfferForm, {
      props: { initial: { id: 5, status: "pending_review", target_categories: [], offer_categories: [] } },
      global: { plugins: [ElementPlus] },
    });
    Object.assign(wrapper.vm.form, { type: "event", title: "Подія", provider: "Орг" });
    wrapper.vm.submitPublish();
    expect(wrapper.emitted()["submit-publish"][0][0].title).toBe("Подія");
  });
```

In `admin/tests/views/OfferFormView.test.js`: add `publish` to the `@/api/offers` mock (the object at the top) — `publish: vi.fn(() => Promise.resolve({ id: 5 })),` — and append inside `describe("OfferFormView", ...)`:

```javascript
  it("updates then publishes on submit-publish", async () => {
    const wrapper = await mountView("/offers/5/edit");
    await flushPromises();
    wrapper.vm.onSubmitPublish({ title: "Pub", type: "event", provider: "P" });
    await flushPromises();
    expect(offers.update).toHaveBeenCalledWith("5", { title: "Pub", type: "event", provider: "P" });
    expect(offers.publish).toHaveBeenCalledWith("5");
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd admin && npx vitest run tests/components/OfferForm.test.js tests/views/OfferFormView.test.js`
Expected: FAIL — `canPublish`/`submitPublish` undefined; `onSubmitPublish` undefined / `offers.publish` not called.

- [ ] **Step 3: Update `OfferForm.vue`**

1. Add `computed` is already imported (line 2). Change the emits (line 14):

```javascript
const emit = defineEmits(["submit", "cancel", "submit-publish"]);
```

2. After the `submit()` function (after line 57), add:

```javascript
const canPublish = computed(() => props.initial?.id && props.initial?.status !== "published");

function submitPublish() {
  const errors = validateOffer(form);
  if (errors.length) {
    ElMessage.error(errors[0]);
    return;
  }
  emit("submit-publish", buildOfferPayload(form));
}
```

3. Update `defineExpose` (line 59):

```javascript
defineExpose({ form, submit, submitPublish, canPublish });
```

4. In the template `.actions` block (lines 115-118), add the publish button between «Зберегти» and «Скасувати»:

```html
    <div class="actions">
      <el-button type="primary" @click="submit">Зберегти</el-button>
      <el-button v-if="canPublish" type="success" @click="submitPublish">Зберегти і опублікувати</el-button>
      <el-button @click="emit('cancel')">Скасувати</el-button>
    </div>
```

- [ ] **Step 4: Update `OfferFormView.vue`**

1. In the template, add the handler to `<OfferForm>` (after `@submit="onSubmit"`, line 53):

```html
      @submit="onSubmit"
      @submit-publish="onSubmitPublish"
```

2. After the `onSubmit` function (after line 41), add:

```javascript
async function onSubmitPublish(payload) {
  try {
    await offers.update(id, payload);
    await offers.publish(id);
    ElMessage.success("Збережено та опубліковано");
    router.push({ name: "offers" });
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}
```

3. Update `defineExpose` (line 43):

```javascript
defineExpose({ onSubmit, onSubmitPublish });
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd admin && npx vitest run tests/components/OfferForm.test.js tests/views/OfferFormView.test.js`
Expected: PASS.

- [ ] **Step 6: Run full admin suite + build**

Run: `cd admin && npm test`
Expected: 102 baseline + new → all green.

Run: `cd admin && npm run build`
Expected: build succeeds.

- [ ] **Step 7: Commit**

```bash
git add admin/src/components/OfferForm.vue admin/src/views/OfferFormView.vue admin/tests/components/OfferForm.test.js admin/tests/views/OfferFormView.test.js
git commit -m "feat(admin): Save-and-publish button on offer edit page"
```

---

## Self-Review

**Spec coverage:**
- Компонент A (`update_offer` links-синк: 0/1/>1) → Task 1 (3 тести) ✅
- Компонент B (кнопка + `submit-publish` + `onSubmitPublish` update→publish; видимість id&&non-published) → Task 2 ✅
- Тести backend (синк/створення/матч) + admin (видимість/емісія/update→publish) + build → Tasks 1–2 ✅

**Placeholder scan:** конкретний код у кожному кроці; жодних TODO/TBD.

**Type consistency:** `submit-publish`, `canPublish`, `submitPublish`, `onSubmitPublish`, `offers.publish`, `OfferLink` — узгоджені між Tasks 1–2 і наявним кодом (`offers.publish` існує; `computed` імпортовано).
