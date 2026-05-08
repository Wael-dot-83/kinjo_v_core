"""Fix tasks table: rename created_by_id/assigned_to_id → created_by/assigned_to,
change due_date from TIMESTAMPTZ to DATE to match ORM model.

Revision ID: a0b1c2d3e4f5
Revises: c0d1e2f3a4b5
Create Date: 2026-05-10 00:00:00.000000
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "a0b1c2d3e4f5"
down_revision: Union[str, None] = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None


def _dialect() -> str:
    return op.get_bind().dialect.name


def _has_column(table: str, col: str) -> bool:
    if not sa.inspect(op.get_bind()).has_table(table):
        return False
    return col in [c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)]


def _index_exists(table: str, name: str) -> bool:
    if not sa.inspect(op.get_bind()).has_table(table):
        return False
    return name in [i["name"] for i in sa.inspect(op.get_bind()).get_indexes(table)]


def upgrade() -> None:
    need_rename_created = _has_column("tasks", "created_by_id")
    need_rename_assigned = _has_column("tasks", "assigned_to_id")
    need_type_fix = _has_column("tasks", "due_date")

    # Drop the old index that references assigned_to_id before rename
    if _index_exists("tasks", "idx_task_assigned_to"):
        op.drop_index("idx_task_assigned_to", table_name="tasks")

    if _dialect() == "sqlite":
        if need_rename_created or need_rename_assigned or need_type_fix:
            with op.batch_alter_table("tasks", recreate="always") as batch_op:
                if need_rename_created:
                    batch_op.alter_column("created_by_id", new_column_name="created_by")
                if need_rename_assigned:
                    batch_op.alter_column("assigned_to_id", new_column_name="assigned_to")
                # SQLite stores dates as text regardless; change declared type for Alembic metadata
                if need_type_fix:
                    batch_op.alter_column(
                        "due_date",
                        type_=sa.Date(),
                        existing_type=sa.DateTime(timezone=True),
                        existing_nullable=True,
                    )
    else:
        # PostgreSQL supports direct RENAME COLUMN and TYPE cast
        if need_rename_created:
            op.execute("ALTER TABLE tasks RENAME COLUMN created_by_id TO created_by")
        if need_rename_assigned:
            op.execute("ALTER TABLE tasks RENAME COLUMN assigned_to_id TO assigned_to")
        if need_type_fix:
            op.execute(
                "ALTER TABLE tasks ALTER COLUMN due_date TYPE DATE "
                "USING due_date::DATE"
            )

    # Recreate index using the correct (new) column name
    if not _index_exists("tasks", "idx_task_assigned_to"):
        op.create_index("idx_task_assigned_to", "tasks", ["assigned_to", "status"])


def downgrade() -> None:
    need_rename_created = _has_column("tasks", "created_by")
    need_rename_assigned = _has_column("tasks", "assigned_to")
    need_type_fix = _has_column("tasks", "due_date")

    if _index_exists("tasks", "idx_task_assigned_to"):
        op.drop_index("idx_task_assigned_to", table_name="tasks")

    if _dialect() == "sqlite":
        if need_rename_created or need_rename_assigned or need_type_fix:
            with op.batch_alter_table("tasks", recreate="always") as batch_op:
                if need_rename_created:
                    batch_op.alter_column("created_by", new_column_name="created_by_id")
                if need_rename_assigned:
                    batch_op.alter_column("assigned_to", new_column_name="assigned_to_id")
                if need_type_fix:
                    batch_op.alter_column(
                        "due_date",
                        type_=sa.DateTime(timezone=True),
                        existing_type=sa.Date(),
                        existing_nullable=True,
                    )
    else:
        if need_rename_created:
            op.execute("ALTER TABLE tasks RENAME COLUMN created_by TO created_by_id")
        if need_rename_assigned:
            op.execute("ALTER TABLE tasks RENAME COLUMN assigned_to TO assigned_to_id")
        if need_type_fix:
            op.execute(
                "ALTER TABLE tasks ALTER COLUMN due_date TYPE TIMESTAMPTZ "
                "USING due_date::TIMESTAMPTZ"
            )

    if not _index_exists("tasks", "idx_task_assigned_to"):
        op.create_index("idx_task_assigned_to", "tasks", ["assigned_to_id", "status"])
