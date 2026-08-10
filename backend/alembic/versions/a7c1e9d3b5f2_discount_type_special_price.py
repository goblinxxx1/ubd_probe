"""add 'special_price' to discount_type enum (offers + offer_discounts)

Revision ID: a7c1e9d3b5f2
Revises: f1a2b3c4d5e6
Create Date: 2026-08-10

special_price carries the final price for УБД in discount_value (not a discount off).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "a7c1e9d3b5f2"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW = "ENUM('percent','fixed','free','special_price')"
_OLD = "ENUM('percent','fixed','free')"


def _modify(enum_sql: str) -> None:
    for table in ("offers", "offer_discounts"):
        op.execute(f"ALTER TABLE {table} MODIFY COLUMN discount_type {enum_sql} NULL")


def upgrade() -> None:
    _modify(_NEW)


def downgrade() -> None:
    # assumes no rows use 'special_price' (a value-narrowing down-migration)
    _modify(_OLD)
