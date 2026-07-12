from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CrawlStateUpdate(BaseModel):
    last_seen_key: str | None = None


class CrawlStateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    last_seen_key: str | None
    last_crawled_at: datetime | None
