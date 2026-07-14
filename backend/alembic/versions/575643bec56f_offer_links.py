"""offer links

Revision ID: 575643bec56f
Revises: c04d4e4207e6
Create Date: 2026-07-14 16:45:43.840321

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '575643bec56f'
down_revision: Union[str, Sequence[str], None] = 'c04d4e4207e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('offers', 'contacts',
                    new_column_name='site_url',
                    existing_type=sa.String(length=512),
                    type_=sa.String(length=1024),
                    existing_nullable=True)
    op.add_column('offers', sa.Column('article_url', sa.String(length=1024), nullable=True))


def downgrade() -> None:
    op.drop_column('offers', 'article_url')
    op.alter_column('offers', 'site_url',
                    new_column_name='contacts',
                    existing_type=sa.String(length=1024),
                    type_=sa.String(length=512),
                    existing_nullable=True)
