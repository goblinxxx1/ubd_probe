from datetime import datetime, timedelta

from app.crud import offer as offer_crud
from app.crud import source as source_crud
from app.models.enums import CreatedBy, OfferStatus
from app.schemas.offer import OfferCreate
from app.schemas.source import SourceCreate


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


def _source(db):
    return source_crud.create_source(
        db, SourceCreate(name="S", type="website", url_or_handle="https://a/x", is_active=True),
        CreatedBy.crawler)


def _published(db, source_id, last_seen, ch, created_by=CreatedBy.crawler):
    o = offer_crud.create_offer(db, _offer(target_url=None), created_by,
                                OfferStatus.published, source_id=source_id, content_hash=ch)
    o.last_seen_at = last_seen
    db.commit()
    db.refresh(o)
    return o


def test_expire_stale_marks_only_stale_promoted_published(db_session):
    s = _source(db_session)
    old = datetime.utcnow() - timedelta(days=40)
    fresh = datetime.utcnow()
    stale = _published(db_session, s.id, old, "h_stale")
    still_fresh = _published(db_session, s.id, fresh, "h_fresh")
    unpromoted = _published(db_session, None, old, "h_unpromoted")   # source_id None
    n = offer_crud.expire_stale(db_session, 30)
    db_session.refresh(stale); db_session.refresh(still_fresh); db_session.refresh(unpromoted)
    assert n == 1
    assert stale.status == OfferStatus.expired
    assert still_fresh.status == OfferStatus.published
    assert unpromoted.status == OfferStatus.published   # not promoted -> never expires
