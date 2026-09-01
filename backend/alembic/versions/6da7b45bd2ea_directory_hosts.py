"""directory_hosts

Revision ID: 6da7b45bd2ea
Revises: e2b4a6c8d0f1
Create Date: 2026-09-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "6da7b45bd2ea"
down_revision: Union[str, Sequence[str], None] = "e2b4a6c8d0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "directory_hosts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("host", name="uq_directory_hosts_host"),
    )


def downgrade() -> None:
    op.drop_table("directory_hosts")
