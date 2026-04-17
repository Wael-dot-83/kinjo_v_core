"""Allow nullable kindergarten_id on messages for cross-KG announcements

Revision ID: 20260122_make_message_kindergarten_nullable
Revises: 8f3cc3e78b4f
Create Date: 2026-01-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260122_make_message_kindergarten_nullable"
down_revision: Union[str, None] = "8f3cc3e78b4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use batch operation for SQLite compatibility
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.alter_column(
            "kindergarten_id",
            existing_type=sa.Integer(),
            nullable=True
        )


def downgrade() -> None:
    # Use batch operation for SQLite compatibility
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.alter_column(
            "kindergarten_id",
            existing_type=sa.Integer(),
            nullable=False
        )
