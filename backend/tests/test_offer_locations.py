from app.crud import offer as offer_crud
from app.models import Offer, OfferLocation, TargetCategory
from app.models.enums import CreatedBy, OfferStatus, OfferType
from app.schemas.offer import OfferCreate, OfferOut, OfferUpdate


def _mk(db, title, locations, status=OfferStatus.published, created_by=CreatedBy.admin):
    return offer_crud.create_offer(
        db, OfferCreate(type=OfferType.discount, title=title, provider="P", locations=locations),
        created_by=created_by, status=status)


def test_location_names_proxy_roundtrip_and_cascade(db_session):
    o = Offer(type=OfferType.discount, title="T", description="", provider="P",
              status=OfferStatus.pending_review, created_by=CreatedBy.crawler)
    o.location_names = ["Київ", "Львів"]
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    assert sorted(o.location_names) == ["Київ", "Львів"]
    assert db_session.query(OfferLocation).count() == 2
    o.location_names = ["Одеса"]
    db_session.commit()
    assert o.location_names == ["Одеса"]
    assert db_session.query(OfferLocation).count() == 1
    db_session.delete(o)
    db_session.commit()
    assert db_session.query(OfferLocation).count() == 0


def test_create_dedupes_and_strips_locations(db_session):
    o = _mk(db_session, "A", ["Київ", " Київ ", "", "Львів"])
    assert sorted(o.location_names) == ["Київ", "Львів"]


def test_offer_out_serializes_names(db_session):
    o = _mk(db_session, "A", ["Київ", "Львів"])
    assert sorted(OfferOut.model_validate(o).locations) == ["Київ", "Львів"]
    o2 = offer_crud.create_offer(
        db_session, OfferCreate(type=OfferType.event, title="B", provider="P"),
        created_by=CreatedBy.admin, status=OfferStatus.published)
    assert OfferOut.model_validate(o2).locations == []


def test_update_replaces_locations(db_session):
    o = _mk(db_session, "A", ["Київ"])
    offer_crud.update_offer(db_session, o.id, OfferUpdate(locations=["Одеса", "Львів"]))
    db_session.refresh(o)
    assert sorted(o.location_names) == ["Львів", "Одеса"]


def test_update_without_locations_keeps_them(db_session):
    o = _mk(db_session, "A", ["Київ"])
    offer_crud.update_offer(db_session, o.id, OfferUpdate(title="A2"))
    db_session.refresh(o)
    assert o.location_names == ["Київ"]


def test_list_offers_filters_by_any_location(db_session):
    _mk(db_session, "A", ["Київ"]); _mk(db_session, "B", ["Львів"]); _mk(db_session, "C", ["Одеса"])
    items, total = offer_crud.list_offers(db_session, status=OfferStatus.published,
                                          locations=["Київ", "Одеса"])
    assert total == 2
    assert {i.title for i in items} == {"A", "C"}


def test_facet_lists_distinct_published_only(db_session):
    _mk(db_session, "A", ["Київ", "Львів"]); _mk(db_session, "B", ["Київ"])
    _mk(db_session, "P", ["Суми"], status=OfferStatus.pending_review, created_by=CreatedBy.crawler)
    assert offer_crud.list_distinct_locations(db_session) == ["Київ", "Львів"]
