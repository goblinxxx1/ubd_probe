from app.core.config import settings
from app.core.security import create_access_token
from app.models import AdminUser, Source
from app.models.enums import AdminRole


def _token(db_session):
    admin = AdminUser(email="mod@example.com", password_hash="x", role=AdminRole.moderator)
    db_session.add(admin)
    db_session.commit()
    return create_access_token(subject=admin.email, role="moderator")


def test_crawler_suggests_then_admin_approves(client, db_session):
    key = {"X-API-Key": settings.crawler_api_key}
    created = client.post("/api/internal/suggested-sources",
                          json={"name": "New TG", "type": "telegram", "url_or_handle": "@newvets"},
                          headers=key)
    assert created.status_code == 200
    sid = created.json()["id"]

    h = {"Authorization": f"Bearer {_token(db_session)}"}
    queue = client.get("/api/admin/suggested-sources?status=pending", headers=h).json()
    assert len(queue) == 1

    approved = client.post(f"/api/admin/suggested-sources/{sid}/approve", headers=h)
    assert approved.status_code == 200
    assert approved.json()["created_by"] == "crawler_suggestion"
    # a real Source now exists
    assert db_session.query(Source).count() == 1


def test_double_approve_conflicts(client, db_session):
    key = {"X-API-Key": settings.crawler_api_key}
    sid = client.post("/api/internal/suggested-sources",
                      json={"name": "X", "type": "website", "url_or_handle": "https://x"},
                      headers=key).json()["id"]
    h = {"Authorization": f"Bearer {_token(db_session)}"}
    client.post(f"/api/admin/suggested-sources/{sid}/approve", headers=h)
    again = client.post(f"/api/admin/suggested-sources/{sid}/approve", headers=h)
    assert again.status_code == 409
