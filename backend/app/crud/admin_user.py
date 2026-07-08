from sqlalchemy.orm import Session

from app.core.errors import unauthorized
from app.core.security import verify_password
from app.models import AdminUser


def get_by_email(db: Session, email: str) -> AdminUser | None:
    return db.query(AdminUser).filter(AdminUser.email == email).first()


def authenticate(db: Session, email: str, password: str) -> AdminUser:
    admin = get_by_email(db, email)
    if admin is None or not verify_password(password, admin.password_hash):
        raise unauthorized("Invalid credentials")
    return admin
