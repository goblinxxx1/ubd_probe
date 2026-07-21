from sqlalchemy.orm import Session

from app.core.errors import not_found
from app.models import Source
from app.models.enums import CreatedBy, SourceType
from app.schemas.source import SourceCreate, SourceUpdate


def create_source(db: Session, data: SourceCreate, created_by: CreatedBy) -> Source:
    obj = Source(name=data.name, type=data.type, url_or_handle=data.url_or_handle,
                 is_active=data.is_active, created_by=created_by)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def list_sources(db: Session, is_active: bool | None = None):
    q = db.query(Source)
    if is_active is not None:
        q = q.filter(Source.is_active == is_active)
    return q.order_by(Source.created_at.desc()).all()


def get_source(db: Session, source_id: int) -> Source:
    obj = db.get(Source, source_id)
    if obj is None:
        raise not_found(f"Source {source_id} not found")
    return obj


def update_source(db: Session, source_id: int, data: SourceUpdate) -> Source:
    obj = get_source(db, source_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


def delete_source(db: Session, source_id: int) -> None:
    obj = get_source(db, source_id)
    db.delete(obj)
    db.commit()


def get_or_create_source_by_ref(db: Session, type_: SourceType, url_or_handle: str,
                                name: str, created_by: CreatedBy) -> Source:
    existing = db.query(Source).filter(Source.type == type_,
                                       Source.url_or_handle == url_or_handle).first()
    if existing is not None:
        if not existing.is_active:
            existing.is_active = True
            db.commit()
            db.refresh(existing)
        return existing
    obj = Source(name=name, type=type_, url_or_handle=url_or_handle,
                 is_active=True, created_by=created_by)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj
