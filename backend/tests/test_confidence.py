from app.services import confidence
from app.models import Offer
from app.models.enums import CreatedBy, OfferStatus, OfferType


def _mk(db, status, **kw):
    o = Offer(type=OfferType.discount, title=kw.pop("title", "T"),
              description=kw.pop("description", ""), provider=kw.pop("provider", "P"),
              status=status, created_by=CreatedBy.crawler, **kw)
    db.add(o); db.commit(); db.refresh(o)
    return o


def test_high_tier_proven_host_with_discount(db_session):
    _mk(db_session, OfferStatus.published, site_url="https://good.ua/a")
    o = _mk(db_session, OfferStatus.pending_review, site_url="https://good.ua/b",
            discount_type="percent", discount_value=20)
    c = confidence.score_offer(db_session, o, {})
    assert c.tier == "high"
    assert c.host == "good.ua" and c.host_published == 1 and c.host_rejected == 0
    assert "proven_host" in c.signals


def test_low_tier_noisy_host(db_session):
    _mk(db_session, OfferStatus.rejected, site_url="https://noisy.ua/a")
    o = _mk(db_session, OfferStatus.pending_review, site_url="https://noisy.ua/b",
            discount_type="percent", discount_value=10)
    c = confidence.score_offer(db_session, o, {})
    assert c.tier == "low" and "noisy_host" in c.signals


def test_low_tier_missing_discount(db_session):
    _mk(db_session, OfferStatus.published, site_url="https://good.ua/x")
    o = _mk(db_session, OfferStatus.pending_review, site_url="https://good.ua/y")  # no discount
    c = confidence.score_offer(db_session, o, {})
    assert c.tier == "low" and "no_discount" in c.signals


def test_medium_tier_new_host(db_session):
    o = _mk(db_session, OfferStatus.pending_review, site_url="https://fresh.ua/a",
            discount_type="percent", discount_value=15)
    c = confidence.score_offer(db_session, o, {})
    assert c.tier == "medium" and "new_host" in c.signals


def test_primary_host_falls_back_to_article_url(db_session):
    o = _mk(db_session, OfferStatus.pending_review, site_url=None,
            article_url="https://blog.ua/p", discount_type="percent", discount_value=5)
    assert confidence.score_offer(db_session, o, {}).host == "blog.ua"


def test_completeness_signals(db_session):
    o = _mk(db_session, OfferStatus.pending_review, site_url="https://x.ua/a")
    c = confidence.score_offer(db_session, o, {})
    assert {"no_discount", "no_location", "no_category"} <= set(c.signals)


def test_host_reputation_memo_counts_once(db_session):
    from app.crud.offer import host_reputation
    _mk(db_session, OfferStatus.published, site_url="https://h.ua/a")
    memo = {}
    assert host_reputation(db_session, "h.ua", memo) == (1, 0)
    assert "h.ua" in memo
    assert host_reputation(db_session, "h.ua", memo) == (1, 0)   # served from memo


def test_enrich_pending_attaches_confidence(db_session):
    a = _mk(db_session, OfferStatus.pending_review, site_url="https://a.ua/x",
            discount_type="percent", discount_value=10)
    b = _mk(db_session, OfferStatus.pending_review, site_url="https://b.ua/y")
    confidence.enrich_pending(db_session, [a, b])
    assert a.confidence.tier in ("high", "medium", "low")
    assert b.confidence.tier == "low"   # no discount
