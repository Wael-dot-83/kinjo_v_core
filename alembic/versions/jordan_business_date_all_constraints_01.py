"""Enforce Jordan business-date semantics for Attendance, Child DOB, and Incident check constraints.

Revision ID: jordan_business_date_all_01
Revises: daily_report_jordan_date_01
Create Date: 2026-08-18 00:32:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'jordan_business_date_all_01'
down_revision = 'daily_report_jordan_date_01'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # 1. attendance_logs
        op.execute("ALTER TABLE attendance_logs DROP CONSTRAINT IF EXISTS ck_attendance_not_future")
        op.execute("""
            ALTER TABLE attendance_logs
            ADD CONSTRAINT ck_attendance_not_future
            CHECK (date <= (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Amman')::date)
        """)

        # 2. children
        op.execute("ALTER TABLE children DROP CONSTRAINT IF EXISTS ck_children_dob_not_future")
        op.execute("""
            ALTER TABLE children
            ADD CONSTRAINT ck_children_dob_not_future
            CHECK (date_of_birth <= (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Amman')::date)
        """)

        # 3. incidents
        op.execute("ALTER TABLE incidents DROP CONSTRAINT IF EXISTS ck_incident_not_future")
        op.execute("""
            ALTER TABLE incidents
            ADD CONSTRAINT ck_incident_not_future
            CHECK (DATE(occurred_at AT TIME ZONE 'Asia/Amman') <= (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Amman')::date)
        """)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # 1. attendance_logs
        op.execute("ALTER TABLE attendance_logs DROP CONSTRAINT IF EXISTS ck_attendance_not_future")
        op.execute("""
            ALTER TABLE attendance_logs
            ADD CONSTRAINT ck_attendance_not_future
            CHECK (date <= CURRENT_DATE)
        """)

        # 2. children
        op.execute("ALTER TABLE children DROP CONSTRAINT IF EXISTS ck_children_dob_not_future")
        op.execute("""
            ALTER TABLE children
            ADD CONSTRAINT ck_children_dob_not_future
            CHECK (date_of_birth <= CURRENT_DATE)
        """)

        # 3. incidents
        op.execute("ALTER TABLE incidents DROP CONSTRAINT IF EXISTS ck_incident_not_future")
        op.execute("""
            ALTER TABLE incidents
            ADD CONSTRAINT ck_incident_not_future
            CHECK (DATE(occurred_at) <= CURRENT_DATE)
        """)
