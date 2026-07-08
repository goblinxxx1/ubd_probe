from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.enums import AdminRole


class AdminUserCreate(BaseModel):
    email: EmailStr
    password: str
    role: AdminRole


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    role: AdminRole
    created_at: datetime
