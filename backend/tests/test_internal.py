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
