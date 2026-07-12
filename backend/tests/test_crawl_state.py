from app.core.config import settings
from app.models import Source
from app.models.enums import CreatedBy, SourceType


def _make_source(db):
    s = Source(name="S", type=SourceType.website, url_or_handle="http://x",
               is_active=True, created_by=CreatedBy.admin)
    db.add(s); db.commit(); db.refresh(s)
    return s


def test_crawl_state_roundtrip(client, db_session):
    src = _make_source(db_session)
    h = {"X-API-Key": settings.crawler_api_key}

    r0 = client.get(f"/api/internal/sources/{src.id}/crawl-state", headers=h)
    assert r0.status_code == 200
    assert r0.json()["last_seen_key"] is None

    r1 = client.post(f"/api/internal/sources/{src.id}/crawl-state",
                     json={"last_seen_key": "post-42"}, headers=h)
    assert r1.status_code == 200
    assert r1.json()["last_seen_key"] == "post-42"
    assert r1.json()["last_crawled_at"] is not None

    r2 = client.get(f"/api/internal/sources/{src.id}/crawl-state", headers=h)
    assert r2.json()["last_seen_key"] == "post-42"


def test_crawl_state_unknown_source_404(client, db_session):
    h = {"X-API-Key": settings.crawler_api_key}
    assert client.get("/api/internal/sources/9999/crawl-state", headers=h).status_code == 404


def test_crawl_state_requires_api_key(client, db_session):
    src = _make_source(db_session)
    assert client.get(f"/api/internal/sources/{src.id}/crawl-state").status_code == 401
