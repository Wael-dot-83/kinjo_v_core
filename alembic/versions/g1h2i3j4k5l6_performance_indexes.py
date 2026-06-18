"""Performance indexes: pg_trgm extension, trigram index on users.username,
composite indexes on (role, status), (submitted_at, is_resolved) for contact_messages,
and (kindergarten_id, status) for enrollment_applications.

Revision ID: g1h2i3j4k5l6
Revises: f9a0b1c2d3e4
Create Date: 2026-06-14 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "g1h2i3j4k5l6"
down_revision: Union[str, None] = "f9a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_postgresql() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgresql():
        # SQLite does not support pg_trgm or concurrent index builds — skip gracefully.
        return

    # Enable pg_trgm for fast ILIKE / similarity searches on text columns.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # Trigram index on users.username — powers admin user-search ILIKE queries.
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_users_username_trgm "
        "ON users USING gin (username gin_trgm_ops)"
    )

    # Trigram index on users.email — powers admin email-search ILIKE queries.
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_users_email_trgm "
        "ON users USING gin (email gin_trgm_ops)"
    )

    # Composite index: role + status — admin user-list filters on both columns simultaneously.
    op.create_index(
        "ix_users_role_status",
        "users",
        ["role", "status"],
        if_not_exists=True,
    )

    # Composite index: contact_messages(submitted_at, is_resolved) — admin contact-message
    # list is always ordered by submitted_at and filtered by is_resolved.
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_contact_messages_submitted_resolved "
            "ON contact_messages (submitted_at DESC, is_resolved)"
        )

    # Composite index: enrollment_applications(kindergarten_id, status) — manager dashboard
    # loads pending enrollments for a given kindergarten.
    op.create_index(
        "ix_enrollment_applications_kg_status",
        "enrollment_applications",
        ["kindergarten_id", "status"],
        if_not_exists=True,
    )


def downgrade() -> None:
    if not _is_postgresql():
        return

    op.drop_index("ix_enrollment_applications_kg_status", table_name="enrollment_applications", if_exists=True)

    op.execute(
        "DROP INDEX CONCURRENTLY IF EXISTS ix_contact_messages_submitted_resolved"
    )

    op.drop_index("ix_users_role_status", table_name="users", if_exists=True)

    op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_users_email_trgm")
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_users_username_trgm")
    # Note: do NOT drop pg_trgm extension here — other indexes may depend on it.
