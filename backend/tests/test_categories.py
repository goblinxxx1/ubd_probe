from app.core.security import create_access_token
from app.models import AdminUser
from app.models.enums import AdminRole


def _super_token(db_session):
    admin = AdminUser(email="root@example.com", password_hash="x", role=AdminRole.super_admin)
    db_session.add(admin)
    db_session.commit()
    return create_access_token(subject=admin.email, role="super_admin")


def _moderator_token(db_session):
    admin = AdminUser(email="mod@example.com", password_hash="x", role=AdminRole.moderator)
    db_session.add(admin)
    db_session.commit()
    return create_access_token(subject=admin.email, role="moderator")


def test_public_lists_are_open(client):
    assert client.get("/api/target-categories").status_code == 200
    assert client.get("/api/offer-categories").status_code == 200


def test_super_admin_creates_and_lists_category(client, db_session):
    token = _super_token(db_session)
    resp = client.post("/api/admin/offer-categories",
                       json={"name": "Розваги", "slug": "rozvahy"},
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["slug"] == "rozvahy"
    listed = client.get("/api/offer-categories").json()
    assert [c["slug"] for c in listed] == ["rozvahy"]


def test_duplicate_slug_conflicts(client, db_session):
    token = _super_token(db_session)
    h = {"Authorization": f"Bearer {token}"}
    client.post("/api/admin/target-categories", json={"name": "УБД", "slug": "ubd"}, headers=h)
    dup = client.post("/api/admin/target-categories", json={"name": "УБД2", "slug": "ubd"}, headers=h)
    assert dup.status_code == 409
    assert dup.json()["code"] == "conflict"


def test_admin_category_requires_auth(client):
    resp = client.post("/api/admin/offer-categories", json={"name": "X", "slug": "x"})
    assert resp.status_code == 401


def test_moderator_forbidden_from_creating_category(client, db_session):
    token = _moderator_token(db_session)
    resp = client.post("/api/admin/offer-categories",
                       json={"name": "X", "slug": "x"},
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
    assert resp.json()["code"] == "forbidden"
