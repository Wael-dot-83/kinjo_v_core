"""Add security indexes and password reset token table bootstrap.

Revision ID: 20250120_unique_email
Revises: 7d792f81c264
Create Date: 2025-01-20
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "20250120_unique_email"
down_revision = "7d792f81c264"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    inspector = sa.inspect(op.get_bind())
    return any(ix.get("name") == index_name for ix in inspector.get_indexes(table_name))


def _create_index_if_missing(
    index_name: str,
    table_name: str,
    columns: list[str],
    unique: bool = False,
) -> None:
    if _table_exists(table_name) and not _index_exists(table_name, index_name):
        op.create_index(
            index_name,
            table_name,
            columns,
            unique=unique,
            if_not_exists=True,
        )


def upgrade() -> None:
    """Add security-related indexes and backfill missing token table."""

    _create_index_if_missing("ix_users_email_unique", "users", ["email"], unique=True)
    _create_index_if_missing("ix_users_username_lookup", "users", ["username"], unique=True)
    _create_index_if_missing("ix_users_kindergarten_id", "users", ["kindergarten_id"])
    _create_index_if_missing("ix_users_role_status", "users", ["role", "status"])
    _create_index_if_missing("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    _create_index_if_missing("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    _create_index_if_missing("ix_audit_logs_action", "audit_logs", ["action"])

    if not _table_exists("password_reset_tokens"):
        op.create_table(
            "password_reset_tokens",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("token", sa.String(length=255), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    _create_index_if_missing(
        "ix_password_reset_tokens_token",
        "password_reset_tokens",
        ["token"],
        unique=True,
    )
    _create_index_if_missing(
        "ix_password_reset_tokens_user_valid",
        "password_reset_tokens",
        ["user_id", "used", "expires_at"],
    )


def downgrade() -> None:
    """Remove indexes added by this migration when present."""

    if _index_exists("password_reset_tokens", "ix_password_reset_tokens_user_valid"):
        op.drop_index("ix_password_reset_tokens_user_valid", table_name="password_reset_tokens")
    if _index_exists("password_reset_tokens", "ix_password_reset_tokens_token"):
        op.drop_index("ix_password_reset_tokens_token", table_name="password_reset_tokens")
    if _index_exists("audit_logs", "ix_audit_logs_action"):
        op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    if _index_exists("audit_logs", "ix_audit_logs_user_id"):
        op.drop_index("ix_audit_logs_user_id", table_name="audit_logs")
    if _index_exists("audit_logs", "ix_audit_logs_created_at"):
        op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    if _index_exists("users", "ix_users_role_status"):
        op.drop_index("ix_users_role_status", table_name="users")
    if _index_exists("users", "ix_users_kindergarten_id"):
        op.drop_index("ix_users_kindergarten_id", table_name="users")
    if _index_exists("users", "ix_users_username_lookup"):
        op.drop_index("ix_users_username_lookup", table_name="users")
    if _index_exists("users", "ix_users_email_unique"):
        op.drop_index("ix_users_email_unique", table_name="users")
