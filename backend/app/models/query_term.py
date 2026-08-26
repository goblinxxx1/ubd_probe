from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.enums import QueryTermStatus


class QueryTerm(Base):
    """Miner-surfaced service/category term awaiting moderator audit. Approved terms feed
    the crawler's query grid. Mirrors BlockedHost (host-candidate audit)."""

    __tablename__ = "query_terms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    term: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    status: Mapped[QueryTermStatus] = mapped_column(
        Enum(QueryTermStatus), default=QueryTermStatus.pending, nullable=False
    )
    z: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    support: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Задача 5C: людський override. Захищений терм ніколи не авто-ретайриться
    # краулером (базовий TTL) і виживає незалежно від сухих статистик.
    protected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reviewed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
