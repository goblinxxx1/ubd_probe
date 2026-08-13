"""add offers.logo_url (brand logo, distinct from image_url hero)

Revision ID: d4e8f1a2b3c5
Revises: b3e7d1c9f4a2
Create Date: 2026-08-13

Nullable, no backfill. Brand logo URL (JSON-LD Organization.logo, SVG-friendly),
kept separate from the card hero image_url.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e8f1a2b3c5"
down_revision: Union[str, Sequence[str], None] = "b3e7d1c9f4a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("offers", sa.Column("logo_url", sa.String(length=1024), nullable=True))


def downgrade() -> None:
    op.drop_column("offers", "logo_url")
