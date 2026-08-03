# Reject retrievable bin + Block-host Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дати модератору дві ортогональні дії над сміттєвим офером — «Відхилити» (м'який retrievable-кошик) і «Заблокувати» (хост `site_url` одразу в медіа-блокліст) — не змінюючи краулер.

**Architecture:** Backend додає 2 admin-ендпоінти (`restore`, `block-host`), що реюзають наявні `offer_crud.set_status` і `blocked_host_crud.add_manual`. Admin (Vue) додає вкладку «Відхилені» + кнопки «Відновити» та «Заблокувати» у `OffersListView.vue`. Краулер не чіпаємо: суппресія відхилених за контентом і споживання блокліста вже існують (треки 22, 29).

**Tech Stack:** FastAPI + SQLAlchemy (backend, pytest), Vue 3 + Element Plus (admin, Vitest).

## Global Constraints

- Спілкування у коментарях/повідомленнях — українською.
- Backend-тести потребують `mysql-container` на :3306 (`docker start mysql-container`).
- Admin перед мержем — і `npm test`, і `npm run build` (Vitest не компілює scoped-Less).
- Admin API-префікс у тестах через `client` = `/api/admin/...`.
- «Заблокувати» **не змінює жоден офер** (рішення спеки). Reject лишається soft; hard-delete окремо.
- TDD (тест-перший), часті коміти. Гілка `feat/reject-block-host` (вже створена від `main`).

---

### Task 1: Backend — ендпоінт `restore` (rejected → pending_review)

**Files:**
- Modify: `backend/app/routers/admin.py` (після `reject_offer`, ~line 108)
- Test: `backend/tests/test_offers_admin.py`

**Interfaces:**
- Consumes: `offer_crud.set_status(db, offer_id, OfferStatus.pending_review, admin.id)` (наявна, offer.py:278).
- Produces: `POST /api/admin/offers/{id}/restore` → `OfferOut` (status стає `pending_review`).

- [ ] **Step 1: Write the failing test**

```python
def test_restore_offer_returns_to_queue(client, db_session):
    token = _admin_token(db_session)
    h = {"Authorization": f"Bearer {token}"}
    rejected = offer_crud.create_offer(
        db_session, OfferCreate(type=OfferType.discount, title="Junk", provider="P"),
        created_by=CreatedBy.crawler, status=OfferStatus.rejected)

    resp = client.post(f"/api/admin/offers/{rejected.id}/restore", headers=h)
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending_review"

    queue = client.get("/api/admin/offers?status=pending_review", headers=h).json()
    assert queue["total"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `backend/`): `./.venv/Scripts/python.exe -m pytest tests/test_offers_admin.py::test_restore_offer_returns_to_queue -v`
Expected: FAIL — 404/405 (route not found).

- [ ] **Step 3: Write minimal implementation**

У `backend/app/routers/admin.py`, одразу після `reject_offer` (line 108), додати:

```python
@router.post("/offers/{offer_id}/restore", response_model=OfferOut)
def restore_offer(offer_id: int, db: Session = Depends(get_db),
                  admin=Depends(get_current_admin)):
    return offer_crud.set_status(db, offer_id, OfferStatus.pending_review, admin.id)
```

(`OfferOut`, `OfferStatus`, `offer_crud`, `get_current_admin`, `Depends`, `get_db` — усі вже імпортовані для сусідніх ендпоінтів.)

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_offers_admin.py::test_restore_offer_returns_to_queue -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/admin.py backend/tests/test_offers_admin.py
git commit -m "feat(backend): admin restore endpoint (rejected -> pending_review)"
```

---

### Task 2: Backend — ендпоінт `block-host` (site_url → approved blocklist)

**Files:**
- Modify: `backend/app/routers/admin.py` (після `restore_offer`)
- Test: `backend/tests/test_offers_admin.py`

