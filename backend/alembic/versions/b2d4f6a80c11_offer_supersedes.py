"""offer supersedes_offer_id

Revision ID: b2d4f6a80c11
Revises: 9a1c7b3e2f10
Create Date: 2026-07-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b2d4f6a80c11'
down_revision: Union[str, Sequence[str], None] = '9a1c7b3e2f10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('offers', sa.Column('supersedes_offer_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_offers_supersedes', 'offers', 'offers',
                          ['supersedes_offer_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint('fk_offers_supersedes', 'offers', type_='foreignkey')
    op.drop_column('offers', 'supersedes_offer_id')
