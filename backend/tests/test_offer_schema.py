import pytest
from pydantic import ValidationError

from app.schemas.offer import OfferCreate
from app.models.enums import DiscountType, OfferType


def test_percent_requires_value():
    with pytest.raises(ValidationError):
        OfferCreate(type=OfferType.discount, title="t", provider="p",
                    discount_type=DiscountType.percent)


def test_free_forbids_value():
    with pytest.raises(ValidationError):
        OfferCreate(type=OfferType.discount, title="t", provider="p",
                    discount_type=DiscountType.free, discount_value=10)


def test_date_order():
    import datetime
    with pytest.raises(ValidationError):
        OfferCreate(type=OfferType.event, title="t", provider="p",
                    valid_from=datetime.date(2026, 8, 1), valid_until=datetime.date(2026, 7, 1))


def test_valid_percent_offer():
    o = OfferCreate(type=OfferType.discount, title="t", provider="p",
                    discount_type=DiscountType.percent, discount_value=50)
    assert o.discount_value == 50
