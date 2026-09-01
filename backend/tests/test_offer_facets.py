import datetime

from app.crud import offer as offer_crud
from app.models import OfferCategory, TargetCategory
from app.models.enums import CreatedBy, OfferStatus, OfferType
from app.schemas.offer import OfferCreate


def _mk(db, *, title, tt=OfferType.discount, tcs=None, ocs=None, locs=None,
        status=OfferStatus.published, valid_until=None):
    return offer_crud.create_offer(
        db, OfferCreate(type=tt, title=title, provider="P", valid_until=valid_until,
                        target_category_ids=tcs or [], offer_category_ids=ocs or [],
                        locations=locs or []),
        created_by=CreatedBy.admin, status=status)


def _cats(db):
    t1 = TargetCategory(name="УБД", slug="ubd")
    t2 = TargetCategory(name="Ветерани", slug="veteran")
    o1 = OfferCategory(name="Розваги", slug="rozvahy")
    o2 = OfferCategory(name="Здоровʼя", slug="health")
    db.add_all([t1, t2, o1, o2]); db.commit()
    return t1, t2, o1, o2


def test_facets_list_only_present_values(client, db_session):
    t1, t2, o1, o2 = _cats(db_session)
    # only t1/o1 are used by a published offer; t2/o2 have none
    _mk(db_session, title="A", tt=OfferType.discount, tcs=[t1.id], ocs=[o1.id], locs=["Київ"])
    _mk(db_session, title="P", tt=OfferType.event, tcs=[t2.id], ocs=[o2.id], status=OfferStatus.pending_review)
    body = client.get("/api/facets").json()
    assert [c["name"] for c in body["target_categories"]] == ["УБД"]
    assert [c["name"] for c in body["offer_categories"]] == ["Розваги"]
    assert [t["value"] for t in body["types"]] == ["discount"]   # event is only pending
    assert [c["count"] for c in body["target_categories"]] == [1]
    assert [l["name"] for l in body["locations"]] == ["Київ"]


def test_facets_expired_value_excluded(client, db_session):
    t1, _, o1, _ = _cats(db_session)
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    _mk(db_session, title="Exp", tcs=[t1.id], ocs=[o1.id], locs=["Суми"], valid_until=yesterday)
    body = client.get("/api/facets").json()
    assert body["target_categories"] == []
    assert body["locations"] == []


def test_facets_counts_are_contextual(client, db_session):
    t1, t2, o1, o2 = _cats(db_session)
    _mk(db_session, title="A", tcs=[t1.id], ocs=[o1.id], locs=["Київ"])
    _mk(db_session, title="B", tcs=[t1.id], ocs=[o2.id], locs=["Львів"])
    # no filter: УБД has 2
    base = client.get("/api/facets").json()
    assert {c["name"]: c["count"] for c in base["target_categories"]}["УБД"] == 2
    # filter to Київ: УБД contextual count drops to 1, and only o1 theme remains
    kyiv = client.get("/api/facets?location=Київ").json()
    assert {c["name"]: c["count"] for c in kyiv["target_categories"]}["УБД"] == 1
    assert [c["name"] for c in kyiv["offer_categories"]] == ["Розваги"]


def test_facets_are_disjunctive_within_a_facet(client, db_session):
    t1, t2, _, _ = _cats(db_session)
    _mk(db_session, title="A", tcs=[t1.id])
    _mk(db_session, title="B", tcs=[t2.id])
    # selecting t1 must NOT zero out t2 in the target facet (facet ignores its own selection)
    body = client.get(f"/api/facets?target_category={t1.id}").json()
    names = {c["name"]: c["count"] for c in body["target_categories"]}
    assert names == {"УБД": 1, "Ветерани": 1}


def test_facets_selected_value_with_zero_stays(client, db_session):
    t1, t2, _, _ = _cats(db_session)
    _mk(db_session, title="A", tcs=[t1.id], locs=["Київ"])   # Ветерани used by nobody
    # t2 selected but no published offer uses it -> still present with count 0 (so it can be un-checked)
    body = client.get(f"/api/facets?target_category={t2.id}").json()
    names = {c["name"]: c["count"] for c in body["target_categories"]}
    assert names.get("Ветерани") == 0


def test_facets_empty_db(client, db_session):
    body = client.get("/api/facets").json()
    assert body == {"target_categories": [], "offer_categories": [], "types": [], "locations": []}
