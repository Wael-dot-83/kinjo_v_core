"""Add FK cascade / SET NULL rules for user-owned records.

Revision ID: p2_fk_cascade_001
Revises: c17d2043714e
Create Date: 2026-06-25

Changes:
  - users.deleted_by → SET NULL on delete
  - parent_profiles.user_id → CASCADE on delete
  - parent_profiles.deleted_by → SET NULL on delete
  - children.deleted_by → SET NULL on delete
  - password_reset_tokens.user_id → CASCADE on delete
  - user_dashboard_preferences.user_id → CASCADE on delete
  - user_filter_preferences.user_id → CASCADE on delete
  - supervisor_profiles.user_id → CASCADE on delete
  - supervisor_profiles.kindergarten_id → CASCADE on delete

SQLite (used in test / dev) does not support ALTER TABLE … DROP/ADD CONSTRAINT;
only the downgrade is a no-op there.  In production PostgreSQL, each FK is
dropped and recreated with the correct ON DELETE rule.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import reflection


revision = "p2_fk_cascade_001"
down_revision = "c17d2043714e"
branch_labels = None
depends_on = None


def _is_postgresql() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def _recreate_fk(
    table: str,
    constraint_name: str,
    local_col: str,
    ref_table: str,
    ref_col: str,
    on_delete: str,
) -> None:
    """Drop (if it exists) and recreate a FK with the desired ON DELETE rule."""
    # Drop existing constraint if present. A bare try/except around
    # op.drop_constraint does NOT work on PostgreSQL: a failed DROP aborts the
    # whole transaction, so the create_foreign_key below then fails with
    # "current transaction is aborted". DROP CONSTRAINT IF EXISTS is the
    # idempotent, transaction-safe form (this migration is PostgreSQL-only).
    op.execute(f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint_name}')

    op.create_foreign_key(
        constraint_name,
        table,
        ref_table,
        [local_col],
        [ref_col],
        ondelete=on_delete,
    )


def upgrade() -> None:
    if not _is_postgresql():
        return

    _recreate_fk(
        "users", "users_deleted_by_fkey",
        "deleted_by", "users", "id", "SET NULL",
    )
    _recreate_fk(
        "parent_profiles", "parent_profiles_user_id_fkey",
        "user_id", "users", "id", "CASCADE",
    )
    _recreate_fk(
        "parent_profiles", "parent_profiles_deleted_by_fkey",
        "deleted_by", "users", "id", "SET NULL",
    )
    _recreate_fk(
        "children", "children_deleted_by_fkey",
        "deleted_by", "users", "id", "SET NULL",
    )
    _recreate_fk(
        "password_reset_tokens", "password_reset_tokens_user_id_fkey",
        "user_id", "users", "id", "CASCADE",
    )
    _recreate_fk(
        "user_dashboard_preferences", "user_dashboard_preferences_user_id_fkey",
        "user_id", "users", "id", "CASCADE",
    )
    _recreate_fk(
        "user_filter_preferences", "user_filter_preferences_user_id_fkey",
        "user_id", "users", "id", "CASCADE",
    )
    _recreate_fk(
        "supervisor_profiles", "supervisor_profiles_user_id_fkey",
        "user_id", "users", "id", "CASCADE",
    )
    _recreate_fk(
        "supervisor_profiles", "supervisor_profiles_kindergarten_id_fkey",
        "kindergarten_id", "kindergartens", "id", "CASCADE",
    )


def downgrade() -> None:
    if not _is_postgresql():
        return

    # Revert to plain FK (no explicit ON DELETE → DB default RESTRICT/NO ACTION)
    _recreate_fk(
        "users", "users_deleted_by_fkey",
        "deleted_by", "users", "id", "NO ACTION",
    )
    _recreate_fk(
        "parent_profiles", "parent_profiles_user_id_fkey",
        "user_id", "users", "id", "NO ACTION",
    )
    _recreate_fk(
        "parent_profiles", "parent_profiles_deleted_by_fkey",
        "deleted_by", "users", "id", "NO ACTION",
    )
    _recreate_fk(
        "children", "children_deleted_by_fkey",
        "deleted_by", "users", "id", "NO ACTION",
    )
    _recreate_fk(
        "password_reset_tokens", "password_reset_tokens_user_id_fkey",
        "user_id", "users", "id", "NO ACTION",
    )
    _recreate_fk(
        "user_dashboard_preferences", "user_dashboard_preferences_user_id_fkey",
        "user_id", "users", "id", "NO ACTION",
    )
    _recreate_fk(
        "user_filter_preferences", "user_filter_preferences_user_id_fkey",
        "user_id", "users", "id", "NO ACTION",
    )
    _recreate_fk(
        "supervisor_profiles", "supervisor_profiles_user_id_fkey",
        "user_id", "users", "id", "NO ACTION",
    )
    _recreate_fk(
        "supervisor_profiles", "supervisor_profiles_kindergarten_id_fkey",
        "kindergarten_id", "kindergartens", "id", "NO ACTION",
    )
