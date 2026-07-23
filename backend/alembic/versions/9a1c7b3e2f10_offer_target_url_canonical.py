"""offer target_url_canonical

Revision ID: 9a1c7b3e2f10
Revises: 67382fc48c01
Create Date: 2026-07-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '9a1c7b3e2f10'
down_revision: Union[str, Sequence[str], None] = '67382fc48c01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _backfill(conn) -> None:
    from app.core.urlnorm import canonicalize_target_url
    rows = conn.execute(
        sa.text("SELECT id, target_url FROM offers WHERE target_url IS NOT NULL")
    ).fetchall()
    for rid, turl in rows:
        canon = canonicalize_target_url(turl)
        if canon:
            conn.execute(
                sa.text("UPDATE offers SET target_url_canonical = :c WHERE id = :i"),
                {"c": canon, "i": rid},
            )


def upgrade() -> None:
    op.add_column('offers', sa.Column('target_url_canonical', sa.String(length=1024), nullable=True))
    op.create_index('ix_offers_target_url_canonical', 'offers',
                    ['target_url_canonical'], mysql_length=255)
    _backfill(op.get_bind())


def downgrade() -> None:
    op.drop_index('ix_offers_target_url_canonical', table_name='offers')
    op.drop_column('offers', 'target_url_canonical')
