from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

import jwt

from app.core.db import get_db
from app.core.errors import forbidden, unauthorized
from app.core.security import decode_access_token, verify_api_key
from app.models import AdminUser
from app.models.enums import AdminRole

__all__ = ["get_db", "get_current_admin", "require_super_admin", "require_api_key"]


def get_current_admin(request: Request, db: Session = Depends(get_db)) -> AdminUser:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise unauthorized()
    token = auth.removeprefix("Bearer ").strip()
    try:
        claims = decode_access_token(token)
    except jwt.PyJWTError:
        raise unauthorized("Invalid or expired token")
    admin = db.query(AdminUser).filter(AdminUser.email == claims.get("sub")).first()
    if admin is None:
        raise unauthorized("Unknown admin")
    return admin


def require_super_admin(admin: AdminUser = Depends(get_current_admin)) -> AdminUser:
    if admin.role != AdminRole.super_admin:
        raise forbidden("Requires super_admin role")
    return admin


def require_api_key(x_api_key: str = Header(default="")) -> None:
    if not verify_api_key(x_api_key):
        raise unauthorized("Invalid API key")
