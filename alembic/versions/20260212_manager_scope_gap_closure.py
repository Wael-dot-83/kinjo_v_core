"""Manager scope gap closure: profile fields + child indicators

Revision ID: 20260212_mgr_scope
Revises: 20260211_add_governance_daily_reports
Create Date: 2026-02-12
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "20260212_mgr_scope"
down_revision = "20260211_add_governance_daily_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # User profile fields (all nullable for backward compatibility)
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("full_name", sa.String(255), nullable=True))
        batch_op.add_column(sa.Column("phone_number", sa.String(20), nullable=True))
        batch_op.add_column(sa.Column("address", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("nationality", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("national_id", sa.String(50), nullable=True))
        batch_op.add_column(sa.Column("passport_number", sa.String(50), nullable=True))

    # Child boolean indicators (server_default for existing rows)
    with op.batch_alter_table("children") as batch_op:
        batch_op.add_column(
            sa.Column("has_special_needs", sa.Boolean(), nullable=False, server_default="false")
        )
        batch_op.add_column(
            sa.Column("has_medical_condition", sa.Boolean(), nullable=False, server_default="false")
        )


def downgrade() -> None:
    with op.batch_alter_table("children") as batch_op:
        batch_op.drop_column("has_medical_condition")
        batch_op.drop_column("has_special_needs")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("passport_number")
        batch_op.drop_column("national_id")
        batch_op.drop_column("nationality")
        batch_op.drop_column("address")
        batch_op.drop_column("phone_number")
        batch_op.drop_column("full_name")
