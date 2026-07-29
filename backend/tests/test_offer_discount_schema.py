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
