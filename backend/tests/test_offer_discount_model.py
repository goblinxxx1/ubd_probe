from decimal import Decimal

from app.models import Offer, OfferDiscount
from app.models.enums import CreatedBy, DiscountType, OfferStatus, OfferType


def test_offer_discounts_relationship_ordered(db_session):
    o = Offer(type=OfferType.discount, title="T", description="", provider="P",
              status=OfferStatus.pending_review, created_by=CreatedBy.crawler)
    o.discounts = [
        OfferDiscount(label="ЗСУ", discount_type=DiscountType.percent,
                      discount_value=Decimal("15"), sort_order=1),
        OfferDiscount(label="МВС", discount_type=DiscountType.percent,
                      discount_value=Decimal("10"), sort_order=0),
    ]
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    assert [d.label for d in o.discounts] == ["МВС", "ЗСУ"]
    assert o.discounts[0].discount_value == Decimal("10")
