from app.crud import directory_host as dh
from app.models import Offer
from app.models.enums import OfferStatus, CreatedBy, OfferType


def _mk_offer(db, host, status=OfferStatus.pending_review, created_by=CreatedBy.crawler):
    o = Offer(type=OfferType.discount, title="t", description="", provider="P",
              status=status, created_by=created_by,
              site_url=f"https://{host}", article_url=f"https://{host}/x")
    db.add(o); db.commit(); db.refresh(o); return o


def test_register_is_idempotent(db_session):
    assert dh.register(db_session, "myhelp.com.ua") is True
    assert dh.register(db_session, "myhelp.com.ua") is False
    assert dh.list_hosts(db_session) == ["myhelp.com.ua"]


def test_register_sweeps_existing_crawler_pending_offers(db_session):
    keep_pub = _mk_offer(db_session, "myhelp.com.ua", status=OfferStatus.published)
    keep_other = _mk_offer(db_session, "otherbiz.com.ua")
    victim = _mk_offer(db_session, "myhelp.com.ua")
    dh.register(db_session, "myhelp.com.ua")
    db_session.refresh(victim); db_session.refresh(keep_pub); db_session.refresh(keep_other)
    assert victim.status == OfferStatus.rejected
    assert keep_pub.status == OfferStatus.published      # published untouched
    assert keep_other.status == OfferStatus.pending_review  # other host untouched
