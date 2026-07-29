from decimal import Decimal

from app.crud import offer as offer_crud
from app.crud import source as source_crud
from app.models import Offer
from app.models.enums import CreatedBy, DiscountType, OfferStatus, OfferType
from app.schemas.offer import OfferCreate
from app.schemas.source import SourceCreate


def _mk(**kw):
    base = dict(type=OfferType.discount, title="T", provider="P",
                discount_type=DiscountType.percent, discount_value=Decimal("15"))
    base.update(kw)
    return OfferCreate(**base)


def _source(db):
    # Offer.source_id is a real FK -> sources.id; a literal id like 1/7 with no row
    # would fail on insert with an unrelated IntegrityError, not the behavior under test.
    return source_crud.create_source(
        db, SourceCreate(name="S", type="website", url_or_handle="https://ex.com", is_active=True),
        CreatedBy.crawler)


def test_create_offer_stores_discounts_list(db_session):
    s = _source(db_session)
    data = _mk(article_url="https://ex.com/promo",
               discounts=[{"label": "МВС", "discount_type": "percent", "discount_value": 10},
                          {"label": "ЗСУ", "discount_type": "percent", "discount_value": 15}])
    o = offer_crud.create_offer(db_session, data, CreatedBy.crawler,
                                OfferStatus.pending_review, source_id=s.id, content_hash="h1")
    assert [(d.label, d.discount_value) for d in o.discounts] == \
        [("МВС", Decimal("10")), ("ЗСУ", Decimal("15"))]
    assert o.article_url_canonical == "ex.com/promo"


def test_create_offer_synthesizes_single_discount_when_no_list(db_session):
    s = _source(db_session)
    o = offer_crud.create_offer(db_session, _mk(), CreatedBy.crawler,
                                OfferStatus.pending_review, source_id=s.id, content_hash="h2")
    assert len(o.discounts) == 1
    assert o.discounts[0].discount_type == DiscountType.percent
    assert o.discounts[0].discount_value == Decimal("15")


def test_page_change_shadows_via_article_url_even_with_null_target(db_session):
    s = _source(db_session)
    # published parent, target_url NULL -> identity is article_url
    parent = offer_crud.create_offer(
        db_session, _mk(article_url="https://ex.com/promo"), CreatedBy.crawler,
        OfferStatus.pending_review, source_id=s.id, content_hash="p1")
    parent.status = OfferStatus.published
    db_session.commit()
    # a changed page (new content_hash, same article_url) -> shadow, not a fresh pending
    changed = offer_crud.create_offer(
        db_session, _mk(article_url="https://ex.com/promo", discount_value=Decimal("20")),
        CreatedBy.crawler, OfferStatus.pending_review, source_id=s.id, content_hash="p2")
    assert changed.supersedes_offer_id == parent.id
    assert changed.status == OfferStatus.pending_review
