from app.core.config import settings


def test_crawler_submits_pending_offer(client, db_session):
    resp = client.post("/api/internal/offers",
                       json={"type": "discount", "title": "Found by crawler", "provider": "Shop"},
                       headers={"X-API-Key": settings.crawler_api_key})
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending_review"
    assert resp.json()["created_by"] == "crawler"
    # not visible publicly
    assert client.get("/api/offers").json()["total"] == 0


def test_internal_offer_requires_api_key(client):
    resp = client.post("/api/internal/offers",
                       json={"type": "discount", "title": "x", "provider": "y"})
    assert resp.status_code == 401


def test_internal_offer_rejects_unknown_source_id(client, db_session):
    resp = client.post("/api/internal/offers",
                       json={"type": "discount", "title": "x", "provider": "y", "source_id": 9999},
                       headers={"X-API-Key": settings.crawler_api_key})
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


def test_crawler_offer_dedup_is_idempotent(client, db_session):
    from app.models import Source
    from app.models.enums import CreatedBy, SourceType
    src = Source(name="Shop", type=SourceType.website, url_or_handle="http://x",
                 is_active=True, created_by=CreatedBy.admin)
    db_session.add(src); db_session.commit()

    body = {"type": "discount", "title": "20% off", "provider": "Shop",
            "source_id": src.id, "content_hash": "abc123"}
    h = {"X-API-Key": settings.crawler_api_key}

    r1 = client.post("/api/internal/offers", json=body, headers=h)
    r2 = client.post("/api/internal/offers", json=body, headers=h)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]  # same row, not a duplicate
    assert client.get("/api/offers").json()["total"] == 0  # still pending


def test_suggested_source_is_idempotent(client, db_session):
    body = {"name": "New Chan", "type": "telegram", "url_or_handle": "t.me/newchan"}
    h = {"X-API-Key": settings.crawler_api_key}
    r1 = client.post("/api/internal/suggested-sources", json=body, headers=h)
    r2 = client.post("/api/internal/suggested-sources", json=body, headers=h)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]


def test_crawler_sourceless_offer_dedup_is_idempotent(client, db_session):
    body = {"type": "discount", "title": "10% UBD", "provider": "Cafe",
            "content_hash": "hashnosrc"}   # no source_id
    h = {"X-API-Key": settings.crawler_api_key}
    r1 = client.post("/api/internal/offers", json=body, headers=h)
    r2 = client.post("/api/internal/offers", json=body, headers=h)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]      # deduped, not a duplicate
    assert r1.json()["source_id"] is None


def test_rejected_sourceless_offer_not_resurrected(client, db_session):
    from app.models import Offer
    from app.models.enums import OfferStatus
    body = {"type": "discount", "title": "x", "provider": "P", "content_hash": "hh"}
    h = {"X-API-Key": settings.crawler_api_key}
    oid = client.post("/api/internal/offers", json=body, headers=h).json()["id"]
    obj = db_session.get(Offer, oid)
    obj.status = OfferStatus.rejected
    db_session.commit()
    r2 = client.post("/api/internal/offers", json=body, headers=h)
    assert r2.json()["id"] == oid                  # same row, not a new pending one


def test_crawler_creates_offer_category(client, db_session):
    h = {"X-API-Key": settings.crawler_api_key}
    resp = client.post("/api/internal/offer-categories",
                       json={"name": "Автосервіс", "slug": "auto"}, headers=h)
    assert resp.status_code == 200
    assert resp.json()["slug"] == "auto"
    assert [c["slug"] for c in client.get("/api/offer-categories").json()] == ["auto"]


def test_crawler_offer_category_is_get_or_create(client, db_session):
    h = {"X-API-Key": settings.crawler_api_key}
    body = {"name": "Автосервіс", "slug": "auto"}
    r1 = client.post("/api/internal/offer-categories", json=body, headers=h)
    r2 = client.post("/api/internal/offer-categories", json=body, headers=h)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]           # same row, no 409
    assert len(client.get("/api/offer-categories").json()) == 1


def test_internal_offer_category_requires_api_key(client):
    resp = client.post("/api/internal/offer-categories",
                       json={"name": "X", "slug": "x"})
    assert resp.status_code == 401


def test_expire_stale_endpoint(client, db_session):
    from datetime import datetime, timedelta
    from app.crud import offer as offer_crud
    from app.crud import source as source_crud
    from app.models.enums import CreatedBy, OfferStatus
    from app.schemas.offer import OfferCreate
    from app.schemas.source import SourceCreate

    s = source_crud.create_source(
        db_session, SourceCreate(name="S", type="website", url_or_handle="https://a/x",
                                 is_active=True), CreatedBy.crawler)
    o = offer_crud.create_offer(
        db_session, OfferCreate(type="discount", title="T", provider="P"),
        CreatedBy.crawler, OfferStatus.published, source_id=s.id, content_hash="h")
    o.last_seen_at = datetime.utcnow() - timedelta(days=40)
    db_session.commit()

    r = client.post("/api/internal/offers/expire-stale", json={"older_than_days": 30},
                    headers={"X-API-Key": settings.crawler_api_key})
    assert r.status_code == 200
    assert r.json() == {"expired": 1}
    db_session.refresh(o)
    assert o.status == OfferStatus.expired
