from app.crud import offer as offer_crud
from app.models import Offer, OfferCategory, TargetCategory
from app.models.enums import CreatedBy, OfferStatus, OfferType
from app.schemas.offer import OfferCreate


def _seed(db_session):
    tc = TargetCategory(name="УБД", slug="ubd")
    oc = OfferCategory(name="Розваги", slug="rozvahy")
    db_session.add_all([tc, oc])
    db_session.commit()
    offer_crud.create_offer(
        db_session, OfferCreate(type=OfferType.discount, title="Published", provider="P",
                                location="Київ", target_category_ids=[tc.id], offer_category_ids=[oc.id]),
        created_by=CreatedBy.admin, status=OfferStatus.published)
    offer_crud.create_offer(
        db_session, OfferCreate(type=OfferType.event, title="Pending", provider="P"),
        created_by=CreatedBy.crawler, status=OfferStatus.pending_review)
    return tc, oc


def test_public_lists_only_published(client, db_session):
    _seed(db_session)
    body = client.get("/api/offers").json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Published"


def test_filter_by_type(client, db_session):
    _seed(db_session)
    body = client.get("/api/offers?type=event").json()
    assert body["total"] == 0  # the only event is pending, not published


def test_filter_by_offer_category(client, db_session):
    _, oc = _seed(db_session)
    body = client.get(f"/api/offers?offer_category={oc.id}").json()
    assert body["total"] == 1


def test_get_pending_offer_returns_404(client, db_session):
    _seed(db_session)
    all_ids = [o["id"] for o in client.get("/api/offers").json()["items"]]
    # request an id that is pending: fetch via search shows only published, so pick published+1
    resp = client.get(f"/api/offers/{max(all_ids) + 1}")
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


def test_get_real_pending_offer_returns_404(client, db_session):
    _seed(db_session)
    pending = db_session.query(Offer).filter(Offer.title == "Pending").one()
    resp = client.get(f"/api/offers/{pending.id}")
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


def test_page_zero_rejected(client, db_session):
    _seed(db_session)
    resp = client.get("/api/offers?page=0")
    assert resp.status_code == 422


def test_size_too_large_rejected(client, db_session):
    _seed(db_session)
    resp = client.get("/api/offers?size=1000")
    assert resp.status_code == 422
