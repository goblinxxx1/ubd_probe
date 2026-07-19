from sqlalchemy.orm import Session

from app.core.errors import conflict, not_found
from app.schemas.category import CategoryCreate, CategoryUpdate


def list_categories(db: Session, model):
    return db.query(model).order_by(model.name).all()


def get_category(db: Session, model, category_id: int):
    obj = db.get(model, category_id)
    if obj is None:
        raise not_found(f"{model.__name__} {category_id} not found")
    return obj


def create_category(db: Session, model, data: CategoryCreate):
    if db.query(model).filter(model.slug == data.slug).first():
        raise conflict(f"slug '{data.slug}' already exists")
    obj = model(name=data.name, slug=data.slug)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_or_create_category(db: Session, model, name: str, slug: str):
    obj = db.query(model).filter(model.slug == slug).first()
    if obj is None:
        obj = model(name=name, slug=slug)
        db.add(obj)
        db.commit()
        db.refresh(obj)
    return obj


def update_category(db: Session, model, category_id: int, data: CategoryUpdate):
    obj = get_category(db, model, category_id)
    if data.slug and data.slug != obj.slug and db.query(model).filter(model.slug == data.slug).first():
        raise conflict(f"slug '{data.slug}' already exists")
    if data.name is not None:
        obj.name = data.name
    if data.slug is not None:
        obj.slug = data.slug
    db.commit()
    db.refresh(obj)
    return obj


def delete_category(db: Session, model, category_id: int):
    obj = get_category(db, model, category_id)
    db.delete(obj)
    db.commit()
