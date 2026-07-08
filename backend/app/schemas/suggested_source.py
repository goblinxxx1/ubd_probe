from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import SourceType, SuggestionStatus


class SuggestedSourceCreate(BaseModel):
    name: str
    type: SourceType
    url_or_handle: str
    discovered_from_source_id: int | None = None
    discovery_note: str | None = None


class SuggestedSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    type: SourceType
    url_or_handle: str
    discovered_from_source_id: int | None
    discovery_note: str | None
    status: SuggestionStatus
    reviewed_at: datetime | None
    created_at: datetime
