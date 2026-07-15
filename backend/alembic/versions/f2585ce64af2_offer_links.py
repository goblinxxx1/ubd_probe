"""offer links

Revision ID: f2585ce64af2
Revises: 575643bec56f
Create Date: 2026-07-15 17:29:36.481461

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2585ce64af2'
down_revision: Union[str, Sequence[str], None] = '575643bec56f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('offers', sa.Column('target_url', sa.String(length=1024), nullable=True))
    op.create_index('ix_offers_target_url', 'offers', ['target_url'], mysql_length=255)
    op.create_table('offer_links',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('offer_id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=512), nullable=False),
        sa.Column('site_url', sa.String(length=1024), nullable=True),
        sa.Column('article_url', sa.String(length=1024), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['offer_id'], ['offers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_offer_links_offer_id', 'offer_links', ['offer_id'])


def downgrade() -> None:
    op.drop_index('ix_offer_links_offer_id', 'offer_links')
    op.drop_table('offer_links')
    op.drop_index('ix_offers_target_url', 'offers')
    op.drop_column('offers', 'target_url')
