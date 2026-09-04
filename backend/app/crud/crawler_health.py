from sqlalchemy.orm import Session

from app.models.crawler_health import CrawlerHealth

_SINGLETON_ID = 1


def upsert_snapshot(db: Session, snapshot: dict) -> CrawlerHealth:
    """Store the latest crawler health snapshot (singleton row id=1). Replaces any prior
    snapshot — v1 keeps no history."""
    obj = db.get(CrawlerHealth, _SINGLETON_ID)
    if obj is None:
        obj = CrawlerHealth(id=_SINGLETON_ID, snapshot=snapshot)
        db.add(obj)
    else:
        obj.snapshot = snapshot
    db.commit()
    db.refresh(obj)
    return obj


def get_latest(db: Session) -> CrawlerHealth | None:
    return db.get(CrawlerHealth, _SINGLETON_ID)
