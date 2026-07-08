"""kpi_p0_performance_indexes

Revision ID: kpi_p0_idx_001
Revises: (previous migration ID — update before merging)
Create Date: 2026-06-24

No schema changes are required for the six P0 KPI fixes.
This migration adds performance indexes that make the P0 query patterns
efficient at production data volumes.

All indexes are created with IF NOT EXISTS / try-except, so this
migration is safe to run on databases that already have partial indexes.
"""

from alembic import op
from sqlalchemy import inspect


revision = "kpi_p0_idx_001"
down_revision = "b2c3d4e5f6a8"
branch_labels = None
depends_on = None

_INDEXES = [
    # attendance_logs: used by every KPI bundle and bulk builder
    (
        "ix_attendance_kg_date_status",
        "attendance_logs",
        "kindergarten_id, date, status",
    ),
    # incidents: used by incident_rate, followup_sla, hard override check
    (
        "ix_incidents_kg_occurred_followup",
        "incidents",
        "kindergarten_id, occurred_at, followup_required_flag, followup_sla_deadline",
    ),
    # staff_training_completion: all three training completion query paths
    (
        "ix_staff_training_kg_user_module_date",
        "staff_training_completion",
        "kindergarten_id, user_id, training_module_id, completion_date",
    ),
    # training_modules: denominator query filters on is_mandatory
    (
        "ix_training_modules_mandatory",
        "training_modules",
        "is_mandatory",
    ),
    # ratio_compliance: ratio bundle query
    (
        "ix_ratio_compliance_kg_date",
        "ratio_compliance",
        "kindergarten_id, date",
    ),
    # kindergartens: hard override license check and regulatory_status
    (
        "ix_kindergartens_license_valid_until",
        "kindergartens",
        "license_valid_until",
    ),
    # enrollment_applications: capacity utilization and overcapacity override
    (
        "ix_enrollment_kg_status",
        "enrollment_applications",
        "kindergarten_id, status",
    ),
    # daily_checklists: checklist compliance bundle query
    (
        "ix_daily_checklists_kg_date_type_status",
        "daily_checklists",
        "kindergarten_id, checklist_date, checklist_type, status",
    ),
    # daily_reports: report submission rate bundle query
    (
        "ix_daily_reports_kg_date_child_status",
        "daily_reports",
        "kindergarten_id, date, child_id, status",
    ),
]


def upgrade():
    # Only create an index when its table and every indexed column actually
    # exist in the live schema. On PostgreSQL a single failing DDL statement
    # (e.g. an index on a column that isn't present) aborts the whole
    # migration transaction, so a bare try/except cannot recover — every
    # later statement, including Alembic's own version stamp, then fails with
    # "current transaction is aborted". Pre-checking with the inspector keeps
    # this migration safe and idempotent across PostgreSQL and SQLite.
    #
    # Notably attendance_logs has no kindergarten_id column (attendance is
    # scoped via class_id -> class -> kindergarten), so its intended index is
    # skipped rather than crashing the upgrade.
    inspector = inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())

    for index_name, table_name, columns in _INDEXES:
        if table_name not in existing_tables:
            continue
        table_columns = {col["name"] for col in inspector.get_columns(table_name)}
        required_columns = [c.strip() for c in columns.split(",")]
        if not all(col in table_columns for col in required_columns):
            continue
        op.execute(
            f"CREATE INDEX IF NOT EXISTS {index_name} "
            f"ON {table_name} ({columns})"
        )


def downgrade():
    for index_name, _, _ in _INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {index_name}")
