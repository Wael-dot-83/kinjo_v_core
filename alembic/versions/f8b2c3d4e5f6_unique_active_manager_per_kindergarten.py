"""enforce one active manager per kindergarten

Revision ID: f8b2c3d4e5f6
Revises: f7a1c2e9b3d0
Create Date: 2026-07-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f8b2c3d4e5f6"
down_revision: Union[str, None] = "f7a1c2e9b3d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    duplicates = op.get_bind().execute(sa.text("""
        SELECT kindergarten_id, COUNT(*) AS manager_count
        FROM users
        WHERE role = 'MANAGER'
          AND status = 'ACTIVE'
          AND deleted_at IS NULL
        GROUP BY kindergarten_id
        HAVING COUNT(*) > 1
    """)).fetchall()
    if duplicates:
        ids = ", ".join(str(row[0]) for row in duplicates)
        raise RuntimeError(
            "Cannot enforce one active manager per kindergarten; "
            f"resolve duplicate active managers for kindergarten IDs: {ids}"
        )

    predicate = sa.text("role = 'MANAGER' AND status = 'ACTIVE' AND deleted_at IS NULL")
    op.create_index(
        "uq_users_active_manager_per_kindergarten",
        "users",
        ["kindergarten_id"],
        unique=True,
        postgresql_where=predicate,
        sqlite_where=predicate,
    )


def downgrade() -> None:
    op.drop_index("uq_users_active_manager_per_kindergarten", table_name="users")
