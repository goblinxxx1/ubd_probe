from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.crud import source as source_crud
from app.models import SourceCrawlState
from app.models.source_crawl_state import SourceCrawlState as _CS


def get_crawl_state(db: Session, source_id: int) -> SourceCrawlState | None:
    source_crud.get_source(db, source_id)  # raises 404 if missing
    return db.query(_CS).filter(_CS.source_id == source_id).first()


def upsert_crawl_state(db: Session, source_id: int, last_seen_key: str | None) -> SourceCrawlState:
    source = source_crud.get_source(db, source_id)  # raises 404 if missing
    now = datetime.now(timezone.utc)
    obj = db.query(_CS).filter(_CS.source_id == source_id).first()
    if obj is None:
        obj = _CS(source_id=source_id)
        db.add(obj)
    obj.last_seen_key = last_seen_key
    obj.last_crawled_at = now
    source.last_crawled_at = now  # mirror onto the source row
    db.commit()
    db.refresh(obj)
    return obj
