"""relax_ai_parent_rec_child_id_nullable

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-16 04:40:00.000000

ai/llm.py writes admin-level governance-case-study recommendations with
child_id=None (not tied to any specific child), but the original migration
declared the column NOT NULL — fixing the mismatch here.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_nullable(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    for c in insp.get_columns(table):
        if c["name"] == column:
            return c["nullable"]
    return True


def upgrade() -> None:
    if not _is_nullable("ai_parent_recommendations", "child_id"):
        with op.batch_alter_table("ai_parent_recommendations") as batch_op:
            batch_op.alter_column(
                "child_id",
                existing_type=sa.Integer(),
                nullable=True,
            )


def downgrade() -> None:
    if _is_nullable("ai_parent_recommendations", "child_id"):
        with op.batch_alter_table("ai_parent_recommendations") as batch_op:
            batch_op.alter_column(
                "child_id",
                existing_type=sa.Integer(),
                nullable=False,
            )
