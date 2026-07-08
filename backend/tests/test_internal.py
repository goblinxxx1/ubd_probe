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
