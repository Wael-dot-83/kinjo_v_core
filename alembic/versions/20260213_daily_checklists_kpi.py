"""Add daily checklists table for governance KPI

Revision ID: 20260213_daily_checklists_kpi
Revises: 20260212_mgr_scope, f66e02e0bc57
Create Date: 2026-02-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260213_daily_checklists_kpi"
down_revision: Union[str, Sequence[str], None] = ("20260212_mgr_scope", "f66e02e0bc57")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "daily_checklists",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kindergarten_id", sa.Integer(), nullable=False),
        sa.Column("checklist_date", sa.Date(), nullable=False),
        sa.Column("checklist_type", sa.String(length=50), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "COMPLETED", "NOT_REQUIRED", name="dailycheckliststatus"),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("submitted_by", sa.Integer(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["kindergarten_id"], ["kindergartens.id"]),
        sa.ForeignKeyConstraint(["submitted_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "kindergarten_id",
            "checklist_date",
            "checklist_type",
            name="uq_daily_checklist_kindergarten_date_type",
        ),
    )
    op.create_index(
        "ix_daily_checklists_kindergarten_date",
        "daily_checklists",
        ["kindergarten_id", "checklist_date"],
        unique=False,
    )
    op.create_index("ix_daily_checklists_status", "daily_checklists", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_daily_checklists_status", table_name="daily_checklists")
    op.drop_index("ix_daily_checklists_kindergarten_date", table_name="daily_checklists")
    op.drop_table("daily_checklists")

