"""add per-meal times and attendance late_reason

These five columns exist on the SQLAlchemy models but were never given a
migration, so every deployed database was missing them while alembic reported
head. SQLAlchemy omits unset nullable columns from an INSERT, which is why
writes kept succeeding and hid the gap; any SELECT of the full model raised
`no such column`. In practice /api/supervisor/children answered 500 on
attendance_logs.late_reason, which took the whole class roster down with it.

All five are nullable with no default, so the migration adds columns and
touches no existing row.

Revision ID: meal_times_late_reason_01
Revises: dr_class_snapshot_01
"""
from alembic import op
import sqlalchemy as sa

revision = "meal_times_late_reason_01"
down_revision = "dr_class_snapshot_01"
branch_labels = None
depends_on = None


# (table, column, type) — VARCHAR(5) holds "HH:MM", matching nap_start/nap_end.
_COLUMNS = (
    ("daily_reports", "breakfast_time", sa.String(length=5)),
    ("daily_reports", "snack_time", sa.String(length=5)),
    ("daily_reports", "milk_time", sa.String(length=5)),
    ("daily_reports", "lunch_time", sa.String(length=5)),
    ("attendance_logs", "late_reason", sa.Text()),
)


def _existing_columns(table: str) -> set[str]:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return {c["name"] for c in insp.get_columns(table)}



def upgrade() -> None:
    # Guarded so the migration is safe on a database where someone already
    # patched a column in by hand, which is how these gaps usually get papered
    # over before anyone writes the migration.
    for table, column, type_ in _COLUMNS:
        if column not in _existing_columns(table):
            op.add_column(table, sa.Column(column, type_, nullable=True))


def downgrade() -> None:
    for table, column, _type in reversed(_COLUMNS):
        if column in _existing_columns(table):
            with op.batch_alter_table(table) as batch:
                batch.drop_column(column)
