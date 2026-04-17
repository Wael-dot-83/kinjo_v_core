"""add supervisor full_time_dedication column if missing

Revision ID: 20260219_add_supervisor_full_time_dedication
Revises: a38db517a179
Create Date: 2026-02-19 02:18:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260219_add_supervisor_full_time_dedication"
down_revision: Union[str, None] = "a38db517a179"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    if _table_exists("supervisor_assignments") and not _column_exists(
        "supervisor_assignments", "full_time_dedication"
    ):
        with op.batch_alter_table("supervisor_assignments", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "full_time_dedication",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("1"),
                )
            )
        with op.batch_alter_table("supervisor_assignments", schema=None) as batch_op:
            batch_op.alter_column("full_time_dedication", server_default=None)


def downgrade() -> None:
    if _table_exists("supervisor_assignments") and _column_exists(
        "supervisor_assignments", "full_time_dedication"
    ):
        with op.batch_alter_table("supervisor_assignments", schema=None) as batch_op:
            batch_op.drop_column("full_time_dedication")
