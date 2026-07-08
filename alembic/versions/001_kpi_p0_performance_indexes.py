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


revision = "kpi_p0_idx_001"
down_revision = "b2c3d4e5f6a8"
branch_labels = None
depends_on = None

_INDEXES = [
    # attendance_logs: used by every KPI bundle and bulk builder. The table has
    # no kindergarten_id (KPI queries reach it via child_id); index the columns
    # the queries actually filter on.
    (
        "ix_attendance_child_date_status",
        "attendance_logs",
        "child_id, date, status",
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


def _run_isolated(bind, sql):
    """Run a DDL statement inside a SAVEPOINT so a failure (e.g. an index on a
    column/table that isn't present in a given schema) is rolled back on its own
    without aborting the surrounding migration transaction. On Postgres a bare
    failed statement poisons the whole transaction, which defeats the
    best-effort try/except this migration relies on."""
    try:
        with bind.begin_nested():
            bind.exec_driver_sql(sql)
    except Exception:
        # Best-effort: index already exists, or its columns aren't present here.
        pass


def upgrade():
    bind = op.get_bind()
    for index_name, table_name, columns in _INDEXES:
        _run_isolated(
            bind,
            f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({columns})",
        )


def downgrade():
    bind = op.get_bind()
    for index_name, _, _ in _INDEXES:
        _run_isolated(bind, f"DROP INDEX IF EXISTS {index_name}")
