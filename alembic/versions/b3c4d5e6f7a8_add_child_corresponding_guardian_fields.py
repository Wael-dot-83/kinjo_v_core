"""add_child_corresponding_guardian_fields

Revision ID: b3c4d5e6f7a8
Revises: 5b7c8d9e0f1a
Create Date: 2026-06-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "5b7c8d9e0f1a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    with op.batch_alter_table("children") as batch_op:
        if not _column_exists("children", "corresponding_type"):
            batch_op.add_column(sa.Column("corresponding_type", sa.String(length=20), nullable=True))
        if not _column_exists("children", "corresponding_phone"):
            batch_op.add_column(sa.Column("corresponding_phone", sa.String(length=20), nullable=True))
        if not _column_exists("children", "corresponding_pending_reason"):
            batch_op.add_column(sa.Column("corresponding_pending_reason", sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("children") as batch_op:
        if _column_exists("children", "corresponding_pending_reason"):
            batch_op.drop_column("corresponding_pending_reason")
        if _column_exists("children", "corresponding_phone"):
            batch_op.drop_column("corresponding_phone")
        if _column_exists("children", "corresponding_type"):
            batch_op.drop_column("corresponding_type")
