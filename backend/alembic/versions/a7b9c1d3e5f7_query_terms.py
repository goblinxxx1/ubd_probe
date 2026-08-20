"""query terms audit table

Revision ID: a7b9c1d3e5f7
Revises: d4e8f1a2b3c5
Create Date: 2026-08-20 04:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7b9c1d3e5f7"
down_revision: Union[str, Sequence[str], None] = "d4e8f1a2b3c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "query_terms",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("term", sa.String(length=255), nullable=False),
        sa.Column("status", sa.Enum("pending", "approved", "rejected", name="querytermstatus"),
                  nullable=False, server_default="pending"),
        sa.Column("z", sa.Float(), nullable=False, server_default="0"),
        sa.Column("support", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("term", name="uq_query_terms_term"),
    )


def downgrade() -> None:
    op.drop_table("query_terms")
