"""add offers.rejection_reason (judge/admin rejection reason + judge-reject marker)

Revision ID: e2b4a6c8d0f1
Revises: c5e7a9b1d3f8
Create Date: 2026-08-26 10:00:00.000000

Nullable, no backfill. Also serves as the "rejected by judge" marker: judge_reject sets
status=rejected + reviewed_by=NULL + rejection_reason=<text>; admin reject (set_status)
sets reviewed_by and leaves this column untouched.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e2b4a6c8d0f1"
down_revision: Union[str, Sequence[str], None] = "c5e7a9b1d3f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("offers", sa.Column("rejection_reason", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("offers", "rejection_reason")
