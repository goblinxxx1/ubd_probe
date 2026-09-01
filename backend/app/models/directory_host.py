from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class DirectoryHost(Base):
    """Хости-каталоги (агрегатори), зареєстровані краулером.

    ОКРЕМА таблиця від blocked_hosts: каталоги мають лишатись fetchable для
    краулера (blocked_hosts — це no-fetch список), просто їхні офери
    в модерацію не йдуть/зачищаються ретро.
    """

    __tablename__ = "directory_hosts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    host: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
