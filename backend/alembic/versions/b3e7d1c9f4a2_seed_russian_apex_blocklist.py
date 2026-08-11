"""seed russian apex blocklist

Revision ID: b3e7d1c9f4a2
Revises: a7c1e9d3b5f2
Create Date: 2026-08-11

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = 'b3e7d1c9f4a2'
down_revision: Union[str, Sequence[str], None] = 'a7c1e9d3b5f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Known Russian sites on gTLDs — apex domains the subdomain heuristic can't catch.
SEED_HOSTS = [
    "boombate.com",
]


def _seed(conn):
    for h in SEED_HOSTS:
        conn.execute(text(
            "INSERT INTO blocked_hosts (host, status, media_ratio, aggregator_ratio, support, "
            "created_at) VALUES (:h, 'approved', 0, 0, 0, NOW()) "
            "ON DUPLICATE KEY UPDATE status='approved'"), {"h": h})


def upgrade() -> None:
    _seed(op.get_bind())


def downgrade() -> None:
    conn = op.get_bind()
    for h in SEED_HOSTS:
        conn.execute(text("DELETE FROM blocked_hosts WHERE host = :h AND reviewed_by IS NULL"),
                     {"h": h})
