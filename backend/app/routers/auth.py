from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.crud import admin_user as admin_crud
from app.core.security import create_access_token
from app.deps import get_db
from app.schemas.auth import LoginRequest, TokenResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    admin = admin_crud.authenticate(db, data.email, data.password)
    token = create_access_token(subject=admin.email, role=admin.role.value)
    return TokenResponse(access_token=token, role=admin.role.value)
