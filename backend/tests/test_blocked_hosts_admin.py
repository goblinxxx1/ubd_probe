from app.core.security import create_access_token
from app.crud import blocked_host as bh_crud
from app.models import AdminUser
from app.models.enums import AdminRole


def _admin_token(db_session):
    admin = AdminUser(email="mod@example.com", password_hash="x", role=AdminRole.moderator)
    db_session.add(admin)
    db_session.commit()
    return create_access_token(subject=admin.email, role="moderator")


def test_admin_lists_blocklist(client, db_session):
    token = _admin_token(db_session)
    h = {"Authorization": f"Bearer {token}"}
    bh_crud.add_manual(db_session, "media.example", reviewed_by=1)
    lst = client.get("/api/admin/host-candidates?status=approved", headers=h)
    assert lst.status_code == 200 and any(r["host"] == "media.example" for r in lst.json())


def test_admin_unblocks_host(client, db_session):
    token = _admin_token(db_session)
    h = {"Authorization": f"Bearer {token}"}
    obj = bh_crud.add_manual(db_session, "media.example", reviewed_by=1)
    r = client.post(f"/api/admin/host-candidates/{obj.id}/reject", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    # unblocked → no longer served to the crawler
    assert "media.example" not in bh_crud.list_approved_hosts(db_session)


def test_admin_unblock_requires_auth(client, db_session):
    obj = bh_crud.add_manual(db_session, "x.example", reviewed_by=1)
    assert client.post(f"/api/admin/host-candidates/{obj.id}/reject").status_code == 401


def test_admin_adds_host_directly_as_approved(client, db_session):
    token = _admin_token(db_session)
    h = {"Authorization": f"Bearer {token}"}
    # a pasted URL with www should normalize to the bare host
    r = client.post("/api/admin/host-candidates", json={"host": "https://www.Veteran.com.ua/news"}, headers=h)
    assert r.status_code == 200
    assert r.json()["host"] == "veteran.com.ua"
    assert r.json()["status"] == "approved"
    # and it shows up in the crawler's approved (LEARNED) list
    lst = client.get("/api/admin/host-candidates?status=approved", headers=h)
    assert any(row["host"] == "veteran.com.ua" for row in lst.json())


def test_admin_add_host_requires_auth(client):
    assert client.post("/api/admin/host-candidates", json={"host": "x.example"}).status_code == 401
