from datetime import datetime

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


def _source(db):
    return source_crud.create_source(
        db, SourceCreate(name="S", type="website", url_or_handle="https://a/x", is_active=True),
        CreatedBy.crawler)


def _published(db, sid, ch, value="10"):
    o = offer_crud.create_offer(db, _offer(discount_value=value), CreatedBy.crawler,
                                OfferStatus.published, source_id=sid, content_hash=ch)
    return o


def test_changed_discount_creates_linked_shadow(db_session):
    s = _source(db_session)
    p = _published(db_session, s.id, "h1", value="10")
    shadow = offer_crud.create_offer(db_session, _offer(discount_value="20"), CreatedBy.crawler,
                                     OfferStatus.pending_review, source_id=s.id, content_hash="h2")
    assert shadow.id != p.id
    assert shadow.status == OfferStatus.pending_review
    assert shadow.supersedes_offer_id == p.id
    assert str(shadow.discount_value) == "20.00"
    db_session.refresh(p)
    assert p.status == OfferStatus.published            # parent stays live


def test_change_bumps_parent_last_seen(db_session):
    s = _source(db_session)
    p = _published(db_session, s.id, "h1")
    p.last_seen_at = datetime(2000, 1, 1)
    db_session.commit()
    offer_crud.create_offer(db_session, _offer(discount_value="20"), CreatedBy.crawler,
                            OfferStatus.pending_review, source_id=s.id, content_hash="h2")
    db_session.refresh(p)
    assert p.last_seen_at > datetime(2000, 1, 1)


def test_repeated_change_updates_single_shadow(db_session):
    s = _source(db_session)
    p = _published(db_session, s.id, "h1")
    a = offer_crud.create_offer(db_session, _offer(discount_value="20"), CreatedBy.crawler,
                                OfferStatus.pending_review, source_id=s.id, content_hash="h2")
    b = offer_crud.create_offer(db_session, _offer(discount_value="30"), CreatedBy.crawler,
                                OfferStatus.pending_review, source_id=s.id, content_hash="h3")
    assert b.id == a.id                                 # same shadow, updated in place
    assert str(b.discount_value) == "30.00"
    assert b.content_hash == "h3"


def test_unchanged_published_rewalk_bumps_no_shadow(db_session):
    s = _source(db_session)
    p = _published(db_session, s.id, "h1")
    again = offer_crud.create_offer(db_session, _offer(discount_value="10"), CreatedBy.crawler,
                                    OfferStatus.pending_review, source_id=s.id, content_hash="h1")
    assert again.id == p.id                             # content_hash match -> bump, no shadow


def test_pending_first_submission_updates_in_place(db_session):
    s = _source(db_session)
    q = offer_crud.create_offer(db_session, _offer(discount_value="10"), CreatedBy.crawler,
                                OfferStatus.pending_review, source_id=s.id, content_hash="h1")
    r = offer_crud.create_offer(db_session, _offer(discount_value="20"), CreatedBy.crawler,
                                OfferStatus.pending_review, source_id=s.id, content_hash="h2")
    assert r.id == q.id                                 # no shadow while still pending
    assert r.supersedes_offer_id is None
    assert str(r.discount_value) == "20.00"


def test_revert_to_parent_content_drops_stale_shadow(db_session):
    s = _source(db_session)
    p = _published(db_session, s.id, "h1", value="10")
    shadow = offer_crud.create_offer(db_session, _offer(discount_value="20"), CreatedBy.crawler,
                                     OfferStatus.pending_review, source_id=s.id, content_hash="h2")
    assert shadow.supersedes_offer_id == p.id
    back = offer_crud.create_offer(db_session, _offer(discount_value="10"), CreatedBy.crawler,
                                   OfferStatus.pending_review, source_id=s.id, content_hash="h1")
    assert back.id == p.id                              # reverted -> matches parent
    db_session.refresh(shadow)
    assert shadow.status == OfferStatus.rejected        # stale shadow dropped from queue
