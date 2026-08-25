from app.core.security import create_access_token
from app.crud import offer as offer_crud
from app.models import AdminUser
from app.models.enums import AdminRole, CreatedBy, OfferStatus, OfferType
from app.schemas.offer import OfferCreate


def _admin_token(db_session):
    admin = AdminUser(email="mod@example.com", password_hash="x", role=AdminRole.moderator)
    db_session.add(admin)
    db_session.commit()
    return create_access_token(subject=admin.email, role="moderator")


def test_moderation_queue_and_publish(client, db_session):
    token = _admin_token(db_session)
    h = {"Authorization": f"Bearer {token}"}
    pending = offer_crud.create_offer(
        db_session, OfferCreate(type=OfferType.discount, title="Crawled", provider="P"),
        created_by=CreatedBy.crawler, status=OfferStatus.pending_review)

    queue = client.get("/api/admin/offers?status=pending_review", headers=h).json()
    assert queue["total"] == 1

    pub = client.post(f"/api/admin/offers/{pending.id}/publish", headers=h)
    assert pub.status_code == 200
    assert pub.json()["status"] == "published"

    # now visible publicly
    assert client.get("/api/offers").json()["total"] == 1


def test_admin_offers_requires_auth(client):
    assert client.get("/api/admin/offers").status_code == 401


def test_admin_sees_expired_published_offer(client, db_session):
    import datetime
    token = _admin_token(db_session)
    h = {"Authorization": f"Bearer {token}"}
    today = datetime.date.today()
    offer_crud.create_offer(
        db_session, OfferCreate(type=OfferType.discount, title="Old", provider="P",
                                valid_until=today - datetime.timedelta(days=1)),
        created_by=CreatedBy.admin, status=OfferStatus.published)
    offer_crud.create_offer(
        db_session, OfferCreate(type=OfferType.discount, title="Live", provider="P"),
        created_by=CreatedBy.admin, status=OfferStatus.published)
    items = {i["title"]: i for i in client.get("/api/admin/offers?status=published", headers=h).json()["items"]}
    # admin still SEES the expired offer (unlike public, which soft-hides it)
    assert "Old" in items and "Live" in items
    # is_expired flag removed from admin serialization (column dropped)
    assert "is_expired" not in items["Old"]


def test_list_offers_search_by_q(client, db_session):
    token = _admin_token(db_session)
    h = {"Authorization": f"Bearer {token}"}
    offer_crud.create_offer(
        db_session, OfferCreate(type=OfferType.discount, title="Кава знижка", provider="Coffee House"),
        created_by=CreatedBy.admin, status=OfferStatus.published)
    offer_crud.create_offer(
        db_session, OfferCreate(type=OfferType.discount, title="Спортзал", provider="Gym Co"),
        created_by=CreatedBy.admin, status=OfferStatus.published)

    resp = client.get("/api/admin/offers?q=Кава", headers=h)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Кава знижка"


def test_update_offer_rejects_invalid_dates_and_discount(client, db_session):
    token = _admin_token(db_session)
    h = {"Authorization": f"Bearer {token}"}
    published = offer_crud.create_offer(
        db_session, OfferCreate(type=OfferType.discount, title="Deal", provider="P"),
        created_by=CreatedBy.admin, status=OfferStatus.published)

    bad_dates = client.patch(f"/api/admin/offers/{published.id}",
                             json={"valid_from": "2026-08-01", "valid_until": "2026-07-01"},
                             headers=h)
    assert bad_dates.status_code == 422
    assert bad_dates.json()["code"] == "validation_error"

    bad_discount = client.patch(f"/api/admin/offers/{published.id}",
                                json={"discount_type": "free", "discount_value": 10},
                                headers=h)
    assert bad_discount.status_code == 422
    assert bad_discount.json()["code"] == "validation_error"


def test_restore_offer_returns_to_queue(client, db_session):
    token = _admin_token(db_session)
    h = {"Authorization": f"Bearer {token}"}
    rejected = offer_crud.create_offer(
        db_session, OfferCreate(type=OfferType.discount, title="Junk", provider="P"),
        created_by=CreatedBy.crawler, status=OfferStatus.rejected)

    resp = client.post(f"/api/admin/offers/{rejected.id}/restore", headers=h)
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending_review"

    queue = client.get("/api/admin/offers?status=pending_review", headers=h).json()
    assert queue["total"] == 1


