from app.core.security import create_access_token
from app.models import AdminUser
from app.models.enums import AdminRole


def _seed_admin(db_session, role):
    admin = AdminUser(email=f"{role.value}@example.com", password_hash="x", role=role)
    db_session.add(admin)
    db_session.commit()
    return create_access_token(subject=admin.email, role=role.value)


def test_super_admin_creates_user(client, db_session):
    token = _seed_admin(db_session, AdminRole.super_admin)
    resp = client.post("/api/admin/users",
                       json={"email": "new@example.com", "password": "pw123456", "role": "moderator"},
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "moderator"


def test_moderator_cannot_manage_users(client, db_session):
    token = _seed_admin(db_session, AdminRole.moderator)
    resp = client.get("/api/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
    assert resp.json()["code"] == "forbidden"
