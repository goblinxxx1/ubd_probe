from app.core.config import settings
from app.core.security import create_access_token
from app.models import AdminUser
from app.models.enums import AdminRole


def _token(db_session):
    admin = AdminUser(email="mod@example.com", password_hash="x", role=AdminRole.moderator)
    db_session.add(admin)
    db_session.commit()
    return create_access_token(subject=admin.email, role="moderator")


def test_admin_creates_source(client, db_session):
    h = {"Authorization": f"Bearer {_token(db_session)}"}
    resp = client.post("/api/admin/sources",
                       json={"name": "TG channel", "type": "telegram", "url_or_handle": "@vets"},
                       headers=h)
    assert resp.status_code == 200
    assert resp.json()["created_by"] == "admin"


def test_internal_sources_requires_api_key(client, db_session):
    assert client.get("/api/internal/sources").status_code == 401
    resp = client.get("/api/internal/sources",
                      headers={"X-API-Key": settings.crawler_api_key})
    assert resp.status_code == 200


def test_internal_sources_filters_active(client, db_session):
    h = {"Authorization": f"Bearer {_token(db_session)}"}
    client.post("/api/admin/sources",
                json={"name": "A", "type": "website", "url_or_handle": "https://a", "is_active": True},
                headers=h)
    client.post("/api/admin/sources",
                json={"name": "B", "type": "website", "url_or_handle": "https://b", "is_active": False},
                headers=h)
    resp = client.get("/api/internal/sources",
                      headers={"X-API-Key": settings.crawler_api_key})
    names = [s["name"] for s in resp.json()]
    assert names == ["A"]


def test_normalize_source_ref():
    from app.core.urlnorm import normalize_source_ref
    assert normalize_source_ref("HTTPS://Shop.Example.com/deal/?utm_source=x#frag") \
        == "https://shop.example.com/deal"
    assert normalize_source_ref("https://ex.com/") == "https://ex.com"
    assert normalize_source_ref("not a url") is None
    assert normalize_source_ref("") is None


def test_get_or_create_source_by_ref_creates_then_reuses(db_session):
    from app.crud import source as source_crud
    from app.models.enums import CreatedBy, SourceType
    a = source_crud.get_or_create_source_by_ref(
        db_session, SourceType.website, "https://shop.example/deal", "Shop", CreatedBy.crawler)
    b = source_crud.get_or_create_source_by_ref(
        db_session, SourceType.website, "https://shop.example/deal", "Shop", CreatedBy.crawler)
    assert a.id == b.id
    assert a.name == "Shop" and a.type == SourceType.website and a.is_active is True


def test_get_or_create_source_by_ref_reactivates(db_session):
    from app.crud import source as source_crud
    from app.models.enums import CreatedBy, SourceType
    a = source_crud.get_or_create_source_by_ref(
        db_session, SourceType.website, "https://shop.example/x", "Shop", CreatedBy.crawler)
    a.is_active = False
    db_session.commit()
    b = source_crud.get_or_create_source_by_ref(
        db_session, SourceType.website, "https://shop.example/x", "Shop", CreatedBy.crawler)
    assert b.id == a.id and b.is_active is True
