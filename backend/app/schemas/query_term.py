from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import QueryTermStatus


class QueryTermCandidate(BaseModel):
    term: str
    z: float = 0.0
    support: int = 0


class QueryTermsSubmit(BaseModel):
    candidates: list[QueryTermCandidate]


class QueryTermManualAdd(BaseModel):
    """Ручне додавання терма адміном (людський override). За замовчуванням
    одразу approved + protected: людина хоче цей терм у гріді назавжди."""
    term: str


class QueryTermOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    term: str
    status: QueryTermStatus
    z: float
    support: int
    protected: bool = False
    created_at: datetime
    reviewed_at: datetime | None = None
