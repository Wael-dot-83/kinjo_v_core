"""enforce valid supervisor assignment date ranges

Revision ID: supervisor_assignment_date_ck_01
Revises: analytics_idx_01
"""
from alembic import op

revision = "supervisor_assignment_date_ck_01"
down_revision = "analytics_idx_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("supervisor_assignments") as batch:
        batch.create_check_constraint(
            "ck_supervisor_assignment_dates",
            "end_date IS NULL OR end_date >= start_date",
        )


def downgrade() -> None:
    with op.batch_alter_table("supervisor_assignments") as batch:
        batch.drop_constraint("ck_supervisor_assignment_dates", type_="check")
