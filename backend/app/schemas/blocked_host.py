from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import BlockedHostStatus


class BlockedHostCreate(BaseModel):
    host: str


class AutoBlockCreate(BaseModel):
    host: str
    sample_url: str | None = None


class BlockedHostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    host: str
    status: BlockedHostStatus
    media_ratio: float
    aggregator_ratio: float
    support: int
    sample_urls: list[str] | None
    reviewed_at: datetime | None
    created_at: datetime
