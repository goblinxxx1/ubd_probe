from datetime import datetime, timezone
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.core.errors import not_found, validation_error
from app.models import BlockedHost
from app.models.enums import BlockedHostStatus


def bare_host(value: str) -> str:
    """Bare registrable host from a host or full URL: no scheme/path/port/www., lowercased."""
    raw = (value or "").strip()
    if not raw:
        return ""
    host = urlsplit(raw if "//" in raw else "//" + raw).hostname or ""
    return host.lower().removeprefix("www.")


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


def reject(db: Session, host_id: int, reviewed_by: int) -> BlockedHost:
    """Unblock: approved → rejected drops the host from `list_approved_hosts` (the
    crawler's no-fetch list). Reusable from any status; the row is kept for history."""
    return _review(db, host_id, BlockedHostStatus.rejected, reviewed_by)


def add_manual(db: Session, host: str, reviewed_by: int) -> BlockedHost:
    """Human directly blocks a host via admin: upsert to `approved` (the crawler's
    LEARNED list). No miner evidence, so ratios/support stay 0."""
    h = bare_host(host)
    if not h:
        raise validation_error("host is required")
    now = datetime.now(timezone.utc)
    obj = db.query(BlockedHost).filter(BlockedHost.host == h).first()
    if obj is None:
        obj = BlockedHost(host=h, status=BlockedHostStatus.approved,
                          reviewed_by=reviewed_by, reviewed_at=now)
        db.add(obj)
    else:
        obj.status = BlockedHostStatus.approved
        obj.reviewed_by = reviewed_by
        obj.reviewed_at = now
    db.commit()
    db.refresh(obj)
    return obj


def auto_block(db: Session, host: str, sample_url: str | None = None) -> BlockedHost:
    """System (non-human) block: upsert host to approved with reviewed_by=None.
    Idempotent — an existing row is promoted to approved. `sample_url`, if given,
    is stored as evidence on first creation (existing rows keep their samples)."""
    h = bare_host(host)
    if not h:
        raise validation_error("host is required")
    obj = db.query(BlockedHost).filter(BlockedHost.host == h).first()
    if obj is None:
        obj = BlockedHost(host=h, status=BlockedHostStatus.approved, reviewed_by=None,
                          reviewed_at=datetime.now(timezone.utc),
                          sample_urls=[sample_url] if sample_url else None)
        db.add(obj)
    else:
        obj.status = BlockedHostStatus.approved
    db.commit()
    db.refresh(obj)
    return obj


def list_approved_hosts(db: Session) -> list[str]:
    rows = (db.query(BlockedHost)
            .filter(BlockedHost.status == BlockedHostStatus.approved).all())
    return [r.host for r in rows]
