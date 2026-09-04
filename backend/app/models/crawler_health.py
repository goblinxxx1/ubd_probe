from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class CrawlerHealth(Base):
    """Latest crawler self-reported health snapshot (singleton, id=1). The crawler owns the
    snapshot shape; the backend stores it opaquely and the admin panel renders it. Upserted
    on each report tick — only the most recent snapshot is kept (no history in v1)."""

    __tablename__ = "crawler_health"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    reported_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
