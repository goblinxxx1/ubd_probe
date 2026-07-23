from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.enums import BlockedHostStatus


class BlockedHost(Base):
    __tablename__ = "blocked_hosts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    host: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    status: Mapped[BlockedHostStatus] = mapped_column(
        Enum(BlockedHostStatus), default=BlockedHostStatus.pending, nullable=False
    )
    media_ratio: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    aggregator_ratio: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    support: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sample_urls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
