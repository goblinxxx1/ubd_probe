"""offer/source dedup: pagination canonical + one website source per host + reject dups

Revision ID: c3d5e7f9a1b2
Revises: e5f6a7b8c9d0
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d5e7f9a1b2"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _backfill_canonical(conn) -> None:
    from app.core.urlnorm import canonicalize_target_url
    rows = conn.execute(sa.text(
        "SELECT id, target_url, article_url FROM offers "
        "WHERE target_url IS NOT NULL OR article_url IS NOT NULL")).fetchall()
    for rid, turl, aurl in rows:
        conn.execute(sa.text(
            "UPDATE offers SET target_url_canonical=:t, article_url_canonical=:a WHERE id=:i"),
            {"t": canonicalize_target_url(turl) if turl else None,
             "a": canonicalize_target_url(aurl) if aurl else None, "i": rid})


def _dedup_sources(conn) -> None:
    from app.core.urlnorm import source_host
    rows = conn.execute(sa.text(
        "SELECT id, url_or_handle FROM sources WHERE type='website' AND is_active=1")).fetchall()
    by_host: dict[str, list[int]] = {}
    for sid, url in rows:
        h = source_host(url)
        if h:
            by_host.setdefault(h, []).append(sid)
    for h, ids in by_host.items():
        if len(ids) < 2:
            continue
        counts = {sid: conn.execute(sa.text(
            "SELECT COUNT(*) FROM offers WHERE source_id=:s"), {"s": sid}).scalar() for sid in ids}
        keep = max(ids, key=lambda s: (counts[s], -s))     # most offers; tie -> lowest id
        for sid in ids:
            if sid != keep:
                conn.execute(sa.text("UPDATE sources SET is_active=0 WHERE id=:s"), {"s": sid})


def _reject_published_pending_dups(conn) -> None:
    conn.execute(sa.text(
        "UPDATE offers p JOIN ("
        "  SELECT DISTINCT article_url_canonical AS a FROM offers "
        "  WHERE status='published' AND article_url_canonical IS NOT NULL"
        ") pub ON p.article_url_canonical = pub.a "
        "SET p.status='rejected' WHERE p.status='pending_review'"))


def upgrade() -> None:
    conn = op.get_bind()
    _backfill_canonical(conn)
    _dedup_sources(conn)
    _reject_published_pending_dups(conn)


def downgrade() -> None:
    pass   # data cleanup — not reversible (matches prior backfill migrations)
