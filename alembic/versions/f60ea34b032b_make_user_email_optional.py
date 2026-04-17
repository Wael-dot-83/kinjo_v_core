"""Make users.email nullable in a migration-safe way.

Revision ID: f60ea34b032b
Revises: 79d8f9c0bde6
Create Date: 2026-01-20 23:02:24.719919
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f60ea34b032b"
down_revision: Union[str, None] = "79d8f9c0bde6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    inspector = sa.inspect(op.get_bind())
    return any(ix.get("name") == index_name for ix in inspector.get_indexes(table_name))


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    if _index_exists(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def _create_index_if_missing(
    index_name: str,
    table_name: str,
    columns: list[str],
    unique: bool = False,
) -> None:
    if _table_exists(table_name) and not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique, if_not_exists=True)


def upgrade() -> None:
    # Remove unique email indexes before making email nullable.
    _drop_index_if_exists("ix_users_email_unique", "users")
    _drop_index_if_exists("ix_users_email", "users")

    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        # SQLite requires table recreation for nullable changes.
        with op.batch_alter_table("users", recreate="always") as batch_op:
            batch_op.alter_column(
                "email",
                existing_type=sa.String(length=255),
                nullable=True,
            )
    else:
        op.alter_column(
            "users",
            "email",
            existing_type=sa.String(length=255),
            nullable=True,
        )

    _create_index_if_missing("idx_user_role_kindergarten", "users", ["role", "kindergarten_id"])
    _create_index_if_missing("ix_users_id", "users", ["id"])
    _create_index_if_missing("ix_users_username", "users", ["username"], unique=True)


def downgrade() -> None:
    # Guarantee non-nullability before altering column back.
    op.execute(sa.text("UPDATE users SET email = '' WHERE email IS NULL"))

    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("users", recreate="always") as batch_op:
            batch_op.alter_column(
                "email",
                existing_type=sa.String(length=255),
                nullable=False,
            )
    else:
        op.alter_column(
            "users",
            "email",
            existing_type=sa.String(length=255),
            nullable=False,
        )

    _create_index_if_missing("ix_users_email", "users", ["email"], unique=True)
    _create_index_if_missing("idx_user_role_kindergarten", "users", ["role", "kindergarten_id"])
    _create_index_if_missing("ix_users_id", "users", ["id"])
    _create_index_if_missing("ix_users_username", "users", ["username"], unique=True)

