"""Add missing performance indexes to critical tables.

Revision ID: a1b2c3d4e5f6
Revises: f66e02e0bc57
Create Date: 2026-04-17 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f66e02e0bc57"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users table ---
    op.create_index("ix_users_role", "users", ["role"])
    op.create_index("ix_users_status", "users", ["status"])
    op.create_index("ix_users_kindergarten_id", "users", ["kindergarten_id"])
    op.create_index("ix_users_role_status", "users", ["role", "status"])

    # --- attendance_logs table ---
    op.create_index("ix_attendance_date", "attendance_logs", ["date"])
    op.create_index("ix_attendance_class_id", "attendance_logs", ["class_id"])
    op.create_index("ix_attendance_class_date", "attendance_logs", ["class_id", "date"])
    op.create_index("ix_attendance_recorded_by", "attendance_logs", ["recorded_by"])

    # --- password_reset_tokens table ---
    op.create_index("ix_password_reset_tokens_used", "password_reset_tokens", ["used"])
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])


def downgrade() -> None:
    # --- password_reset_tokens table ---
    op.drop_index("ix_password_reset_tokens_user_id", table_name="password_reset_tokens")
    op.drop_index("ix_password_reset_tokens_used", table_name="password_reset_tokens")

    # --- attendance_logs table ---
    op.drop_index("ix_attendance_recorded_by", table_name="attendance_logs")
    op.drop_index("ix_attendance_class_date", table_name="attendance_logs")
    op.drop_index("ix_attendance_class_id", table_name="attendance_logs")
    op.drop_index("ix_attendance_date", table_name="attendance_logs")

    # --- users table ---
    op.drop_index("ix_users_role_status", table_name="users")
    op.drop_index("ix_users_kindergarten_id", table_name="users")
    op.drop_index("ix_users_status", table_name="users")
    op.drop_index("ix_users_role", table_name="users")
