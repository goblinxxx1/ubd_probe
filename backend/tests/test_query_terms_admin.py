from app.core.config import settings
from app.core.security import create_access_token
from app.models import AdminUser
from app.models.enums import AdminRole

_KEY = {"X-API-Key": settings.crawler_api_key}


def _admin_token(db_session):
    admin = AdminUser(email="qt@example.com", password_hash="x", role=AdminRole.moderator)
    db_session.add(admin); db_session.commit()
    return create_access_token(subject=admin.email, role="moderator")


def test_submit_list_approve_flow(client, db_session):
    # crawler submits candidates (internal, no auth)
    sub = client.post("/api/internal/query-terms", headers=_KEY, json={"candidates": [
        {"term": "імплантація", "z": 1.1, "support": 3},
        {"term": "зуби", "z": 1.0, "support": 3}]})
    assert sub.status_code == 200 and sub.json()["upserted"] == 2

    token = _admin_token(db_session)
    h = {"Authorization": f"Bearer {token}"}
    lst = client.get("/api/admin/query-terms?status=pending", headers=h)
    assert lst.status_code == 200
    ids = {r["term"]: r["id"] for r in lst.json()}
    assert "імплантація" in ids and "зуби" in ids

    ap = client.post(f"/api/admin/query-terms/{ids['імплантація']}/approve", headers=h)
    assert ap.status_code == 200 and ap.json()["status"] == "approved"
    rj = client.post(f"/api/admin/query-terms/{ids['зуби']}/reject", headers=h)
    assert rj.status_code == 200 and rj.json()["status"] == "rejected"

    # crawler reads approved (internal)
    appr = client.get("/api/internal/query-terms/approved", headers=_KEY)
    assert appr.status_code == 200 and appr.json() == ["імплантація"]


def test_to_pending_drops_approved_term_from_grid(client, db_session):
    client.post("/api/internal/query-terms", headers=_KEY, json={"candidates": [
        {"term": "евакуатор", "z": 1.2, "support": 5}]})
    token = _admin_token(db_session)
    h = {"Authorization": f"Bearer {token}"}
    tid = client.get("/api/admin/query-terms?status=pending", headers=h).json()[0]["id"]
    client.post(f"/api/admin/query-terms/{tid}/approve", headers=h)
    assert client.get("/api/internal/query-terms/approved", headers=_KEY).json() == ["евакуатор"]

    tp = client.post(f"/api/admin/query-terms/{tid}/to-pending", headers=h)
    assert tp.status_code == 200
    assert tp.json()["status"] == "pending"
    assert tp.json()["reviewed_at"] is None
    # dropped from the crawler's approved grid feed
    assert client.get("/api/internal/query-terms/approved", headers=_KEY).json() == []
    # back in the candidate queue for re-audit
    pend = [r["term"] for r in client.get("/api/admin/query-terms?status=pending", headers=h).json()]
    assert "евакуатор" in pend


def test_query_terms_admin_requires_auth(client, db_session):
    assert client.get("/api/admin/query-terms").status_code == 401
    assert client.post("/api/admin/query-terms/1/approve").status_code == 401
    assert client.post("/api/admin/query-terms/1/to-pending").status_code == 401
    assert client.post("/api/admin/query-terms").status_code == 401
    assert client.post("/api/admin/query-terms/1/protect").status_code == 401


def test_manual_add_protected_term_is_returned_and_flagged(client, db_session):
    """Задача 5C: адмін вручну додає терм → approved + protected; краулер тягне його
    у protected-фід, і він потрапляє в approved-грід."""
    token = _admin_token(db_session)
    h = {"Authorization": f"Bearer {token}"}
    add = client.post("/api/admin/query-terms", headers=h, json={"term": "Ручний Терм"})
    assert add.status_code == 200
    body = add.json()
    assert body["term"] == "ручний терм"          # normalized lower
    assert body["status"] == "approved"
    assert body["protected"] is True

    # crawler reads the protected feed (internal)
    prot = client.get("/api/internal/query-terms/protected", headers=_KEY)
    assert prot.status_code == 200 and prot.json() == ["ручний терм"]
    # and it's live in the approved grid too
    appr = client.get("/api/internal/query-terms/approved", headers=_KEY).json()
    assert "ручний терм" in appr


def _seed(client, *terms):
    client.post("/api/internal/query-terms", headers=_KEY, json={"candidates": [
        {"term": t, "z": 1.0, "support": 3} for t in terms]})


