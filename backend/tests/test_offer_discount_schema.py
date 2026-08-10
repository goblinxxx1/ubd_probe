# backend/tests/test_offer_discount_schema.py
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.offer import DiscountIn, OfferCreate
from app.models.enums import DiscountType, OfferType


def test_offer_create_accepts_discounts_list():
    oc = OfferCreate(type=OfferType.discount, title="T", provider="P",
                     discount_type=DiscountType.percent, discount_value=Decimal("15"),
                     discounts=[{"label": "ЗСУ", "discount_type": "percent", "discount_value": 15},
                                {"label": None, "discount_type": "free", "discount_value": None}])
    assert oc.discounts[0].label == "ЗСУ"
    assert oc.discounts[1].discount_type == DiscountType.free


def test_discount_in_rejects_value_without_percent_fixed():
    with pytest.raises(ValidationError):
        DiscountIn(label="x", discount_type=DiscountType.free, discount_value=Decimal("5"))


def test_special_price_requires_value():
    # special_price carries the final price in discount_value — it is required
    ok = OfferCreate(type=OfferType.discount, title="T", provider="P",
                     discount_type=DiscountType.special_price, discount_value=Decimal("499"))
    assert ok.discount_type == DiscountType.special_price
    assert ok.discount_value == Decimal("499")
    with pytest.raises(ValidationError):
        OfferCreate(type=OfferType.discount, title="T", provider="P",
                    discount_type=DiscountType.special_price, discount_value=None)


def test_special_price_discount_row_requires_value():
    ok = DiscountIn(label="УБД", discount_type=DiscountType.special_price, discount_value=Decimal("499"))
    assert ok.discount_value == Decimal("499")
    with pytest.raises(ValidationError):
        DiscountIn(label="УБД", discount_type=DiscountType.special_price, discount_value=None)
