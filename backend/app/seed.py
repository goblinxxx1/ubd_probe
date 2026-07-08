from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models import AdminUser, OfferCategory, TargetCategory
from app.models.enums import AdminRole

TARGET_CATEGORIES = [
    ("УБД", "ubd"), ("Ветеран", "veteran"),
    ("Особа з інвалідністю внаслідок війни", "war-disability"),
    ("Сім'я загиблого", "fallen-family"), ("Внутрішньо переміщена особа", "idp"),
]
OFFER_CATEGORIES = [
    ("Розваги", "rozvahy"), ("Музеї", "museums"), ("Кафе/ресторани", "food"),
    ("Спорт", "sport"), ("Освіта", "education"), ("Транспорт", "transport"),
    ("Медицина", "medicine"),
]


def seed(db: Session) -> None:
    if not db.query(AdminUser).filter(AdminUser.email == settings.seed_admin_email).first():
        db.add(AdminUser(email=settings.seed_admin_email,
                         password_hash=hash_password(settings.seed_admin_password),
                         role=AdminRole.super_admin))
    for name, slug in TARGET_CATEGORIES:
        if not db.query(TargetCategory).filter(TargetCategory.slug == slug).first():
            db.add(TargetCategory(name=name, slug=slug))
    for name, slug in OFFER_CATEGORIES:
        if not db.query(OfferCategory).filter(OfferCategory.slug == slug).first():
            db.add(OfferCategory(name=name, slug=slug))
    db.commit()


def main() -> None:
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
