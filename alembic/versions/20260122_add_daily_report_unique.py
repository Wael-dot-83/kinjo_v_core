"""add_daily_report_unique

Revision ID: 20260122_add_daily_report_unique
Revises: 20260122_make_message_kindergarten_nullable
Create Date: 2026-01-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260122_add_daily_report_unique"
down_revision: Union[str, None] = "20260122_make_message_kindergarten_nullable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use batch operation for SQLite compatibility
    with op.batch_alter_table("daily_reports", schema=None) as batch_op:
        batch_op.create_unique_constraint("uq_daily_report_child_date", ["child_id", "date"])
        batch_op.create_index("ix_daily_reports_child_date", ["child_id", "date"])


def downgrade() -> None:
    # Use batch operation for SQLite compatibility
    with op.batch_alter_table("daily_reports", schema=None) as batch_op:
        batch_op.drop_index("ix_daily_reports_child_date")
        batch_op.drop_constraint("uq_daily_report_child_date", type_="unique")
