"""Add governance daily report views and reminders tables

Revision ID: 20260211_add_governance_daily_reports
Revises: 7d792f81c264
Create Date: 2026-02-11
"""
from alembic import op
import sqlalchemy as sa

revision = "20260211_add_governance_daily_reports"
down_revision = "7d792f81c264"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_report_views",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("daily_report_id", sa.Integer(), sa.ForeignKey("daily_reports.id"), nullable=False),
        sa.Column("parent_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("viewed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("daily_report_id", "parent_user_id", name="uq_daily_report_view"),
        sa.Index("ix_daily_report_views_report", "daily_report_id"),
    )

    op.create_table(
        "governance_reminders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("reminder_type", sa.String(50), nullable=False),
        sa.Column("sent_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("cooldown_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Index("ix_governance_reminders_target", "target_type", "target_id", "cooldown_expires_at"),
    )


def downgrade() -> None:
    op.drop_table("governance_reminders")
    op.drop_table("daily_report_views")
