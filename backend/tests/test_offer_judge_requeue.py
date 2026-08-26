from app.crud import offer as offer_crud
from app.models.enums import CreatedBy, OfferStatus


def _mk(db, status, created_by=CreatedBy.crawler, **kw):
    from app.models.offer import Offer
    from app.models.enums import OfferType
    o = Offer(type=OfferType.discount, title=kw.get("title", "T"), description="",
             provider=kw.get("provider", "P"), status=status, created_by=created_by,
             site_url=kw.get("site_url"), article_url=kw.get("article_url"))
    db.add(o); db.commit(); db.refresh(o)
    return o


def test_judge_reject_flips_pending_crawler_offer(db_session):
    o = _mk(db_session, OfferStatus.pending_review, created_by=CreatedBy.crawler)
    out = offer_crud.judge_reject(db_session, o.id, "junk: no discount context")
    assert out.status == OfferStatus.rejected
    assert out.reviewed_by is None
    assert out.rejection_reason == "junk: no discount context"


def test_judge_reject_accepts_crawler_suggestion_created_by(db_session):
    o = _mk(db_session, OfferStatus.pending_review, created_by=CreatedBy.crawler_suggestion)
    out = offer_crud.judge_reject(db_session, o.id, "junk")
    assert out.status == OfferStatus.rejected
    assert out.reviewed_by is None


def test_judge_reject_refuses_published_offer(db_session):
    o = _mk(db_session, OfferStatus.published, created_by=CreatedBy.crawler)
    try:
        offer_crud.judge_reject(db_session, o.id, "junk")
        assert False, "expected an error for a published offer"
    except Exception:
        pass
    db_session.refresh(o)
    assert o.status == OfferStatus.published   # untouched
    assert o.rejection_reason is None


def test_judge_reject_refuses_admin_created_offer(db_session):
    o = _mk(db_session, OfferStatus.pending_review, created_by=CreatedBy.admin)
    try:
        offer_crud.judge_reject(db_session, o.id, "junk")
        assert False, "expected an error for an admin-created offer"
    except Exception:
        pass
    db_session.refresh(o)
    assert o.status == OfferStatus.pending_review   # untouched
    assert o.reviewed_by is None
    assert o.rejection_reason is None


def test_judge_reject_refuses_already_reviewed_offer(db_session):
    # already rejected once (e.g. by admin) — judge must not re-touch it
    o = _mk(db_session, OfferStatus.rejected, created_by=CreatedBy.crawler)
    try:
        offer_crud.judge_reject(db_session, o.id, "junk")
        assert False, "expected an error for a non-pending offer"
    except Exception:
        pass


def test_list_pending_unjudged_for_crawler_filters_and_orders(db_session):
    admin_pending = _mk(db_session, OfferStatus.pending_review, created_by=CreatedBy.admin)
    published = _mk(db_session, OfferStatus.published, created_by=CreatedBy.crawler)
    c1 = _mk(db_session, OfferStatus.pending_review, created_by=CreatedBy.crawler)
    c2 = _mk(db_session, OfferStatus.pending_review, created_by=CreatedBy.crawler_suggestion)

    out = offer_crud.list_pending_unjudged_for_crawler(db_session, limit=10)

    ids = [o.id for o in out]
    assert admin_pending.id not in ids
    assert published.id not in ids
    assert ids == [c1.id, c2.id]   # oldest-first


def test_list_pending_unjudged_for_crawler_respects_limit(db_session):
    for _ in range(3):
        _mk(db_session, OfferStatus.pending_review, created_by=CreatedBy.crawler)
    out = offer_crud.list_pending_unjudged_for_crawler(db_session, limit=2)
    assert len(out) == 2