def test_restore_non_rejected_offer_is_422(client, db_session):
    token = _admin_token(db_session)
    h = {"Authorization": f"Bearer {token}"}
    published = offer_crud.create_offer(
        db_session, OfferCreate(type=OfferType.discount, title="Live", provider="P"),
        created_by=CreatedBy.admin, status=OfferStatus.published)

    resp = client.post(f"/api/admin/offers/{published.id}/restore", headers=h)
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"

    # статус лишається незмінним, оффер не знято з публікації
    assert offer_crud.get_offer(db_session, published.id).status == OfferStatus.published


def test_block_host_from_site_url_approves_host(client, db_session):
    token = _admin_token(db_session)
    h = {"Authorization": f"Bearer {token}"}
    offer = offer_crud.create_offer(
        db_session,
        OfferCreate(type=OfferType.discount, title="Junk", provider="News Site",
                    site_url="https://www.junk-media.example/promo?utm_source=x"),
        created_by=CreatedBy.crawler, status=OfferStatus.pending_review)

    resp = client.post(f"/api/admin/offers/{offer.id}/block-host", headers=h)
    assert resp.status_code == 200
    body = resp.json()
    assert body["host"] == "junk-media.example"   # bare host: no scheme/www/path
    assert body["status"] == "approved"

    # host now in the crawler's LEARNED list
    blocked = client.get("/api/admin/host-candidates?status=approved", headers=h).json()
    assert any(b["host"] == "junk-media.example" for b in blocked)

    # offer itself is untouched
    assert client.get(f"/api/admin/offers/{offer.id}", headers=h).json()["status"] == "pending_review"


def test_block_host_falls_back_to_link_site_url(client, db_session):
    token = _admin_token(db_session)
    h = {"Authorization": f"Bearer {token}"}
    # no offer-level site_url; link carries it
    offer = offer_crud.create_offer(
        db_session,
        OfferCreate(type=OfferType.discount, title="Junk", provider="P",
                    site_url="https://linkhost.example/deal"),
        created_by=CreatedBy.crawler, status=OfferStatus.pending_review)
    offer.site_url = None
    db_session.commit()

    resp = client.post(f"/api/admin/offers/{offer.id}/block-host", headers=h)
    assert resp.status_code == 200
    assert resp.json()["host"] == "linkhost.example"


def test_block_host_without_host_is_422(client, db_session):
    token = _admin_token(db_session)
    h = {"Authorization": f"Bearer {token}"}
    offer = offer_crud.create_offer(
        db_session, OfferCreate(type=OfferType.discount, title="No host", provider="P"),
        created_by=CreatedBy.admin, status=OfferStatus.pending_review)
    for link in offer.links:
        link.site_url = None
    db_session.commit()

    resp = client.post(f"/api/admin/offers/{offer.id}/block-host", headers=h)
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


def _mk_offer(db, status, **kw):
    from app.models import Offer
    o = Offer(type=OfferType.discount, title=kw.pop("title", "T"), description="",
              provider=kw.pop("provider", "P"), status=status, created_by=CreatedBy.crawler, **kw)
    db.add(o); db.commit(); db.refresh(o)
    return o


def test_bulk_reject_rejects_all_given(client, db_session):
    token = _admin_token(db_session); h = {"Authorization": f"Bearer {token}"}
    ids = [_mk_offer(db_session, OfferStatus.pending_review,
                     site_url=f"https://x{i}.ua/a").id for i in range(3)]
    r = client.post("/api/admin/offers/bulk-reject", json={"ids": ids}, headers=h)
    assert r.status_code == 200
    assert sorted(r.json()["rejected"]) == sorted(ids)
    assert r.json()["failed"] == []
    for oid in ids:
        db_session.expire_all()
        assert offer_crud.get_offer(db_session, oid).status == OfferStatus.rejected


def test_bulk_reject_reports_missing_id_in_failed(client, db_session):
    token = _admin_token(db_session); h = {"Authorization": f"Bearer {token}"}
    real = _mk_offer(db_session, OfferStatus.pending_review, site_url="https://r.ua/a").id
    r = client.post("/api/admin/offers/bulk-reject", json={"ids": [real, 99999]}, headers=h)
    assert r.status_code == 200
    assert r.json()["rejected"] == [real]
    assert [f["id"] for f in r.json()["failed"]] == [99999]


def test_bulk_reject_empty_ids_422(client, db_session):
    token = _admin_token(db_session); h = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/admin/offers/bulk-reject", json={"ids": []}, headers=h).status_code == 422


def test_bulk_reject_requires_admin(client):
    assert client.post("/api/admin/offers/bulk-reject", json={"ids": [1]}).status_code == 401
