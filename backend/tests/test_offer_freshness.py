from datetime import datetime

from app.crud import offer as offer_crud
from app.models.enums import CreatedBy, OfferStatus
from app.schemas.offer import OfferCreate


def _offer(**over):
    base = dict(type="discount", title="T", provider="P", discount_type="percent",
                discount_value="10", site_url="https://a/x", article_url="https://a/x",
                target_url="https://biz/deal")
    base.update(over)
    return OfferCreate(**base)


def test_create_sets_last_seen_at(db_session):
    o = offer_crud.create_offer(db_session, _offer(target_url=None), CreatedBy.crawler,
                                OfferStatus.pending_review, content_hash="h1")
    assert isinstance(o.last_seen_at, datetime)


def test_resubmit_same_content_hash_bumps_last_seen(db_session):
    a = offer_crud.create_offer(db_session, _offer(target_url=None), CreatedBy.crawler,
                                OfferStatus.pending_review, content_hash="h1")
    a.last_seen_at = datetime(2000, 1, 1)
    db_session.commit()
    b = offer_crud.create_offer(db_session, _offer(target_url=None), CreatedBy.crawler,
                                OfferStatus.pending_review, content_hash="h1")
    assert b.id == a.id
    assert b.last_seen_at > datetime(2000, 1, 1)


def test_resubmit_same_target_url_bumps_last_seen(db_session):
    a = offer_crud.create_offer(db_session, _offer(target_url="https://biz/deal"),
                                CreatedBy.crawler, OfferStatus.pending_review)
    a.last_seen_at = datetime(2000, 1, 1)
    db_session.commit()
    b = offer_crud.create_offer(db_session, _offer(target_url="https://biz/deal", provider="Q"),
                                CreatedBy.crawler, OfferStatus.pending_review)
    assert b.id == a.id
    assert b.last_seen_at > datetime(2000, 1, 1)
