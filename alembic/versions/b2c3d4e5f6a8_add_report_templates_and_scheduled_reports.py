"""add_report_templates_and_scheduled_reports

Add report_templates and scheduled_reports tables for the enterprise Reports Center.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a8"
down_revision: Union[str, None] = "a1b2c3d4e5f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "report_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("report_type", sa.String(length=100), nullable=False),
        sa.Column("filters", sa.JSON(), nullable=True),
        sa.Column("export_format", sa.String(length=20), nullable=False, server_default="CSV"),
        sa.Column("include_charts", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("include_summary", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_report_templates_created_by", "report_templates", ["created_by"])

    op.create_table(
        "scheduled_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("report_type", sa.String(length=100), nullable=False),
        sa.Column("filters", sa.JSON(), nullable=True),
        sa.Column("export_format", sa.String(length=20), nullable=False, server_default="CSV"),
        sa.Column("frequency", sa.String(length=50), nullable=False),
        sa.Column("recipients", sa.JSON(), nullable=True),
        sa.Column("next_run", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scheduled_reports_created_by", "scheduled_reports", ["created_by"])
    op.create_index("ix_scheduled_reports_next_run", "scheduled_reports", ["next_run"])


def downgrade() -> None:
    op.drop_index("ix_scheduled_reports_next_run", table_name="scheduled_reports")
    op.drop_index("ix_scheduled_reports_created_by", table_name="scheduled_reports")
    op.drop_table("scheduled_reports")
    op.drop_index("ix_report_templates_created_by", table_name="report_templates")
    op.drop_table("report_templates")
