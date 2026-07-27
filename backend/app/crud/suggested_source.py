from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.errors import conflict, not_found
from app.core.urlnorm import normalize_ref
from app.crud import source as source_crud
from app.models import Source, SuggestedSource
from app.models.enums import CreatedBy, SuggestionStatus
from app.schemas.source import SourceCreate
from app.schemas.suggested_source import SuggestedSourceCreate


def create_suggestion(db: Session, data: SuggestedSourceCreate) -> SuggestedSource | None:
    ref = normalize_ref(data.type, data.url_or_handle)
    active = db.query(Source).filter(Source.type == data.type, Source.is_active.is_(True)).all()
    if any(normalize_ref(s.type.value if hasattr(s.type, "value") else s.type,
                         s.url_or_handle) == ref for s in active):
        return None
    existing = (db.query(SuggestedSource)
                .filter(SuggestedSource.type == data.type,
                        SuggestedSource.url_or_handle == data.url_or_handle)
                .first())
    if existing is not None:
        return existing
    obj = SuggestedSource(
        name=data.name, type=data.type, url_or_handle=data.url_or_handle,
        discovered_from_source_id=data.discovered_from_source_id,
        discovery_note=data.discovery_note, status=SuggestionStatus.pending,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def list_suggestions(db: Session, status: SuggestionStatus | None = None):
    q = db.query(SuggestedSource)
    if status is not None:
        q = q.filter(SuggestedSource.status == status)
    return q.order_by(SuggestedSource.created_at.desc()).all()


def get_suggestion(db: Session, suggestion_id: int) -> SuggestedSource:
    obj = db.get(SuggestedSource, suggestion_id)
    if obj is None:
        raise not_found(f"SuggestedSource {suggestion_id} not found")
    return obj


def approve(db: Session, suggestion_id: int, reviewed_by: int) -> Source:
    obj = get_suggestion(db, suggestion_id)
    if obj.status != SuggestionStatus.pending:
        raise conflict("Suggestion already reviewed")
    source = source_crud.create_source(
        db, SourceCreate(name=obj.name, type=obj.type, url_or_handle=obj.url_or_handle),
        created_by=CreatedBy.crawler_suggestion,
    )
    obj.status = SuggestionStatus.approved
    obj.reviewed_by = reviewed_by
    obj.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    return source


def reject(db: Session, suggestion_id: int, reviewed_by: int) -> SuggestedSource:
    obj = get_suggestion(db, suggestion_id)
    if obj.status != SuggestionStatus.pending:
        raise conflict("Suggestion already reviewed")
    obj.status = SuggestionStatus.rejected
    obj.reviewed_by = reviewed_by
    obj.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(obj)
    return obj
