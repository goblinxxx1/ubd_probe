from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.associationproxy import association_proxy

from app.core.db import Base
from app.models.categories import (
    OfferCategory, TargetCategory, offer_offer_categories, offer_target_categories,
)
from app.models.enums import CreatedBy, DiscountType, OfferStatus, OfferType

if TYPE_CHECKING:
    from app.models.offer_discount import OfferDiscount
    from app.models.offer_link import OfferLink
    from app.models.offer_location import OfferLocation


def _mk_location(name: str):
    from app.models.offer_location import OfferLocation
    return OfferLocation(name=name)


class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[OfferType] = mapped_column(Enum(OfferType), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    provider: Mapped[str] = mapped_column(String(512), nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    discount_type: Mapped[DiscountType | None] = mapped_column(Enum(DiscountType), nullable=True)
    discount_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    site_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    article_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    target_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    target_url_canonical: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    article_url_canonical: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[OfferStatus] = mapped_column(Enum(OfferStatus), nullable=False)
    created_by: Mapped[CreatedBy] = mapped_column(Enum(CreatedBy), nullable=False)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True)
    supersedes_offer_id: Mapped[int | None] = mapped_column(
        ForeignKey("offers.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    target_categories: Mapped[list[TargetCategory]] = relationship(
        secondary=offer_target_categories, lazy="selectin"
    )
    offer_categories: Mapped[list[OfferCategory]] = relationship(
        secondary=offer_offer_categories, lazy="selectin"
    )
    links: Mapped[list["OfferLink"]] = relationship(
        back_populates="offer", cascade="all, delete-orphan", lazy="selectin"
    )
    locations: Mapped[list["OfferLocation"]] = relationship(
        back_populates="offer", cascade="all, delete-orphan", lazy="selectin"
    )
    discounts: Mapped[list["OfferDiscount"]] = relationship(
        back_populates="offer", cascade="all, delete-orphan",
        order_by="OfferDiscount.sort_order", lazy="selectin",
    )
    location_names = association_proxy("locations", "name", creator=_mk_location)
    supersedes: Mapped["Offer | None"] = relationship(
        "Offer", remote_side="Offer.id", foreign_keys="Offer.supersedes_offer_id",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("source_id", "content_hash", name="uq_offer_source_content_hash"),
        Index("ix_offers_target_url", "target_url", mysql_length=255),
        Index("ix_offers_target_url_canonical", "target_url_canonical", mysql_length=255),
        Index("ix_offers_article_url_canonical", "article_url_canonical", mysql_length=255),
    )
