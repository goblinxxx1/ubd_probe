"""seed news/social host blocklist (round 2)

Adds Ukrainian news portals + social/link-hub hosts that the crawler was
scraping into offers after a DB rebuild wiped the self-grown blocklist.
These are structurally never a UBD-discount source, so we seed them as
approved blocks (the self-growing miner would eventually re-learn them, but
seeding closes the precision gap immediately and survives future rebuilds).

Revision ID: f1a2b3c4d5e6
Revises: d4e6f8a0b2c4
Create Date: 2026-08-09

"""
from alembic import op
from sqlalchemy import text

revision = "f1a2b3c4d5e6"
down_revision = "d4e6f8a0b2c4"
branch_labels = None
depends_on = None

SEED_HOSTS = [
    # Ukrainian news / media portals
    "lmn.in.ua", "denzadnem.com.ua", "tvoemisto.tv", "novyny.live",
    # social / link-hub aggregators (same class as linktr.ee / addtoany already seeded)
    "tiktok.com", "bio.site",
]


def _seed(conn):
    for h in SEED_HOSTS:
        conn.execute(text(
            "INSERT INTO blocked_hosts (host, status, media_ratio, aggregator_ratio, support, "
            "created_at) VALUES (:h, 'approved', 0, 0, 0, NOW()) "
            "ON DUPLICATE KEY UPDATE status='approved'"), {"h": h})


def upgrade():
    _seed(op.get_bind())


def downgrade():
    conn = op.get_bind()
    for h in SEED_HOSTS:
        conn.execute(text("DELETE FROM blocked_hosts WHERE host = :h AND reviewed_by IS NULL"),
                     {"h": h})
