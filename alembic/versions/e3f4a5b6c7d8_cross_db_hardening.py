"""Cross-DB hardening: attendance FK + survey unique constraint.

Fixes two issues on SQLite left by c1a2b3d4e5f6:
  1. ALTER TABLE ADD CONSTRAINT is unsupported – use batch mode instead.
  2. Unique constraint on survey_responses requires duplicate pruning first.

Revision ID: e3f4a5b6c7d8
Revises: c1a2b3d4e5f6
Create Date: 2026-05-01 01:30:00.000000
"""
from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, None] = "c1a2b3d4e5f6"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Introspection helpers
# ---------------------------------------------------------------------------

def _dialect() -> str:
    return op.get_bind().dialect.name


def _has_table(t: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(t)


def _has_column(t: str, c: str) -> bool:
    if not _has_table(t):
        return False
    return c in [col["name"] for col in sa.inspect(op.get_bind()).get_columns(t)]


def _has_fk(t: str, name: str) -> bool:
    if not _has_table(t):
        return False
    return name in [fk["name"] for fk in sa.inspect(op.get_bind()).get_foreign_keys(t)]


def _has_constraint_or_index(t: str, name: str) -> bool:
    if not _has_table(t):
        return False
    insp = sa.inspect(op.get_bind())
    return (
        name in [c["name"] for c in insp.get_unique_constraints(t)]
        or name in [i["name"] for i in insp.get_indexes(t)]
    )


# ---------------------------------------------------------------------------
# Safe FK helpers
# ---------------------------------------------------------------------------

def _add_fk_column_safe(
    table: str,
    column: str,
    ref_table: str,
    ref_col: str,
    type_: sa.types.TypeEngine,
    nullable: bool = True,
) -> None:
    """Add column only; FK is created separately after backfill."""
    if not _has_column(table, column):
        op.add_column(table, sa.Column(column, type_, nullable=nullable))


def _create_fk_safe(
    table: str,
    column: str,
    ref_table: str,
    ref_col: str,
    fk_name: str,
) -> None:
    """Create FK portably.

    SQLite cannot ALTER TABLE ADD CONSTRAINT, so batch mode with
    recreate='always' rebuilds the table with the FK in the CREATE TABLE.
    PostgreSQL uses a direct ALTER TABLE ADD CONSTRAINT.
    Also guards against an equivalent FK already existing under a different
    name (e.g. fk_attendance_class from a prior migration run).
    """
    if not _has_table(table):
        return
    for fk in sa.inspect(op.get_bind()).get_foreign_keys(table):
        if fk.get("name") == fk_name:
            return
        if (
            fk.get("constrained_columns") == [column]
            and fk.get("referred_table") == ref_table
            and fk.get("referred_columns") == [ref_col]
        ):
            return  # equivalent FK exists under a different name – skip

    if _dialect() == "sqlite":
        with op.batch_alter_table(table, recreate="always") as batch_op:
            batch_op.create_foreign_key(fk_name, ref_table, [column], [ref_col])
    else:
        op.create_foreign_key(fk_name, table, ref_table, [column], [ref_col])


def _drop_fk_safe(table: str, fk_name: str) -> None:
    """Drop FK portably.

    SQLite batch mode drops the FK by rebuilding the table without it.
    PostgreSQL uses ALTER TABLE DROP CONSTRAINT.
    """
    if not _has_fk(table, fk_name):
        return
    if _dialect() == "sqlite":
        with op.batch_alter_table(table, recreate="always") as batch_op:
            batch_op.drop_constraint(fk_name, type_="foreignkey")
    else:
        op.drop_constraint(fk_name, table, type_="foreignkey")


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _backfill_class_id() -> None:
    """Populate attendance_logs.class_id from sessions.class_id where NULL.

    Skips gracefully when the sessions table or session_id column are absent;
    the FK is still created (nullable=True) even when no rows are backfilled.
    """
    if not _has_table("sessions") or not _has_column("attendance_logs", "session_id"):
        return
    attendance = sa.table(
        "attendance_logs",
        sa.column("class_id", sa.Integer),
        sa.column("session_id", sa.Integer),
    )
    sessions = sa.table(
        "sessions",
        sa.column("id", sa.Integer),
        sa.column("class_id", sa.Integer),
    )
    subq = (
        sa.select(sessions.c.class_id)
        .where(sessions.c.id == attendance.c.session_id)
        .scalar_subquery()
    )
    op.execute(
        attendance.update()
        .where(attendance.c.class_id.is_(None))
        .values(class_id=subq)
    )


def _deduplicate_survey_responses() -> None:
    """Keep the latest response per (user_id, survey_id); delete older dupes.

    Uses a window-function CTE so zero rows are deleted when no duplicates
    exist. The current schema stores the user FK as parent_id; we detect the
    actual column name at runtime so this stays safe after any rename.
    """
    if not _has_table("survey_responses"):
        return
    # Schema uses parent_id; spec column is user_id – detect whichever exists.
    user_col = "parent_id" if _has_column("survey_responses", "parent_id") else "user_id"
    if not _has_column("survey_responses", user_col):
        return

    r = sa.table(
        "survey_responses",
        sa.column("id", sa.Integer),
        sa.column(user_col, sa.Integer),
        sa.column("survey_id", sa.Integer),
        sa.column("created_at", sa.DateTime),
    )
    ranked = sa.select(
        r.c.id,
        sa.func.row_number()
        .over(
            partition_by=[r.c[user_col], r.c.survey_id],
            # .nulls_last() – SQLAlchemy 2.x method form; NOT the standalone nullslast()
            order_by=[r.c.created_at.desc().nulls_last(), r.c.id.desc()],
        )
        .label("rn"),
    ).cte("ranked")
    to_delete = sa.select(ranked.c.id).where(ranked.c.rn > 1)
    op.execute(r.delete().where(r.c.id.in_(to_delete)))


# ---------------------------------------------------------------------------
# Upgrade / downgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    # 1. Add class_id column (nullable) – no FK yet, so backfill can run first.
    _add_fk_column_safe(
        "attendance_logs", "class_id", "classes", "id", sa.Integer(), nullable=True
    )

    # 2. Populate class_id from sessions.class_id via session_id where possible.
    _backfill_class_id()

    # 3. Create the FK portably (batch rebuild on SQLite; ALTER TABLE on PG).
    _create_fk_safe(
        "attendance_logs", "class_id", "classes", "id", "fk_attendance_logs_class_id"
    )

    # 4. Prune duplicate survey responses before the unique constraint is added.
    _deduplicate_survey_responses()

    # 5. Enforce unique (user_id, survey_id) on survey_responses.
    if _has_table("survey_responses"):
        user_col = "parent_id" if _has_column("survey_responses", "parent_id") else "user_id"
        if _has_column("survey_responses", user_col):
            if _dialect() == "sqlite":
                if not _has_constraint_or_index("survey_responses", "ix_unique_user_survey"):
                    op.create_index(
                        "ix_unique_user_survey",
                        "survey_responses",
                        [user_col, "survey_id"],
                        unique=True,
                    )
            else:
                if not _has_constraint_or_index("survey_responses", "uq_user_survey"):
                    op.create_unique_constraint(
                        "uq_user_survey",
                        "survey_responses",
                        [user_col, "survey_id"],
                    )


def downgrade() -> None:
    # Reverse step 5: drop unique constraint / index.
    if _has_table("survey_responses"):
        if _dialect() == "sqlite":
            if _has_constraint_or_index("survey_responses", "ix_unique_user_survey"):
                op.drop_index("ix_unique_user_survey", table_name="survey_responses")
        else:
            if _has_constraint_or_index("survey_responses", "uq_user_survey"):
                op.drop_constraint("uq_user_survey", "survey_responses", type_="unique")

    # Reverse step 3: drop FK.
    _drop_fk_safe("attendance_logs", "fk_attendance_logs_class_id")

    # Reverse step 1: drop class_id column (batch mode on SQLite).
    if _has_column("attendance_logs", "class_id"):
        if _dialect() == "sqlite":
            with op.batch_alter_table("attendance_logs", recreate="always") as batch_op:
                batch_op.drop_column("class_id")
        else:
            op.drop_column("attendance_logs", "class_id")
