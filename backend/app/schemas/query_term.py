from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import QueryTermStatus


class QueryTermCandidate(BaseModel):
    term: str
    z: float = 0.0
    support: int = 0


class QueryTermsSubmit(BaseModel):
    candidates: list[QueryTermCandidate]


class QueryTermOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    term: str
    status: QueryTermStatus
    z: float
    support: int
    created_at: datetime
    reviewed_at: datetime | None = None