def test_bulk_approve_and_reject(client, db_session):
    _seed(client, "терм-а", "терм-б", "терм-в")
    token = _admin_token(db_session)
    h = {"Authorization": f"Bearer {token}"}
    ids = {r["term"]: r["id"] for r in client.get(
        "/api/admin/query-terms?status=pending", headers=h).json()}

    ap = client.post("/api/admin/query-terms/bulk", headers=h,
                     json={"ids": [ids["терм-а"], ids["терм-б"]], "action": "approve"})
    assert ap.status_code == 200
    assert set(ap.json()["done"]) == {ids["терм-а"], ids["терм-б"]}
    assert ap.json()["failed"] == []
    assert sorted(client.get("/api/internal/query-terms/approved", headers=_KEY).json()) == \
        ["терм-а", "терм-б"]

    rj = client.post("/api/admin/query-terms/bulk", headers=h,
                     json={"ids": [ids["терм-в"]], "action": "reject"})
    assert rj.status_code == 200 and rj.json()["done"] == [ids["терм-в"]]
    assert client.get("/api/internal/query-terms/rejected", headers=_KEY).json() == ["терм-в"]


def test_bulk_partial_failure_isolates_bad_id(client, db_session):
    _seed(client, "живий")
    token = _admin_token(db_session)
    h = {"Authorization": f"Bearer {token}"}
    good = client.get("/api/admin/query-terms?status=pending", headers=h).json()[0]["id"]

    res = client.post("/api/admin/query-terms/bulk", headers=h,
                      json={"ids": [good, 999999], "action": "protect"})
    assert res.status_code == 200
    body = res.json()
    assert body["done"] == [good]
    assert [f["id"] for f in body["failed"]] == [999999]
    # the good one still applied despite the sibling failure
    assert client.get("/api/internal/query-terms/protected", headers=_KEY).json() == ["живий"]


def test_bulk_to_pending_and_unprotect(client, db_session):
    _seed(client, "повертаю")
    token = _admin_token(db_session)
    h = {"Authorization": f"Bearer {token}"}
    tid = client.get("/api/admin/query-terms?status=pending", headers=h).json()[0]["id"]
    client.post("/api/admin/query-terms/bulk", headers=h,
                json={"ids": [tid], "action": "approve"})
    client.post("/api/admin/query-terms/bulk", headers=h,
                json={"ids": [tid], "action": "protect"})

    tp = client.post("/api/admin/query-terms/bulk", headers=h,
                     json={"ids": [tid], "action": "to_pending"})
    assert tp.status_code == 200 and tp.json()["done"] == [tid]
    assert client.get("/api/internal/query-terms/approved", headers=_KEY).json() == []

    up = client.post("/api/admin/query-terms/bulk", headers=h,
                     json={"ids": [tid], "action": "unprotect"})
    assert up.status_code == 200 and up.json()["done"] == [tid]
    assert client.get("/api/internal/query-terms/protected", headers=_KEY).json() == []


def test_bulk_requires_auth_and_nonempty_ids(client, db_session):
    assert client.post("/api/admin/query-terms/bulk").status_code == 401
    token = _admin_token(db_session)
    h = {"Authorization": f"Bearer {token}"}
    # empty ids → 422 (Field min_length=1)
    assert client.post("/api/admin/query-terms/bulk", headers=h,
                       json={"ids": [], "action": "approve"}).status_code == 422
    # bad action → 422
    assert client.post("/api/admin/query-terms/bulk", headers=h,
                       json={"ids": [1], "action": "delete"}).status_code == 422


def test_protect_unprotect_toggle(client, db_session):
    """protect/unprotect перемикає прапорець, не чіпаючи approve/reject."""
    client.post("/api/internal/query-terms", headers=_KEY, json={"candidates": [
        {"term": "масаж", "z": 1.0, "support": 4}]})
    token = _admin_token(db_session)
    h = {"Authorization": f"Bearer {token}"}
    tid = client.get("/api/admin/query-terms?status=pending", headers=h).json()[0]["id"]

    pr = client.post(f"/api/admin/query-terms/{tid}/protect", headers=h)
    assert pr.status_code == 200 and pr.json()["protected"] is True
    assert client.get("/api/internal/query-terms/protected", headers=_KEY).json() == ["масаж"]

    un = client.post(f"/api/admin/query-terms/{tid}/unprotect", headers=h)
    assert un.status_code == 200 and un.json()["protected"] is False
    assert client.get("/api/internal/query-terms/protected", headers=_KEY).json() == []
