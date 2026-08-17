"""Enforce Jordan business-date semantics for DailyReport check constraint.

Revision ID: daily_report_jordan_date_01
Revises: notif_delivery_retry_01
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa


revision = "daily_report_jordan_date_01"
down_revision = "notif_delivery_retry_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE daily_reports DROP CONSTRAINT IF EXISTS ck_report_not_future")
        op.execute("""
            ALTER TABLE daily_reports
                ADD CONSTRAINT ck_report_not_future
                CHECK (date <= (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Amman')::date)
        """)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE daily_reports DROP CONSTRAINT IF EXISTS ck_report_not_future")
        op.execute("""
            ALTER TABLE daily_reports
                ADD CONSTRAINT ck_report_not_future
                CHECK (date <= CURRENT_DATE)
        """)
