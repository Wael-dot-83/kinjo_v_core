"""reconcile active kindergartens without managers

Revision ID: a9c3d4e5f607
Revises: f8b2c3d4e5f6
Create Date: 2026-07-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a9c3d4e5f607"
down_revision: Union[str, None] = "f8b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Preserve legacy non-operational rows as DRAFT. Assigning a manager later
    # activates the kindergarten atomically through the supported workflow.
    op.get_bind().execute(sa.text("""
        UPDATE kindergartens
        SET status = 'DRAFT'
        WHERE status = 'ACTIVE'
          AND NOT EXISTS (
              SELECT 1
              FROM users
              WHERE users.kindergarten_id = kindergartens.id
                AND users.role = 'MANAGER'
                AND users.status = 'ACTIVE'
                AND users.deleted_at IS NULL
          )
    """))


def downgrade() -> None:
    # The former operational status cannot be reconstructed safely.
    pass
