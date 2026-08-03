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


from app.crud import source as source_crud
from app.schemas.source import SourceCreate
from app.models.enums import CreatedBy, SourceType


def test_create_source_dedups_website_by_host(db_session):
    a = source_crud.create_source(db_session, SourceCreate(
        name="Root", type=SourceType.website, url_or_handle="https://batart.army"),
        created_by=CreatedBy.admin)
    b = source_crud.create_source(db_session, SourceCreate(
        name="Specials", type=SourceType.website,
        url_or_handle="https://batart.army/en/specials?page=2"), created_by=CreatedBy.admin)
    assert b.id == a.id                                   # same host -> existing returned
    n = db_session.query(source_crud.Source).filter_by(url_or_handle="https://batart.army").count()
    assert n == 1


def test_create_source_allows_different_host_and_type(db_session):
    a = source_crud.create_source(db_session, SourceCreate(
        name="A", type=SourceType.website, url_or_handle="https://a.ua"),
        created_by=CreatedBy.admin)
    b = source_crud.create_source(db_session, SourceCreate(
        name="B", type=SourceType.website, url_or_handle="https://b.ua"),
        created_by=CreatedBy.admin)
    assert b.id != a.id                                   # different host -> new


def test_delete_source_with_crawl_state_and_offers(db_session):
    from app.crud import source as source_crud
    from app.schemas.source import SourceCreate
    from app.models import Offer, SourceCrawlState
    from app.models.enums import CreatedBy, OfferStatus, OfferType, SourceType
    src = source_crud.create_source(db_session, SourceCreate(
        name="S", type=SourceType.website, url_or_handle="https://del.ua"),
        created_by=CreatedBy.admin)
    db_session.add(SourceCrawlState(source_id=src.id, last_seen_key="k"))
    off = Offer(type=OfferType.discount, title="T", description="", provider="P",
                source_id=src.id, status=OfferStatus.published, created_by=CreatedBy.crawler)
    db_session.add(off)
    db_session.commit()
    off_id = off.id

    source_crud.delete_source(db_session, src.id)          # must NOT raise IntegrityError
    db_session.expire_all()
    assert db_session.get(source_crud.Source, src.id) is None          # source gone
    assert db_session.get(Offer, off_id).source_id is None             # offer orphaned, survives
    assert db_session.query(SourceCrawlState).filter_by(source_id=src.id).count() == 0


def test_delete_source_that_discovered_a_suggestion(db_session):
    # 3rd FK to sources.id: suggested_sources.discovered_from_source_id (RESTRICT) — must not 500.
    from app.crud import source as source_crud
    from app.schemas.source import SourceCreate
    from app.models import SuggestedSource
    from app.models.enums import CreatedBy, SourceType, SuggestionStatus
    src = source_crud.create_source(db_session, SourceCreate(
        name="Disc", type=SourceType.website, url_or_handle="https://disc.ua"),
        created_by=CreatedBy.admin)
    sug = SuggestedSource(name="Found", type=SourceType.website,
                          url_or_handle="https://found.ua",
                          discovered_from_source_id=src.id, status=SuggestionStatus.pending)
    db_session.add(sug)
    db_session.commit()
    sug_id = sug.id

    source_crud.delete_source(db_session, src.id)          # must NOT raise IntegrityError
    db_session.expire_all()
    assert db_session.get(source_crud.Source, src.id) is None
    assert db_session.get(SuggestedSource, sug_id).discovered_from_source_id is None  # nulled, survives
