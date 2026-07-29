from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.enums import DiscountType

if TYPE_CHECKING:
    from app.models.offer import Offer


class OfferDiscount(Base):
    __tablename__ = "offer_discounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    offer_id: Mapped[int] = mapped_column(
        ForeignKey("offers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    discount_type: Mapped[DiscountType | None] = mapped_column(Enum(DiscountType), nullable=True)
    discount_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    offer: Mapped["Offer"] = relationship(back_populates="discounts")
