"""add_parent_profile_parent_type

Revision ID: a1b2c3d4e5f6
Revises: 42ccd5fefd32
Create Date: 2026-06-16 04:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '42ccd5fefd32'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    if not _column_exists("parent_profiles", "parent_type"):
        with op.batch_alter_table("parent_profiles") as batch_op:
            batch_op.add_column(sa.Column("parent_type", sa.String(length=20), nullable=True))


def downgrade() -> None:
    if _column_exists("parent_profiles", "parent_type"):
        with op.batch_alter_table("parent_profiles") as batch_op:
            batch_op.drop_column("parent_type")
