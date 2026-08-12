"""add scheduled_chart_exports

Recurring chart exports delivered by email.

Revision ID: sched_chart_exports_01
Revises: audit_details_text_01
Create Date: 2026-08-13
"""

from alembic import op
import sqlalchemy as sa

revision = "sched_chart_exports_01"
down_revision = "audit_details_text_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduled_chart_exports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("chart_type", sa.String(length=30), nullable=True),
        sa.Column("date_preset", sa.String(length=20), nullable=False, server_default="last_30"),
        sa.Column("export_format", sa.String(length=10), nullable=False, server_default="CSV"),
        sa.Column("frequency", sa.String(length=10), nullable=False, server_default="WEEKLY"),
        sa.Column("hour_utc", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("recipient_email", sa.String(length=255), nullable=False),
        sa.Column("governorate", sa.String(length=100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_status", sa.String(length=20), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("hour_utc >= 0 AND hour_utc <= 23", name="ck_sched_export_hour_range"),
        sa.CheckConstraint(
            "frequency IN ('DAILY','WEEKLY','MONTHLY')", name="ck_sched_export_frequency"
        ),
        sa.CheckConstraint("export_format IN ('CSV','JSON')", name="ck_sched_export_format"),
    )
    op.create_index("ix_scheduled_chart_exports_id", "scheduled_chart_exports", ["id"])
    op.create_index("ix_scheduled_chart_exports_user_id", "scheduled_chart_exports", ["user_id"])
    op.create_index("ix_scheduled_chart_exports_next_run_at", "scheduled_chart_exports", ["next_run_at"])
    # The due-schedule sweep filters on both columns together.
    op.create_index("ix_sched_export_due", "scheduled_chart_exports", ["is_active", "next_run_at"])


def downgrade() -> None:
    op.drop_index("ix_sched_export_due", table_name="scheduled_chart_exports")
    op.drop_index("ix_scheduled_chart_exports_next_run_at", table_name="scheduled_chart_exports")
    op.drop_index("ix_scheduled_chart_exports_user_id", table_name="scheduled_chart_exports")
    op.drop_index("ix_scheduled_chart_exports_id", table_name="scheduled_chart_exports")
    op.drop_table("scheduled_chart_exports")
