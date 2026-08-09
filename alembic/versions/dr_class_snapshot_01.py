"""add immutable class snapshot to daily reports

Revision ID: dr_class_snapshot_01
Revises: supervisor_assignment_date_ck_01
"""
from alembic import op
import sqlalchemy as sa

revision = "dr_class_snapshot_01"
down_revision = "supervisor_assignment_date_ck_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("daily_reports", sa.Column("class_id", sa.Integer(), nullable=True))
    # Legacy rows have no historical enrollment snapshot. This best-effort
    # backfill preserves the current class, while supervisor access fails
    # closed for any row that cannot be associated with one.
    op.execute("""
        UPDATE daily_reports
        SET class_id = (
            SELECT enrollment.class_id
            FROM enrollment_applications AS enrollment
            WHERE enrollment.child_id = daily_reports.child_id
              AND enrollment.kindergarten_id = daily_reports.kindergarten_id
              AND enrollment.status = 'ACTIVE'
              AND enrollment.deleted_at IS NULL
              AND enrollment.class_id IS NOT NULL
            LIMIT 1
        )
        WHERE EXISTS (
            SELECT 1 FROM enrollment_applications AS enrollment
            WHERE enrollment.child_id = daily_reports.child_id
              AND enrollment.kindergarten_id = daily_reports.kindergarten_id
              AND enrollment.status = 'ACTIVE'
              AND enrollment.deleted_at IS NULL
              AND enrollment.class_id IS NOT NULL
        )
    """)
    with op.batch_alter_table("daily_reports") as batch:
        batch.create_foreign_key("fk_daily_reports_class_id", "classes", ["class_id"], ["id"])
        batch.create_index("ix_daily_reports_class_id", ["class_id"])


def downgrade() -> None:
    with op.batch_alter_table("daily_reports") as batch:
        batch.drop_index("ix_daily_reports_class_id")
        batch.drop_constraint("fk_daily_reports_class_id", type_="foreignkey")
        batch.drop_column("class_id")
