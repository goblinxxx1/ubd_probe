from datetime import datetime

from app.crud import offer as offer_crud
from app.crud import blocked_host as bh
from app.crud import source as source_crud
from app.models import Offer
from app.models.enums import CreatedBy, OfferStatus
from app.schemas.offer import OfferCreate
from app.schemas.source import SourceCreate


def _offer(article, *, target=None, provider="P", val="10", title="T",
           site="https://shop.ua"):
    return OfferCreate(type="discount", title=title, provider=provider,
                       discount_type="percent", discount_value=val,
                       site_url=site, article_url=article, target_url=target)


def _create(db, data, *, status=OfferStatus.pending_review, ch=None, source_id=None):
    return offer_crud.create_offer(db, data, CreatedBy.crawler, status,
                                   source_id=source_id, content_hash=ch)


def test_same_page_variants_collapse_to_one_pending(db_session):
    # byte-different URL forms (www / trailing slash / utm) + drifted content_hash
    a = _create(db_session, _offer("https://shop.ua/promo"), ch="h1")
    b = _create(db_session, _offer("https://www.shop.ua/promo/?utm_source=fb", val="20"),
                ch="h2")
    assert b.id == a.id
    assert db_session.query(Offer).count() == 1


def test_rejected_page_does_not_return_to_queue(db_session):
    a = _create(db_session, _offer("https://shop.ua/promo"), ch="h1")
    a.status = OfferStatus.rejected
    db_session.commit()
    b = _create(db_session, _offer("https://shop.ua/promo", val="20"), ch="h2")
    assert b.id == a.id
    assert b.status == OfferStatus.rejected            # stays rejected, no fresh pending
    assert db_session.query(Offer).count() == 1


def test_published_page_bumps_last_seen_without_shadow(db_session):
    a = _create(db_session, _offer("https://shop.ua/promo"), ch="h1")
    a.status = OfferStatus.published
    a.last_seen_at = datetime(2000, 1, 1)
    db_session.commit()
    b = _create(db_session, _offer("https://shop.ua/promo", val="20"), ch="h2")
    assert b.id == a.id
    assert b.supersedes_offer_id is None               # discovered published -> skip, not shadow
    assert b.last_seen_at > datetime(2000, 1, 1)


def test_different_pages_stay_separate(db_session):
    a = _create(db_session, _offer("https://shop.ua/one"), ch="h1")
    b = _create(db_session, _offer("https://shop.ua/two"), ch="h2")
    assert a.id != b.id


def test_source_bound_offer_unaffected(db_session):
    # with a real source, branch 3 (update-in-place) still applies; the new
    # source_id=None branch must not swallow it.
    s = source_crud.create_source(
        db_session, SourceCreate(name="S", type="website",
                                 url_or_handle="https://shop.ua", is_active=True),
        CreatedBy.crawler)
    a = _create(db_session, _offer("https://shop.ua/promo"), ch="h1", source_id=s.id)
    b = _create(db_session, _offer("https://shop.ua/promo", val="20"), ch="h2",
                source_id=s.id)
    assert b.id == a.id                                # branch 3 updates in place
    assert str(b.discount_value) == "20.00"            # branch 3 DID apply content


def test_blocked_source_duplicate_collapses_by_page(db_session):
    bh.auto_block(db_session, "shop.ua")
    a = _create(db_session, _offer("https://shop.ua/promo"), ch="h1")
    assert a.status == OfferStatus.rejected            # blocked -> forced reject
    b = _create(db_session, _offer("https://shop.ua/promo", val="20"), ch="h2")
    assert b.id == a.id                                # drifted content still collapses
    assert db_session.query(Offer).count() == 1
