"""IAM hardening: lockout, password tracking, attendance picked_by_name + constraint

Revision ID: iam_hardening_001
Revises: f3da6d982bac
Create Date: 2025-02-10
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "iam_hardening_001"
down_revision = "f3da6d982bac"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    for col in inspector.get_columns(table_name):
        if col.get("name") == column_name:
            return True
    return False


def upgrade() -> None:
    # --- User IAM columns ---
    if not _column_exists("users", "failed_login_count"):
        op.add_column("users", sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"))
    if not _column_exists("users", "locked_until"):
        op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    if not _column_exists("users", "password_changed_at"):
        op.add_column("users", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))
    if not _column_exists("users", "last_login_at"):
        op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))

    # --- AttendanceLog: add picked_by_name + check constraint ---
    if not _column_exists("attendance_logs", "picked_by_name"):
        op.add_column("attendance_logs", sa.Column("picked_by_name", sa.String(200), nullable=True))

    # SQLite cannot reliably add a CHECK to an existing table without full recreate.
    # Keep migration deterministic across dialects by enforcing constraint on non-SQLite.
    if op.get_bind().dialect.name != "sqlite":
        op.create_check_constraint(
            "ck_attendance_checkout_after_checkin",
            "attendance_logs",
            "(check_out_at IS NULL) OR (check_in_at IS NULL) OR (check_out_at >= check_in_at)",
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint(
            "ck_attendance_checkout_after_checkin",
            "attendance_logs",
            type_="check",
        )
    if _column_exists("attendance_logs", "picked_by_name"):
        op.drop_column("attendance_logs", "picked_by_name")

    if _column_exists("users", "last_login_at"):
        op.drop_column("users", "last_login_at")
    if _column_exists("users", "password_changed_at"):
        op.drop_column("users", "password_changed_at")
    if _column_exists("users", "locked_until"):
        op.drop_column("users", "locked_until")
    if _column_exists("users", "failed_login_count"):
        op.drop_column("users", "failed_login_count")
