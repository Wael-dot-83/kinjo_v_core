"""Add unique email constraint and indexes for admin security

Revision ID: 20250120_unique_email
Revises: previous_revision
Create Date: 2025-01-20

This migration adds:
1. Unique constraint on users.email (if not already present)
2. Index on users.username for faster lookups
3. Index on users.kindergarten_id for role-scoped queries
4. Index on audit_logs.created_at for date filtering
5. Index on audit_logs.user_id for user filtering
6. Index on password_reset_tokens.token for token lookups
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '20250120_unique_email'
down_revision = None  # Update this to your actual previous revision
branch_labels = None
depends_on = None


def upgrade():
    """Add security-related indexes and constraints."""

    # Create index on users.email if not exists (for unique constraint performance)
    op.create_index(
        'ix_users_email_unique',
        'users',
        ['email'],
        unique=True,
        if_not_exists=True
    )

    # Create index on users.username for faster auth lookups
    op.create_index(
        'ix_users_username_lookup',
        'users',
        ['username'],
        unique=True,
        if_not_exists=True
    )

    # Create index on users.kindergarten_id for scoped queries
    op.create_index(
        'ix_users_kindergarten_id',
        'users',
        ['kindergarten_id'],
        if_not_exists=True
    )

    # Create index on users for role-based filtering
    op.create_index(
        'ix_users_role_status',
        'users',
        ['role', 'status'],
        if_not_exists=True
    )

    # Create index on audit_logs.created_at for date filtering
    op.create_index(
        'ix_audit_logs_created_at',
        'audit_logs',
        ['created_at'],
        if_not_exists=True
    )

    # Create index on audit_logs.user_id for user filtering
    op.create_index(
        'ix_audit_logs_user_id',
        'audit_logs',
        ['user_id'],
        if_not_exists=True
    )

    # Create index on audit_logs for action type filtering
    op.create_index(
        'ix_audit_logs_action',
        'audit_logs',
        ['action'],
        if_not_exists=True
    )

    # Create index on password_reset_tokens.token for fast lookups
    op.create_index(
        'ix_password_reset_tokens_token',
        'password_reset_tokens',
        ['token'],
        unique=True,
        if_not_exists=True
    )

    # Create index on password_reset_tokens for user + validity check
    op.create_index(
        'ix_password_reset_tokens_user_valid',
        'password_reset_tokens',
        ['user_id', 'used', 'expires_at'],
        if_not_exists=True
    )


def downgrade():
    """Remove security-related indexes and constraints."""

    # Remove indexes in reverse order
    op.drop_index('ix_password_reset_tokens_user_valid', table_name='password_reset_tokens')
    op.drop_index('ix_password_reset_tokens_token', table_name='password_reset_tokens')
    op.drop_index('ix_audit_logs_action', table_name='audit_logs')
    op.drop_index('ix_audit_logs_user_id', table_name='audit_logs')
    op.drop_index('ix_audit_logs_created_at', table_name='audit_logs')
    op.drop_index('ix_users_role_status', table_name='users')
    op.drop_index('ix_users_kindergarten_id', table_name='users')
    op.drop_index('ix_users_username_lookup', table_name='users')
    op.drop_index('ix_users_email_unique', table_name='users')
