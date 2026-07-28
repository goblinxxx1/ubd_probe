"""offer_locations child table

Revision ID: a1b2c3d4e5f6
Revises: b2d4f6a80c11
Create Date: 2026-07-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "b2d4f6a80c11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _backfill(conn) -> None:
    conn.execute(sa.text(
        "INSERT INTO offer_locations (offer_id, name) "
        "SELECT id, location FROM offers "
        "WHERE location IS NOT NULL AND location <> ''"
    ))


def upgrade() -> None:
    op.create_table(
        "offer_locations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("offer_id", sa.Integer(),
                  sa.ForeignKey("offers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
    )
    op.create_index("ix_offer_locations_offer_id", "offer_locations", ["offer_id"])
    op.create_index("ix_offer_locations_name", "offer_locations", ["name"])
    _backfill(op.get_bind())
    op.drop_column("offers", "location")


def downgrade() -> None:
    op.add_column("offers", sa.Column("location", sa.String(length=255), nullable=True))
    op.get_bind().execute(sa.text(
        "UPDATE offers o JOIN offer_locations l ON l.offer_id = o.id SET o.location = l.name"
    ))
    op.drop_index("ix_offer_locations_name", table_name="offer_locations")
    op.drop_index("ix_offer_locations_offer_id", table_name="offer_locations")
    op.drop_table("offer_locations")
