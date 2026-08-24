from app.crud import offer as offer_crud
from app.models import Offer
from app.models.enums import CreatedBy, OfferStatus
from app.schemas.offer import OfferCreate


def _offer(article, *, val="30", dtype="percent", title="T", site=None, discounts=None):
    host_site = site or ("https://" + article.split("://", 1)[1].split("/", 1)[0])
    return OfferCreate(type="discount", title=title, provider="P",
                       discount_type=dtype, discount_value=val,
                       site_url=host_site, article_url=article,
                       discounts=discounts if discounts is not None else [])


def _create(db, data, *, status=OfferStatus.pending_review, ch=None):
    return offer_crud.create_offer(db, data, CreatedBy.crawler, status,
                                   source_id=None, content_hash=ch)


def test_listing_slug_collapses_onto_deep_peer(db_session):
    # mebelmarket: published deep offer, then /promotions listing with same 8%
    deep = _create(db_session, _offer("https://mebelmarket.ua/promotion/znyzhka-viyskovm",
                                      val="8", title="Deep offer wording"),
                   status=OfferStatus.published, ch="h1")
    hub = _create(db_session, _offer("https://mebelmarket.ua/promotions",
                                     val="8", title="Storefront listing wording"), ch="h2")
    assert hub.id == deep.id                          # collapsed onto the published deep peer
    assert db_session.query(Offer).count() == 1


def test_url_parent_collapses_onto_child(db_session):
    # whiteclinic: /promotions is a URL-parent of the published deep offer
    deep = _create(db_session, _offer("https://whiteclinic.ua/promotions/znyzhka-10",
                                      val="10", title="Deep"),
                   status=OfferStatus.published, ch="h1")
    hub = _create(db_session, _offer("https://whiteclinic.ua/promotions",
                                     val="10", title="Listing"), ch="h2")
    assert hub.id == deep.id
    assert db_session.query(Offer).count() == 1


def test_about_slug_collapses(db_session):
    deep = _create(db_session, _offer("https://m2fit.com.ua/veteran", val="15", title="Deep"),
                   status=OfferStatus.published, ch="h1")
    hub = _create(db_session, _offer("https://m2fit.com.ua/about", val="15", title="About us"),
                  ch="h2")
    assert hub.id == deep.id


def test_hub_with_new_magnitude_is_kept(db_session):
    # listing carries BOTH the published 8% AND a new 15% -> subset fails -> new offer surfaces
    deep = _create(db_session, _offer("https://shop.ua/promotion/deal", val="8", title="Deep"),
                   status=OfferStatus.published, ch="h1")
    hub = _create(db_session,
                  _offer("https://shop.ua/promotions", val="8", title="Listing",
                         discounts=[{"discount_type": "percent", "discount_value": "8"},
                                    {"discount_type": "percent", "discount_value": "15"}]),
                  ch="h2")
    assert hub.id != deep.id                          # NOT collapsed: 15% is new
    assert db_session.query(Offer).count() == 2


def test_two_deep_offer_pages_stay_separate(db_session):
    # neither is a hub -> distinct same-% offers preserved (new-candidate protection)
    a = _create(db_session, _offer("https://clinic.ua/dental-10", val="10", title="Dental"),
                status=OfferStatus.published, ch="h1")
    b = _create(db_session, _offer("https://clinic.ua/cosmetology-10", val="10",
                                   title="Cosmetology"), ch="h2")
    assert a.id != b.id
    assert db_session.query(Offer).count() == 2


def test_hub_with_no_same_host_peer_is_kept(db_session):
    hub = _create(db_session, _offer("https://lonely.ua/promotions", val="20"), ch="h1")
    assert db_session.query(Offer).count() == 1
    assert hub.article_url_canonical == "lonely.ua/promotions"


def test_hub_different_magnitude_is_kept(db_session):
    deep = _create(db_session, _offer("https://shop2.ua/promotion/deal", val="30", title="Deep"),
                   status=OfferStatus.published, ch="h1")
    hub = _create(db_session, _offer("https://shop2.ua/promotions", val="10", title="Listing"),
                  ch="h2")
    assert hub.id != deep.id                          # 10% not a subset of 30%
    assert db_session.query(Offer).count() == 2
