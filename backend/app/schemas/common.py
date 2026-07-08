from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorResponse(BaseModel):
    detail: str
    code: str


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int
