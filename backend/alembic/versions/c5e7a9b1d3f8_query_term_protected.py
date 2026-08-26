"""query_terms.protected flag (human override — exempt from auto-retire)

Revision ID: c5e7a9b1d3f8
Revises: a7b9c1d3e5f7
Create Date: 2026-08-26 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c5e7a9b1d3f8"
down_revision: Union[str, Sequence[str], None] = "a7b9c1d3e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "query_terms",
        sa.Column("protected", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("query_terms", "protected")
