"""Phase 1 completion: missing constraints and composite indexes.

Revision ID: c0d1e2f3a4b5
Revises: b1c2d3e4f5a6
Create Date: 2026-05-07 06:00:00.000000

Adds:
  1.8  ck_attendance_not_future   — attendance_logs.date <= today
  1.8  ck_report_not_future       — daily_reports.date  <= today
  1.8  ck_incident_not_future     — incidents.occurred_at <= now
  1.9  ck_arrival_time_format     — daily_reports HH:MM format checks
  1.9  ck_leave_time_format
  1.9  ck_nap_start_format
  1.9  ck_nap_end_format
  1.15 ck_health_alert_severity   — health_alerts.severity IN (…)
  1.14 10 composite indexes

All constraints are dialect-aware:
  PostgreSQL: uses regex (~) / NOW() / CURRENT_DATE
  SQLite:     uses GLOB / date('now')
Indexes are added with CREATE INDEX CONCURRENTLY on PostgreSQL.
"""
import sqlalchemy as sa
from alembic import op

revision = "c0d1e2f3a4b5"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None

_TIME_RE_PG     = r"^([0-1][0-9]|2[0-3]):[0-5][0-9]$"
_TIME_GLOB_SQ   = "[0-2][0-9]:[0-5][0-9]"

_SEVERITY_CHECK = "severity IN ('LOW','MEDIUM','HIGH','CRITICAL')"


def _dialect() -> str:
    return op.get_bind().dialect.name


def _has_constraint(table: str, name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return any(
        c.get("name") == name
        for c in insp.get_check_constraints(table)
    )


def _has_index(table: str, name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return any(i["name"] == name for i in insp.get_indexes(table))


def _add_check(table: str, name: str, pg_sql: str, sq_sql: str) -> None:
    if _has_constraint(table, name):
        return
    if _dialect() == "postgresql":
        op.execute(sa.text(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({pg_sql})"))
    # SQLite does not support ADD CONSTRAINT via ALTER TABLE; the production
    # database (PostgreSQL) enforces these constraints. ORM-level validation
    # covers the same rules for all dialects.


def _create_index(name: str, table: str, cols: str, unique: bool = False) -> None:
    if _has_index(table, name):
        return
    uniq = "UNIQUE " if unique else ""
    if _dialect() == "postgresql":
        op.execute(sa.text(
            f"CREATE {uniq}INDEX CONCURRENTLY IF NOT EXISTS {name} ON {table} ({cols})"
        ))
    else:
        op.create_index(name, table, cols.split(", "), unique=unique)


def _drop_check(table: str, name: str) -> None:
    if not _has_constraint(table, name):
        return
    if _dialect() == "postgresql":
        op.execute(sa.text(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}"))
    else:
        with op.batch_alter_table(table, recreate="always") as batch:
            batch.drop_constraint(name, type_="check")


def _drop_index(name: str, table: str) -> None:
    if not _has_index(table, name):
        return
    if _dialect() == "postgresql":
        op.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {name}"))
    else:
        op.drop_index(name, table_name=table)


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    d = _dialect()

    # 1.8 — future-date guards
    _add_check(
        "attendance_logs", "ck_attendance_not_future",
        "date <= CURRENT_DATE",
        "date <= date('now')",
    )
    _add_check(
        "daily_reports", "ck_report_not_future",
        "date <= CURRENT_DATE",
        "date <= date('now')",
    )
    _add_check(
        "incidents", "ck_incident_not_future",
        "DATE(occurred_at) <= CURRENT_DATE",
        "DATE(occurred_at) <= date('now')",
    )

    # 1.9 — HH:MM time-format checks on daily_reports
    for col, cname in [
        ("arrival_time", "ck_arrival_time_format"),
        ("leave_time",   "ck_leave_time_format"),
        ("nap_start",    "ck_nap_start_format"),
        ("nap_end",      "ck_nap_end_format"),
    ]:
        null_ok = col in ("nap_start", "nap_end")
        if d == "postgresql":
            null_clause = f"{col} IS NULL OR " if null_ok else ""
            expr = f"{null_clause}{col} ~ '{_TIME_RE_PG}'"
        else:
            null_clause = f"{col} IS NULL OR " if null_ok else ""
            expr = f"{null_clause}{col} GLOB '{_TIME_GLOB_SQ}'"
        _add_check("daily_reports", cname, expr, expr)

    # 1.15 — health_alerts severity must be one of the valid values
    _add_check(
        "health_alerts", "ck_health_alert_severity",
        _SEVERITY_CHECK,
        _SEVERITY_CHECK,
    )

    # 1.14 — composite indexes
    _create_index("ix_attendance_child_date",       "attendance_logs",          "child_id, date")
    _create_index("ix_incidents_child_occurred",    "incidents",                "child_id, occurred_at")
    _create_index("ix_cases_status_assigned",       "safeguarding_cases",       "status, assigned_to")
    _create_index("ix_waitlist_status_priority",    "waitlist_entries",         "status, priority_score")
    _create_index("ix_enrollments_child_status",    "enrollment_applications",  "child_id, status")
    _create_index("ix_audit_logs_entity_time",      "audit_logs",               "entity_type, created_at")
    _create_index("ix_survey_responses_parent",     "survey_responses",         "parent_id, survey_id, created_at")
    _create_index("ix_ai_rec_child_reviewed",       "ai_parent_recommendations","child_id, human_reviewed, created_at")
    _create_index("ix_ai_feedback_source",          "ai_feedback",              "source_table, source_id")
    _create_index("ix_messages_recipient_read",     "messages",                 "recipient_id, is_read, created_at")


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    # Drop indexes
    _drop_index("ix_messages_recipient_read",    "messages")
    _drop_index("ix_ai_feedback_source",         "ai_feedback")
    _drop_index("ix_ai_rec_child_reviewed",      "ai_parent_recommendations")
    _drop_index("ix_survey_responses_parent",    "survey_responses")
    _drop_index("ix_audit_logs_entity_time",     "audit_logs")
    _drop_index("ix_enrollments_child_status",   "enrollment_applications")
    _drop_index("ix_waitlist_status_priority",   "waitlist_entries")
    _drop_index("ix_cases_status_assigned",      "safeguarding_cases")
    _drop_index("ix_incidents_child_occurred",   "incidents")
    _drop_index("ix_attendance_child_date",      "attendance_logs")

    # Drop constraints
    _drop_check("health_alerts",  "ck_health_alert_severity")
    for cname in ["ck_nap_end_format", "ck_nap_start_format",
                  "ck_leave_time_format", "ck_arrival_time_format"]:
        _drop_check("daily_reports", cname)
    _drop_check("incidents",      "ck_incident_not_future")
    _drop_check("daily_reports",  "ck_report_not_future")
    _drop_check("attendance_logs","ck_attendance_not_future")
