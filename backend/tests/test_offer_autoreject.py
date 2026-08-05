from app.crud import offer as offer_crud
from app.crud import blocked_host as bh
from app.schemas.offer import OfferCreate
from app.models.enums import CreatedBy, OfferStatus


def _crawler(db, **kw):
    data = OfferCreate(type="discount", title=kw.pop("title", "T"),
                       provider=kw.pop("provider", "Biz"), **kw)
    return offer_crud.create_offer(db, data, CreatedBy.crawler, OfferStatus.pending_review)


def test_gate_rejects_offer_from_blocked_site_host(db_session):
    bh.auto_block(db_session, "fraza.ua")
    o = _crawler(db_session, site_url="https://fraza.ua/x", article_url="https://fraza.ua/x",
                 provider="uglovoy.com.ua", target_url="https://uglovoy.com.ua")
    assert o.status == OfferStatus.rejected


def test_gate_matches_subdomain_of_blocked_host(db_session):
    bh.auto_block(db_session, "znaj.ua")
    o = _crawler(db_session, article_url="https://breaking.znaj.ua/post", provider="Shop")
    assert o.status == OfferStatus.rejected


def test_gate_rejects_on_blocked_provider_host(db_session):
    bh.auto_block(db_session, "google.com")
    o = _crawler(db_session, provider="google.com", site_url="https://google.com/x")
    assert o.status == OfferStatus.rejected


def test_gate_passes_clean_business_host(db_session):
    o = _crawler(db_session, site_url="https://reima.ua/mil", provider="reima.ua",
                 target_url="https://reima.ua")
    assert o.status == OfferStatus.pending_review


def test_gate_ignores_admin_offers(db_session):
    bh.auto_block(db_session, "fraza.ua")
    data = OfferCreate(type="discount", title="T", provider="fraza.ua",
                       site_url="https://fraza.ua/x")
    o = offer_crud.create_offer(db_session, data, CreatedBy.admin, OfferStatus.published)
    assert o.status == OfferStatus.published   # admin path untouched
