from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models.source import Source
from app.models.enums import CreatedBy, SourceType

FIXTURE_URL = "http://fixture/"


def demo_seed(db: Session) -> Source:
    existing = db.query(Source).filter(Source.url_or_handle == FIXTURE_URL).first()
    if existing:
        return existing
    src = Source(
        name="Demo Fixture",
        type=SourceType.website,
        url_or_handle=FIXTURE_URL,
        is_active=True,
        created_by=CreatedBy.admin,
    )
    db.add(src)
    db.commit()
    db.refresh(src)
    return src


def main() -> None:
    db = SessionLocal()
    try:
        demo_seed(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
