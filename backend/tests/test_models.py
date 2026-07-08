from datetime import date

from app.models import Offer, OfferCategory, Source, TargetCategory
from app.models.enums import CreatedBy, DiscountType, OfferStatus, OfferType, SourceType


def test_offer_with_categories_persists(db_session):
    src = Source(name="Shop site", type=SourceType.website,
                 url_or_handle="https://shop.example", created_by=CreatedBy.admin)
    tc = TargetCategory(name="УБД", slug="ubd")
    oc = OfferCategory(name="Розваги", slug="rozvahy")
    db_session.add_all([src, tc, oc])
    db_session.flush()

    offer = Offer(
        type=OfferType.discount, title="-50% на квитки", description="desc",
        provider="Кінотеатр X", location="Київ",
        valid_from=date(2026, 7, 1), valid_until=date(2026, 8, 1),
        discount_type=DiscountType.percent, discount_value=50,
        source_id=src.id, status=OfferStatus.pending_review, created_by=CreatedBy.crawler,
        target_categories=[tc], offer_categories=[oc],
    )
    db_session.add(offer)
    db_session.flush()
    db_session.refresh(offer)

    assert offer.id is not None
    assert [c.slug for c in offer.target_categories] == ["ubd"]
    assert [c.slug for c in offer.offer_categories] == ["rozvahy"]
    assert offer.status == OfferStatus.pending_review
