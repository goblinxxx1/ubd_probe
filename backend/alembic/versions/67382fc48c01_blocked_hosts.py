"""blocked_hosts

Revision ID: 67382fc48c01
Revises: 7f3c1a2b9d10
Create Date: 2026-07-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '67382fc48c01'
down_revision: Union[str, Sequence[str], None] = '7f3c1a2b9d10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'blocked_hosts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('host', sa.String(length=255), nullable=False),
        sa.Column(
            'status',
            sa.Enum('pending', 'approved', 'rejected', name='blockedhoststatus'),
            nullable=False,
        ),
        sa.Column('media_ratio', sa.Float(), nullable=False),
        sa.Column('aggregator_ratio', sa.Float(), nullable=False),
        sa.Column('support', sa.Integer(), nullable=False),
        sa.Column('sample_urls', sa.JSON(), nullable=True),
        sa.Column('reviewed_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('host', name='uq_blocked_hosts_host'),
    )


def downgrade() -> None:
    op.drop_table('blocked_hosts')
