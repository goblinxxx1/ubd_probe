from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.models.enums import DiscountType, OfferStatus, OfferType, CreatedBy
from app.schemas.category import CategoryOut


class OfferBase(BaseModel):
    type: OfferType
    title: str
    description: str = ""
    provider: str
    location: str | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    discount_type: DiscountType | None = None
    discount_value: Decimal | None = None
    site_url: str | None = None
    article_url: str | None = None
    target_url: str | None = None
    image_url: str | None = None
    target_category_ids: list[int] = []
    offer_category_ids: list[int] = []

    @field_validator("site_url", "article_url", "target_url", mode="before")
    @classmethod
    def _optional_url(cls, v):
        if v is None or v == "":
            return None
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("must be an http:// or https:// URL")
        return v

    @model_validator(mode="after")
    def _check(self):
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until must be on or after valid_from")
        if self.discount_type in (DiscountType.percent, DiscountType.fixed):
            if self.discount_value is None:
                raise ValueError("discount_value required for percent/fixed discounts")
        else:
            if self.discount_value is not None:
                raise ValueError("discount_value must be empty unless discount_type is percent/fixed")
        return self


class OfferCreate(OfferBase):
    pass


class OfferUpdate(BaseModel):
    type: OfferType | None = None
    title: str | None = None
    description: str | None = None
    provider: str | None = None
    location: str | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    discount_type: DiscountType | None = None
    discount_value: Decimal | None = None
    site_url: str | None = None
    article_url: str | None = None
    target_url: str | None = None
    image_url: str | None = None
    target_category_ids: list[int] | None = None
    offer_category_ids: list[int] | None = None

    @field_validator("site_url", "article_url", "target_url", mode="before")
    @classmethod
    def _optional_url(cls, v):
        if v is None or v == "":
            return None
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("must be an http:// or https:// URL")
        return v


class OfferLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    provider: str
    site_url: str | None
    article_url: str | None


class OfferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    type: OfferType
    title: str
    description: str
    provider: str
    location: str | None
    valid_from: date | None
    valid_until: date | None
    discount_type: DiscountType | None
    discount_value: Decimal | None
    site_url: str | None
    article_url: str | None
    target_url: str | None
    image_url: str | None
    links: list[OfferLinkOut] = []
    source_id: int | None
    status: OfferStatus
    created_by: CreatedBy
    created_at: datetime
    updated_at: datetime
    target_categories: list[CategoryOut]
    offer_categories: list[CategoryOut]
