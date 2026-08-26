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


def to_pending(db: Session, term_id: int) -> QueryTerm:
    """Return a term to the candidate queue (e.g. un-reject a mistaken reject). Clears the
    review stamp so it reads as a fresh, un-reviewed candidate; the crawler stops excluding
    it once it is no longer rejected and re-surfaces it on the next mining run."""
    obj = get(db, term_id)
    obj.status = QueryTermStatus.pending
    obj.reviewed_by = None
    obj.reviewed_at = None
    db.commit()
    db.refresh(obj)
    return obj


def manual_add(db: Session, term: str, reviewed_by: int) -> QueryTerm:
    """Задача 5C: людський override — адмін вручну додає терм. Одразу approved +
    protected (людина хоче його в гріді назавжди, поза авто-петлею). Якщо терм уже
    існує — підіймаємо в approved і ставимо protected (людське рішення виграє)."""
    key = term.strip().lower()
    if not key:
        raise not_found("empty term")
    obj = db.query(QueryTerm).filter(QueryTerm.term == key).first()
    if obj is None:
        obj = QueryTerm(term=key, status=QueryTermStatus.approved, protected=True)
        db.add(obj)
    else:
        obj.status = QueryTermStatus.approved
        obj.protected = True
    obj.reviewed_by = reviewed_by
    obj.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(obj)
    return obj


def set_protected(db: Session, term_id: int, protected: bool) -> QueryTerm:
    """Перемкнути захист терма (людський override проти авто-ретайру)."""
    obj = get(db, term_id)
    obj.protected = protected
    db.commit()
    db.refresh(obj)
    return obj


def list_protected_terms(db: Session) -> list[str]:
    """Захищені терми — краулер тягне їх, щоб НІКОЛИ не авто-ретайрити (базовий TTL
    завжди). Дзеркало list_approved_terms/list_rejected_terms."""
    rows = (db.query(QueryTerm)
            .filter(QueryTerm.protected.is_(True)).all())
    return [r.term for r in rows]


def list_approved_terms(db: Session) -> list[str]:
    rows = (db.query(QueryTerm)
            .filter(QueryTerm.status == QueryTermStatus.approved).all())
    return [r.term for r in rows]


def list_rejected_terms(db: Session) -> list[str]:
    """Moderator-rejected terms — the crawler pulls these to hard-exclude them from
    mining (they never re-enter the audit queue until un-rejected). Mirror of
    list_approved_terms."""
    rows = (db.query(QueryTerm)
            .filter(QueryTerm.status == QueryTermStatus.rejected).all())
    return [r.term for r in rows]
