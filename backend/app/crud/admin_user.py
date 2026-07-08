from sqlalchemy.orm import Session

from app.core.errors import conflict, not_found, unauthorized
from app.core.security import hash_password, verify_password
from app.models import AdminUser
from app.models.enums import AdminRole
from app.schemas.admin_user import AdminUserCreate


def get_by_email(db: Session, email: str) -> AdminUser | None:
    return db.query(AdminUser).filter(AdminUser.email == email).first()


def authenticate(db: Session, email: str, password: str) -> AdminUser:
    admin = get_by_email(db, email)
    if admin is None or not verify_password(password, admin.password_hash):
        raise unauthorized("Invalid credentials")
    return admin


def create_admin(db: Session, data: AdminUserCreate) -> AdminUser:
    if get_by_email(db, data.email):
        raise conflict(f"email '{data.email}' already exists")
    obj = AdminUser(email=data.email, password_hash=hash_password(data.password), role=data.role)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def list_admins(db: Session):
    return db.query(AdminUser).order_by(AdminUser.email).all()


def delete_admin(db: Session, admin_id: int) -> None:
    obj = db.get(AdminUser, admin_id)
    if obj is None:
        raise not_found(f"AdminUser {admin_id} not found")
    db.delete(obj)
    db.commit()
