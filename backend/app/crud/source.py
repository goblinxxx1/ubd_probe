from sqlalchemy.orm import Session

from app.core.errors import not_found
from app.core.urlnorm import source_host
from app.models import Source
from app.models.enums import CreatedBy, SourceType
from app.schemas.source import SourceCreate, SourceUpdate


def create_source(db: Session, data: SourceCreate, created_by: CreatedBy) -> Source:
    if data.type == SourceType.website:
        host = source_host(data.url_or_handle)
        if host:
            for s in (db.query(Source)
                      .filter(Source.type == SourceType.website, Source.is_active.is_(True))
                      .all()):
                if source_host(s.url_or_handle) == host:
                    return s                              # dedup: one active website source per host
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
    from app.models import Offer, SourceCrawlState   # local import avoids cycle
    obj = get_source(db, source_id)
    db.query(SourceCrawlState).filter(SourceCrawlState.source_id == source_id)\
        .delete(synchronize_session=False)                # ephemeral crawl cursor — safe to drop
    db.query(Offer).filter(Offer.source_id == source_id)\
        .update({Offer.source_id: None}, synchronize_session=False)   # offers survive orphaned
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
