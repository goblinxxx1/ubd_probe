from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.errors import not_found
from app.models import BlockedHost
from app.models.enums import BlockedHostStatus
from app.schemas.blocked_host import HostCandidateCreate


def upsert_candidate(db: Session, data: HostCandidateCreate) -> BlockedHost:
    host = data.host.strip().lower().removeprefix("www.")
    obj = db.query(BlockedHost).filter(BlockedHost.host == host).first()
    if obj is not None:
        if obj.status == BlockedHostStatus.pending:   # refresh signals while pending
            obj.media_ratio = data.media_ratio
            obj.aggregator_ratio = data.aggregator_ratio
            obj.support = data.support
            obj.sample_urls = data.sample_urls
            db.commit()
            db.refresh(obj)
        return obj                                    # approved/rejected untouched
    obj = BlockedHost(host=host, media_ratio=data.media_ratio,
                      aggregator_ratio=data.aggregator_ratio, support=data.support,
                      sample_urls=data.sample_urls, status=BlockedHostStatus.pending)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get(db: Session, host_id: int) -> BlockedHost:
    obj = db.get(BlockedHost, host_id)
    if obj is None:
        raise not_found(f"BlockedHost {host_id} not found")
    return obj


def list_hosts(db: Session, status: BlockedHostStatus | None = None):
    q = db.query(BlockedHost)
    if status is not None:
        q = q.filter(BlockedHost.status == status)
    return q.order_by(BlockedHost.created_at.desc()).all()


def _review(db: Session, host_id: int, status: BlockedHostStatus, reviewed_by: int) -> BlockedHost:
    obj = get(db, host_id)
    obj.status = status
    obj.reviewed_by = reviewed_by
    obj.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(obj)
    return obj


def approve(db: Session, host_id: int, reviewed_by: int) -> BlockedHost:
    return _review(db, host_id, BlockedHostStatus.approved, reviewed_by)


def reject(db: Session, host_id: int, reviewed_by: int) -> BlockedHost:
    return _review(db, host_id, BlockedHostStatus.rejected, reviewed_by)


def list_approved_hosts(db: Session) -> list[str]:
    rows = (db.query(BlockedHost)
            .filter(BlockedHost.status == BlockedHostStatus.approved).all())
    return [r.host for r in rows]
