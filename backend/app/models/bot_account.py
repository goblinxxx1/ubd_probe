from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.enums import BotAccountState


class BotAccount(Base):
    __tablename__ = "bot_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[BotAccountState] = mapped_column(
        Enum(BotAccountState), nullable=False, default=BotAccountState.active
    )
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (UniqueConstraint("platform", "username", name="uq_bot_platform_username"),)
