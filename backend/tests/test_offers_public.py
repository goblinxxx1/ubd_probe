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
                                locations=["Київ"], target_category_ids=[tc.id], offer_category_ids=[oc.id]),
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


def _seed_variety(db_session):
    """Three published offers across distinct target/offer categories and types."""
    t1 = TargetCategory(name="УБД", slug="ubd")
    t2 = TargetCategory(name="Ветерани", slug="veteran")
    t3 = TargetCategory(name="Родини", slug="family")
    o1 = OfferCategory(name="Розваги", slug="rozvahy")
    o2 = OfferCategory(name="Здоровʼя", slug="health")
    db_session.add_all([t1, t2, t3, o1, o2])
    db_session.commit()

    def mk(title, tt, tcs, ocs):
        offer_crud.create_offer(
            db_session, OfferCreate(type=tt, title=title, provider="P",
                                    target_category_ids=tcs, offer_category_ids=ocs),
            created_by=CreatedBy.admin, status=OfferStatus.published)

    mk("A", OfferType.discount, [t1.id], [o1.id])
    mk("B", OfferType.event, [t2.id], [o2.id])
    mk("C", OfferType.discount, [t3.id], [o1.id])
    return {"t1": t1.id, "t2": t2.id, "t3": t3.id, "o1": o1.id, "o2": o2.id}


def test_filter_by_multiple_target_categories(client, db_session):
    ids = _seed_variety(db_session)
    body = client.get(
        f"/api/offers?target_category={ids['t1']}&target_category={ids['t2']}").json()
    assert body["total"] == 2
    assert sorted(o["title"] for o in body["items"]) == ["A", "B"]


def test_filter_by_multiple_types(client, db_session):
    _seed_variety(db_session)
    both = client.get("/api/offers?type=discount&type=event").json()
    assert both["total"] == 3
    one = client.get("/api/offers?type=discount").json()
    assert one["total"] == 2
    assert sorted(o["title"] for o in one["items"]) == ["A", "C"]


def test_filter_by_multiple_offer_categories(client, db_session):
    ids = _seed_variety(db_session)
    body = client.get(
        f"/api/offers?offer_category={ids['o1']}&offer_category={ids['o2']}").json()
    assert body["total"] == 3   # o1 -> A,C ; o2 -> B


def test_single_target_category_still_filters(client, db_session):
    ids = _seed_variety(db_session)
    body = client.get(f"/api/offers?target_category={ids['t1']}").json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "A"


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


def test_filter_by_multiple_locations(client, db_session):
    for title, locs in [("A", ["Київ"]), ("B", ["Львів"]), ("C", ["Одеса"])]:
        offer_crud.create_offer(
            db_session, OfferCreate(type=OfferType.discount, title=title, provider="P", locations=locs),
            created_by=CreatedBy.admin, status=OfferStatus.published)
    body = client.get("/api/offers?location=Київ&location=Одеса").json()
    assert body["total"] == 2
    assert {i["title"] for i in body["items"]} == {"A", "C"}


def test_locations_facet_endpoint_lists_published_only(client, db_session):
    offer_crud.create_offer(
        db_session, OfferCreate(type=OfferType.discount, title="A", provider="P",
                                locations=["Львів", "Київ"]),
        created_by=CreatedBy.admin, status=OfferStatus.published)
    offer_crud.create_offer(
        db_session, OfferCreate(type=OfferType.discount, title="P", provider="P", locations=["Суми"]),
        created_by=CreatedBy.crawler, status=OfferStatus.pending_review)
    assert client.get("/api/locations").json() == ["Київ", "Львів"]


def test_offer_detail_preview_serves_unpublished(client, db_session):
    from app.models import Offer
    from app.models.enums import CreatedBy, OfferStatus, OfferType
    o = Offer(type=OfferType.discount, title="Pending preview", description="d", provider="P",
              status=OfferStatus.pending_review, created_by=CreatedBy.crawler)
    db_session.add(o); db_session.commit(); db_session.refresh(o)
    # without preview -> hidden (404); with preview -> served
    assert client.get(f"/api/offers/{o.id}").status_code == 404
    r = client.get(f"/api/offers/{o.id}", params={"preview": "true"})
    assert r.status_code == 200
    assert r.json()["title"] == "Pending preview"
