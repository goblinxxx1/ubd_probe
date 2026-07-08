from app.core.security import hash_password
from app.models import AdminUser
from app.models.enums import AdminRole


def _make_admin(db_session):
    admin = AdminUser(email="mod@example.com", password_hash=hash_password("pw12345"),
                      role=AdminRole.moderator)
    db_session.add(admin)
    db_session.commit()


def test_login_success_returns_token(client, db_session):
    _make_admin(db_session)
    resp = client.post("/api/auth/login", json={"email": "mod@example.com", "password": "pw12345"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["role"] == "moderator"
    assert body["access_token"]


def test_login_bad_password(client, db_session):
    _make_admin(db_session)
    resp = client.post("/api/auth/login", json={"email": "mod@example.com", "password": "wrong"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthorized"