**Interfaces:**
- Consumes: `offer_crud.get_offer(db, offer_id)`; `blocked_host_crud.add_manual(db, host_or_url, admin.id)` (наявна, blocked_host.py:74 — сама bare-host'ить URL і кидає `validation_error("host is required")` на порожньому); `offer.links[*].site_url`.
- Produces: `POST /api/admin/offers/{id}/block-host` → `BlockedHostOut` (`status == "approved"`). Офер незмінний.

- [ ] **Step 1: Write the failing tests**

```python
def test_block_host_from_site_url_approves_host(client, db_session):
    token = _admin_token(db_session)
    h = {"Authorization": f"Bearer {token}"}
    offer = offer_crud.create_offer(
        db_session,
        OfferCreate(type=OfferType.discount, title="Junk", provider="News Site",
                    site_url="https://www.junk-media.example/promo?utm_source=x"),
        created_by=CreatedBy.crawler, status=OfferStatus.pending_review)

    resp = client.post(f"/api/admin/offers/{offer.id}/block-host", headers=h)
    assert resp.status_code == 200
    body = resp.json()
    assert body["host"] == "junk-media.example"   # bare host: no scheme/www/path
    assert body["status"] == "approved"

    # host now in the crawler's LEARNED list
    blocked = client.get("/api/admin/host-candidates?status=approved", headers=h).json()
    assert any(b["host"] == "junk-media.example" for b in blocked)

    # offer itself is untouched
    assert client.get(f"/api/admin/offers/{offer.id}", headers=h).json()["status"] == "pending_review"


def test_block_host_falls_back_to_link_site_url(client, db_session):
    token = _admin_token(db_session)
    h = {"Authorization": f"Bearer {token}"}
    # no offer-level site_url; link carries it
    offer = offer_crud.create_offer(
        db_session,
        OfferCreate(type=OfferType.discount, title="Junk", provider="P",
                    site_url="https://linkhost.example/deal"),
        created_by=CreatedBy.crawler, status=OfferStatus.pending_review)
    offer.site_url = None
    db_session.commit()

    resp = client.post(f"/api/admin/offers/{offer.id}/block-host", headers=h)
    assert resp.status_code == 200
    assert resp.json()["host"] == "linkhost.example"


def test_block_host_without_host_is_422(client, db_session):
    token = _admin_token(db_session)
    h = {"Authorization": f"Bearer {token}"}
    offer = offer_crud.create_offer(
        db_session, OfferCreate(type=OfferType.discount, title="No host", provider="P"),
        created_by=CreatedBy.admin, status=OfferStatus.pending_review)
    for link in offer.links:
        link.site_url = None
    db_session.commit()

    resp = client.post(f"/api/admin/offers/{offer.id}/block-host", headers=h)
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_offers_admin.py -k block_host -v`
Expected: FAIL — route not found.

- [ ] **Step 3: Write minimal implementation**

У `backend/app/routers/admin.py`, після `restore_offer`, додати:

```python
@router.post("/offers/{offer_id}/block-host", response_model=BlockedHostOut)
def block_offer_host(offer_id: int, db: Session = Depends(get_db),
                     admin=Depends(get_current_admin)):
    offer = offer_crud.get_offer(db, offer_id)
    host_src = offer.site_url or next(
        (link.site_url for link in offer.links if link.site_url), None)
    # add_manual bare-hosts the URL and raises validation_error on empty -> 422.
    return blocked_host_crud.add_manual(db, host_src or "", admin.id)
```

(`BlockedHostOut`, `blocked_host_crud` — уже імпортовані для host-candidates ендпоінтів.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_offers_admin.py -k block_host -v`
Expected: 3 PASS.

- [ ] **Step 5: Run the full backend suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: усі зелені (156 + 4 нові = 160).

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/admin.py backend/tests/test_offers_admin.py
git commit -m "feat(backend): admin block-host endpoint (offer site_url -> approved blocklist)"
```

---

### Task 3: Admin — вкладка «Відхилені» + кнопка «Відновити»

**Files:**
- Modify: `admin/src/api/offers.js`
- Modify: `admin/src/views/OffersListView.vue`
- Test: `admin/tests/views/OffersListView.test.js`

**Interfaces:**
- Consumes: `POST /admin/offers/{id}/restore` (Task 1).
- Produces: `offers.restore(id)`; `onRestore(id)` метод; таб `name="rejected"`.

- [ ] **Step 1: Write the failing tests**

У `admin/tests/views/OffersListView.test.js` додати `restore: vi.fn(() => Promise.resolve({}))` у мок `@/api/offers`, і нові тести:

```javascript
it("switching to the rejected tab reloads with rejected status", async () => {
  const router = makeRouter();
  router.push("/");
  await router.isReady();
  const wrapper = mount(OffersListView, { global: { plugins: [router, ElementPlus] } });
  await flushPromises();
  wrapper.vm.tab = "rejected";
  await wrapper.vm.applyFilters({});
  await flushPromises();
  expect(offers.list).toHaveBeenLastCalledWith({ status: "rejected", page: 1, size: 20 });
});

it("restore calls the API and reloads", async () => {
  const router = makeRouter();
  router.push("/");
  await router.isReady();
  const wrapper = mount(OffersListView, { global: { plugins: [router, ElementPlus] } });
  await flushPromises();
  await wrapper.vm.onRestore(1);
  await flushPromises();
  expect(offers.restore).toHaveBeenCalledWith(1);
  expect(offers.list).toHaveBeenCalledTimes(2);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `admin/`): `npm test -- OffersListView`
Expected: FAIL — `offers.restore is not a function` / `onRestore is not a function`.

- [ ] **Step 3: Implement**

У `admin/src/api/offers.js` додати рядок:

```javascript
export const restore = (id) => client.post(`/admin/offers/${id}/restore`).then((r) => r.data);
```

У `admin/src/views/OffersListView.vue`:

1) Додати таб-пейн після «На модерації» (line 104):

```html
<el-tab-pane label="Відхилені" name="rejected" />
```

2) Додати метод `onRestore` (біля `onReject`):

```javascript
async function onRestore(id) {
  try {
    await offers.restore(id);
    ElMessage.success("Відновлено");
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}
```

3) Додати кнопку в `#actions` (біля інших, перед «Видалити»):

```html
<el-button v-if="row.status === 'rejected'" size="small" type="success" @click="onRestore(row.id)">Відновити</el-button>
```

4) Додати `onRestore` у `defineExpose({ ... })` (line 90).

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test -- OffersListView`
Expected: усі PASS.

- [ ] **Step 5: Commit**

```bash
git add admin/src/api/offers.js admin/src/views/OffersListView.vue admin/tests/views/OffersListView.test.js
git commit -m "feat(admin): rejected offers tab + restore action"
```

---

### Task 4: Admin — кнопка «Заблокувати» з підтвердженням

**Files:**
- Modify: `admin/src/utils/confirm.js`
- Modify: `admin/src/api/offers.js`
- Modify: `admin/src/views/OffersListView.vue`
- Test: `admin/tests/views/OffersListView.test.js`

**Interfaces:**
- Consumes: `POST /admin/offers/{id}/block-host` (Task 2); `ElMessageBox.confirm` (element-plus).
- Produces: `confirmAction(message)`; `offers.blockHost(id)`; `onBlockHost(id)`; кнопка «Заблокувати» на `pending_review`/`published` рядках із `site_url`.

- [ ] **Step 1: Write the failing tests**

У `admin/tests/views/OffersListView.test.js`:

а) Розширити мок element-plus, додавши `ElMessageBox` (щоб `confirm.js` бачив resolved-confirm):

```javascript
vi.mock("element-plus", async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    ElMessage: { success: vi.fn(), error: vi.fn() },
    ElMessageBox: { confirm: vi.fn(() => Promise.resolve()) },
  };
});
```

б) Додати `blockHost: vi.fn(() => Promise.resolve({ host: "h", status: "approved" }))` у мок `@/api/offers`.

в) Нові тести:

```javascript
it("block-host calls the API after confirm and reloads", async () => {
  const router = makeRouter();
  router.push("/");
  await router.isReady();
  const wrapper = mount(OffersListView, { global: { plugins: [router, ElementPlus] } });
  await flushPromises();
  await wrapper.vm.onBlockHost(1);
  await flushPromises();
  expect(offers.blockHost).toHaveBeenCalledWith(1);
});

