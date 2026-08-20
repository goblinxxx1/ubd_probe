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


def test_query_terms_admin_requires_auth(client, db_session):
    assert client.get("/api/admin/query-terms").status_code == 401
    assert client.post("/api/admin/query-terms/1/approve").status_code == 401
