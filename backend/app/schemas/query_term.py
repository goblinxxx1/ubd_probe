from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

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


class QueryTermBulkAction(str, Enum):
    """Масові дії — дзеркало рядкових. `unreject` (кнопка rejected-вкладки)
    мапиться на `to_pending`, тож окремою дією не потрібен."""
    approve = "approve"
    reject = "reject"
    to_pending = "to_pending"
    protect = "protect"
    unprotect = "unprotect"


class QueryTermBulkIn(BaseModel):
    ids: list[int] = Field(min_length=1)
    action: QueryTermBulkAction


class QueryTermBulkFail(BaseModel):
    id: int
    error: str


class QueryTermBulkOut(BaseModel):
    done: list[int] = []
    failed: list[QueryTermBulkFail] = []
