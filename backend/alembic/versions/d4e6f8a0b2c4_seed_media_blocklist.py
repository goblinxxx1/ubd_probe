"""seed media/social host blocklist

Revision ID: d4e6f8a0b2c4
Revises: c3d5e7f9a1b2
Create Date: 2026-08-05

"""
from alembic import op
from sqlalchemy import text

revision = "d4e6f8a0b2c4"
down_revision = "c3d5e7f9a1b2"
branch_labels = None
depends_on = None

SEED_HOSTS = [
    "fraza.ua", "znaj.ua", "epravda.com.ua", "focus.ua", "kosht.media", "24tv.ua",
    "unn.ua", "parlament.ua", "rubryka.com", "ogo.ua", "izum.ua", "nefterynok.info",
    "uc.kr.ua", "pravdahub.com.ua", "ukrainianwall.com", "dtkt.ua",
    "api.whatsapp.com", "news.google.com", "google.com", "linkedin.com",
    "linktr.ee", "addtoany.com",
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