it("block-host does nothing when confirm is cancelled", async () => {
  const { ElMessageBox } = await import("element-plus");
  ElMessageBox.confirm.mockRejectedValueOnce("cancel");
  const router = makeRouter();
  router.push("/");
  await router.isReady();
  const wrapper = mount(OffersListView, { global: { plugins: [router, ElementPlus] } });
  await flushPromises();
  await wrapper.vm.onBlockHost(1);
  await flushPromises();
  expect(offers.blockHost).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test -- OffersListView`
Expected: FAIL — `onBlockHost is not a function` / `offers.blockHost is not a function`.

- [ ] **Step 3: Implement**

У `admin/src/utils/confirm.js` додати generic confirm:

```javascript
export function confirmAction(message, title = "Підтвердження") {
  return ElMessageBox.confirm(message, title, {
    type: "warning",
    confirmButtonText: "Так",
    cancelButtonText: "Скасувати",
  });
}
```

У `admin/src/api/offers.js` додати:

```javascript
export const blockHost = (id) => client.post(`/admin/offers/${id}/block-host`).then((r) => r.data);
```

У `admin/src/views/OffersListView.vue`:

1) Розширити import confirm-утиліт (line 9):

```javascript
import { confirmDelete, confirmAction } from "@/utils/confirm";
```

2) Додати метод `onBlockHost` (біля `onReject`):

```javascript
async function onBlockHost(id) {
  try {
    await confirmAction("Заблокувати хост цього офера в медіа-блоклісті? Краулер більше не братиме цей сайт.");
  } catch {
    return;
  }
  try {
    const res = await offers.blockHost(id);
    ElMessage.success(`Заблоковано: ${res.host}`);
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}
```

3) Додати кнопку в `#actions` (перед «Видалити»):

```html
<el-button
  v-if="(row.status === 'pending_review' || row.status === 'published') && isHttpUrl(row.site_url)"
  size="small" type="danger" plain @click="onBlockHost(row.id)">Заблокувати</el-button>
```

4) Додати `onBlockHost` у `defineExpose({ ... })`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test -- OffersListView`
Expected: усі PASS.

- [ ] **Step 5: Run the full admin suite + build**

Run: `npm test` then `npm run build`
Expected: усі тести зелені; build без помилок.

- [ ] **Step 6: Commit**

```bash
git add admin/src/utils/confirm.js admin/src/api/offers.js admin/src/views/OffersListView.vue admin/tests/views/OffersListView.test.js
git commit -m "feat(admin): block-host button with confirm on offer rows"
```

---

## Self-Review notes

- **Spec coverage:** Частина A (retrievable-кошик) → Task 1 (restore endpoint) + Task 3 (вкладка+кнопка). Частина B (block-host) → Task 2 (endpoint) + Task 4 (кнопка+confirm). API-таблиця спеки → Task 1/2. «Заблокувати не чіпає офер» → перевірено у Task 2 test (`status == "pending_review"` після блоку). «Який хост = site_url фолбек link» → Task 2 tests. Краулер без змін — жодної краулерної таски (за спекою).
- **Placeholder scan:** без TBD/TODO; усі кроки містять реальний код і команди.
- **Type consistency:** `offers.restore`/`offers.blockHost`/`onRestore`/`onBlockHost`/`confirmAction` вживаються однаково в усіх тасках; ендпоінти `/restore` і `/block-host` збігаються між backend (Task 1/2) і api-шаром (Task 3/4).
- **Пост-мерж:** deploy — канонічний ребілд `backend` + `admin` образів; краулер не чіпаємо. Оновити пам'ять беклогу (#12 DONE).
