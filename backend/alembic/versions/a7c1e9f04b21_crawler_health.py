"""crawler health snapshot (singleton)

Stores the crawler's latest self-reported health snapshot for the admin
monitoring panel. One row (id=1), upserted on each report tick; no history.

Revision ID: a7c1e9f04b21
Revises: 6da7b45bd2ea
Create Date: 2026-09-04

"""
from alembic import op
import sqlalchemy as sa

revision = "a7c1e9f04b21"
down_revision = "6da7b45bd2ea"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crawler_health",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("reported_at", sa.DateTime(), server_default=sa.text("now()"),
                  nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("crawler_health")
