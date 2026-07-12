from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import BotAccountState


class BotAccountStateUpdate(BaseModel):
    state: BotAccountState
    cooldown_until: datetime | None = None
    note: str | None = None


class BotAccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    platform: str
    username: str
    state: BotAccountState
    cooldown_until: datetime | None
    last_used_at: datetime | None
    note: str | None
