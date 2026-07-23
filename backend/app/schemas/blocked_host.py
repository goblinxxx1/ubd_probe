from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import BlockedHostStatus


class HostCandidateCreate(BaseModel):
    host: str
    media_ratio: float = 0.0
    aggregator_ratio: float = 0.0
    support: int = 0
    sample_urls: list[str] | None = None


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
