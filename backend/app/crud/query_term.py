from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.errors import not_found
from app.models.enums import QueryTermStatus
from app.models.query_term import QueryTerm
from app.schemas.query_term import QueryTermCandidate


def upsert_candidates(db: Session, items: list[QueryTermCandidate]) -> int:
    """Bulk upsert mined candidates. A pending row refreshes its z/support; a new term is
    inserted pending; approved/rejected rows are left untouched. Mirrors
    blocked_host.upsert_candidate."""
    n = 0
    for it in items:
        term = it.term.strip().lower()
        if not term:
            continue
        obj = db.query(QueryTerm).filter(QueryTerm.term == term).first()
        if obj is not None:
            if obj.status == QueryTermStatus.pending:
                obj.z = it.z
                obj.support = it.support
            continue
        db.add(QueryTerm(term=term, z=it.z, support=it.support,
                         status=QueryTermStatus.pending))
        n += 1
    db.commit()
    return n


def get(db: Session, term_id: int) -> QueryTerm:
    obj = db.get(QueryTerm, term_id)
    if obj is None:
        raise not_found(f"QueryTerm {term_id} not found")
    return obj


def list_terms(db: Session, status: QueryTermStatus | None = None):
    q = db.query(QueryTerm)
    if status is not None:
        q = q.filter(QueryTerm.status == status)
    return q.order_by(QueryTerm.created_at.desc()).all()


def _review(db: Session, term_id: int, status: QueryTermStatus, reviewed_by: int) -> QueryTerm:
    obj = get(db, term_id)
    obj.status = status
    obj.reviewed_by = reviewed_by
    obj.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(obj)
    return obj


def approve(db: Session, term_id: int, reviewed_by: int) -> QueryTerm:
    return _review(db, term_id, QueryTermStatus.approved, reviewed_by)


def reject(db: Session, term_id: int, reviewed_by: int) -> QueryTerm:
    return _review(db, term_id, QueryTermStatus.rejected, reviewed_by)


def list_approved_terms(db: Session) -> list[str]:
    rows = (db.query(QueryTerm)
            .filter(QueryTerm.status == QueryTermStatus.approved).all())
    return [r.term for r in rows]
