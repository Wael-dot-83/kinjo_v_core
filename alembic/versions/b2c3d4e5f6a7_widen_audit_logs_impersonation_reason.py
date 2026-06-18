"""widen_audit_logs_impersonation_reason

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-16 04:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_type(table: str, column: str):
    bind = op.get_bind()
    insp = inspect(bind)
    for c in insp.get_columns(table):
        if c["name"] == column:
            return c["type"]
    return None


def upgrade() -> None:
    existing_type = _column_type("audit_logs", "impersonation_reason")
    if existing_type is not None and not isinstance(existing_type, sa.Text):
        with op.batch_alter_table("audit_logs") as batch_op:
            batch_op.alter_column(
                "impersonation_reason",
                existing_type=sa.String(length=255),
                type_=sa.Text(),
                existing_nullable=True,
            )


def downgrade() -> None:
    existing_type = _column_type("audit_logs", "impersonation_reason")
    if existing_type is not None and not isinstance(existing_type, sa.String):
        with op.batch_alter_table("audit_logs") as batch_op:
            batch_op.alter_column(
                "impersonation_reason",
                existing_type=sa.Text(),
                type_=sa.String(length=255),
                existing_nullable=True,
            )
