from sqlalchemy import Column, ForeignKey, Integer, String, Table

from app.core.db import Base

offer_target_categories = Table(
    "offer_target_categories",
    Base.metadata,
    Column("offer_id", ForeignKey("offers.id", ondelete="CASCADE"), primary_key=True),
    Column("target_category_id", ForeignKey("target_categories.id", ondelete="CASCADE"), primary_key=True),
)

offer_offer_categories = Table(
    "offer_offer_categories",
    Base.metadata,
    Column("offer_id", ForeignKey("offers.id", ondelete="CASCADE"), primary_key=True),
    Column("offer_category_id", ForeignKey("offer_categories.id", ondelete="CASCADE"), primary_key=True),
)


class TargetCategory(Base):
    __tablename__ = "target_categories"

    id: int = Column(Integer, primary_key=True)
    name: str = Column(String(255), nullable=False)
    slug: str = Column(String(255), unique=True, nullable=False)


class OfferCategory(Base):
    __tablename__ = "offer_categories"

    id: int = Column(Integer, primary_key=True)
    name: str = Column(String(255), nullable=False)
    slug: str = Column(String(255), unique=True, nullable=False)
