from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import CreatedBy, SourceType


class SourceCreate(BaseModel):
    name: str
    type: SourceType
    url_or_handle: str
    is_active: bool = True


class SourceUpdate(BaseModel):
    name: str | None = None
    type: SourceType | None = None
    url_or_handle: str | None = None
    is_active: bool | None = None


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    type: SourceType
    url_or_handle: str
    is_active: bool
    last_crawled_at: datetime | None
    created_by: CreatedBy
    created_at: datetime
