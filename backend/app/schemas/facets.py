from pydantic import BaseModel

from app.models.enums import OfferType


class CategoryFacet(BaseModel):
    id: int
    name: str
    count: int


class TypeFacet(BaseModel):
    value: OfferType
    count: int


class LocationFacet(BaseModel):
    name: str
    count: int


class FacetsOut(BaseModel):
    target_categories: list[CategoryFacet]
    offer_categories: list[CategoryFacet]
    types: list[TypeFacet]
    locations: list[LocationFacet]
