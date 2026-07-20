"""offer last_seen_at

Revision ID: 7f3c1a2b9d10
Revises: f2585ce64af2
Create Date: 2026-07-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '7f3c1a2b9d10'
down_revision: Union[str, Sequence[str], None] = 'f2585ce64af2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('offers', sa.Column('last_seen_at', sa.DateTime(), nullable=True))
    op.execute("UPDATE offers SET last_seen_at = created_at WHERE last_seen_at IS NULL")


def downgrade() -> None:
    op.drop_column('offers', 'last_seen_at')
