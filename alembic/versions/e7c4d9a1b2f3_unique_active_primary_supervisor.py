"""enforce one active primary supervisor per class (finding #1)

Revision ID: e7c4d9a1b2f3
Revises: d4a2c1b8e6f0
Create Date: 2026-07-07 21:20:00.000000

The retired legacy Class.supervisor_id column used to guarantee (via app logic)
that a class had at most one primary supervisor. SupervisorAssignment has no such
constraint, so a race/bug could create two active is_primary rows for one class,
which would double-count supervisor workload metrics and make the active-primary
lookup pick an arbitrary row. This adds a partial UNIQUE index enforcing at most
one row per class where (is_primary AND deleted_at IS NULL), after retiring any
existing duplicates (keeping the newest).

NOTE: the migration chain is currently forked (this branch head d4a2c1b8e6f0 and
the kindergarten-management branch head d4a2b8c1f0e9 both descend from
c3f1a7d9e2b0). An `alembic merge` of the two heads is required before
`alembic upgrade head` will run — that merge should be created once both branches
are committed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "e7c4d9a1b2f3"
down_revision: Union[str, None] = "d4a2c1b8e6f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX = "uq_supervisor_assignments_primary_per_class"


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    is_true = "is_primary IS TRUE" if dialect == "postgresql" else "is_primary = 1"

    # 1) Retire duplicate active primaries, keeping the newest (max id) per class,
    #    so the unique index below can be created.
    op.execute(sa.text(
        f"""
        UPDATE supervisor_assignments
        SET deleted_at = CURRENT_TIMESTAMP, end_date = CURRENT_DATE
        WHERE {is_true} AND deleted_at IS NULL
          AND id NOT IN (
              SELECT MAX(id) FROM supervisor_assignments
              WHERE {is_true} AND deleted_at IS NULL
              GROUP BY class_id
          )
        """
    ))

    # 2) Create the partial unique index (idempotent).
    existing = {ix["name"] for ix in inspect(bind).get_indexes("supervisor_assignments")}
    if _INDEX not in existing:
        op.create_index(
            _INDEX,
            "supervisor_assignments",
            ["class_id"],
            unique=True,
            sqlite_where=sa.text("is_primary = 1 AND deleted_at IS NULL"),
            postgresql_where=sa.text("is_primary AND deleted_at IS NULL"),
        )


def downgrade() -> None:
    existing = {ix["name"] for ix in inspect(op.get_bind()).get_indexes("supervisor_assignments")}
    if _INDEX in existing:
        op.drop_index(_INDEX, table_name="supervisor_assignments")
