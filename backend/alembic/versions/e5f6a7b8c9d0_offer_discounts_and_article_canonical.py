"""offer_discounts table + offers.article_url_canonical

Revision ID: e5f6a7b8c9d0
Revises: a1b2c3d4e5f6
Create Date: 2026-07-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DISCOUNT_ENUM = sa.Enum("percent", "fixed", "free", name="discounttype")


def _backfill(conn) -> None:
    from app.core.urlnorm import canonicalize_target_url
    rows = conn.execute(
        sa.text("SELECT id, article_url, discount_type, discount_value "
                "FROM offers")
    ).fetchall()
    for rid, aurl, dtype, dval in rows:
        if aurl:
            canon = canonicalize_target_url(aurl)
            if canon:
                conn.execute(
                    sa.text("UPDATE offers SET article_url_canonical = :c WHERE id = :i"),
                    {"c": canon, "i": rid},
                )
        if dtype is not None:
            conn.execute(
                sa.text("INSERT INTO offer_discounts "
                        "(offer_id, label, discount_type, discount_value, sort_order) "
                        "VALUES (:o, NULL, :t, :v, 0)"),
                {"o": rid, "t": dtype, "v": dval},
            )


def upgrade() -> None:
    op.add_column("offers", sa.Column("article_url_canonical", sa.String(length=1024), nullable=True))
    op.create_index("ix_offers_article_url_canonical", "offers",
                    ["article_url_canonical"], mysql_length=255)
    op.create_table(
        "offer_discounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("offer_id", sa.Integer(), sa.ForeignKey("offers.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("discount_type", _DISCOUNT_ENUM, nullable=True),
        sa.Column("discount_value", sa.Numeric(10, 2), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_offer_discounts_offer_id", "offer_discounts", ["offer_id"])
    _backfill(op.get_bind())


def downgrade() -> None:
    # Note: ix_offer_discounts_offer_id is not dropped explicitly here — on
    # MySQL it backs the offer_discounts.offer_id foreign key constraint, so
    # an explicit DROP INDEX before DROP TABLE fails with error 1553
    # ("needed in a foreign key constraint"). Dropping the table removes the
    # FK and its supporting index together.
    op.drop_table("offer_discounts")
    op.drop_index("ix_offers_article_url_canonical", table_name="offers")
    op.drop_column("offers", "article_url_canonical")
