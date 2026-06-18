"""add_opaque_public_ids

Adds an opaque, globally-unique `public_id` (UUID4 string) to the three
most sensitive, most externally-referenced personal-data tables — users,
children, enrollment_applications — as a foundation for exposing opaque
identifiers instead of sequential integers in any future public-facing
route (GWS S.5.10-026). The internal integer `id` remains the primary key
and FK target everywhere; this is purely additive.

Plain `op.add_column` (no batch mode) is used deliberately: `users` has many
incoming foreign keys, and `batch_alter_table` recreates the whole table,
which previously caused a topological-sort failure on this exact table
(see alembic/env.py history / project memory). A simple ADD COLUMN does not
need batch mode on SQLite or Postgres.

Existing rows are backfilled with generated UUIDs. The column is left
nullable at the database level (SQLite cannot add a NOT NULL constraint to
an existing column without a full table rebuild); the ORM model declares
`nullable=False` with a default, so every row written from here on always
gets a value — only pre-existing rows on very old databases could ever be
NULL, and this migration backfills all of those too.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-16 23:50:00.000000

"""
import uuid as uuid_lib
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("users", "children", "enrollment_applications")


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return any(c["name"] == column for c in insp.get_columns(table))


def _index_exists(table: str, index_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return any(ix["name"] == index_name for ix in insp.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()

    for table in TABLES:
        if not _column_exists(table, "public_id"):
            op.add_column(table, sa.Column("public_id", sa.String(36), nullable=True))

    # Backfill any existing rows that don't have one yet. Treat empty strings as
    # placeholders too: local runtime schema creation adds the column with an
    # empty default before Alembic has run.
    for table in TABLES:
        rows = bind.execute(sa.text(f"SELECT id FROM {table} WHERE public_id IS NULL OR public_id = ''")).fetchall()
        for (row_id,) in rows:
            bind.execute(
                sa.text(f"UPDATE {table} SET public_id = :pid WHERE id = :rid"),
                {"pid": str(uuid_lib.uuid4()), "rid": row_id},
            )

    for table in TABLES:
        idx_name = f"ix_{table}_public_id"
        if not _index_exists(table, idx_name):
            op.create_index(idx_name, table, ["public_id"], unique=True)


def downgrade() -> None:
    for table in TABLES:
        idx_name = f"ix_{table}_public_id"
        if _index_exists(table, idx_name):
            op.drop_index(idx_name, table_name=table)
    for table in TABLES:
        if _column_exists(table, "public_id"):
            op.drop_column(table, "public_id")
