from app.core.security import create_access_token
from app.crud import blocked_host as bh_crud
from app.models import AdminUser
from app.models.enums import AdminRole
from app.schemas.blocked_host import HostCandidateCreate


def _admin_token(db_session):
    admin = AdminUser(email="mod@example.com", password_hash="x", role=AdminRole.moderator)
    db_session.add(admin)
    db_session.commit()
    return create_access_token(subject=admin.email, role="moderator")


def test_admin_lists_and_approves(client, db_session):
    token = _admin_token(db_session)
    h = {"Authorization": f"Bearer {token}"}
    c = bh_crud.upsert_candidate(db_session, HostCandidateCreate(host="media.example", support=4))
    lst = client.get("/api/admin/host-candidates?status=pending", headers=h)
    assert lst.status_code == 200 and any(r["host"] == "media.example" for r in lst.json())
    ap = client.post(f"/api/admin/host-candidates/{c.id}/approve", headers=h)
    assert ap.status_code == 200 and ap.json()["status"] == "approved"


def test_admin_requires_auth(client, db_session):
    c = bh_crud.upsert_candidate(db_session, HostCandidateCreate(host="x.example"))
    assert client.post(f"/api/admin/host-candidates/{c.id}/reject").status_code == 401
