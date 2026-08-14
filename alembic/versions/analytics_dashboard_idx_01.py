"""analytics dashboard indexes: class-scoped daily reports, attendance status,
child drill-down on incidents, and child demographic faceting.

Adds the composite indexes the new /reports/analytics filter bar needs for
fast multi-dimensional aggregation without table rewrites or downtime.

Revision ID: analytics_dashboard_idx_01
Revises: sched_chart_exports_01
Create Date: 2026-08-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "analytics_dashboard_idx_01"
down_revision: Union[str, None] = "sched_chart_exports_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_sqlite() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "sqlite"


def upgrade() -> None:
    # DailyReport: class-scoped analytics (the dashboard drill-down filters on
    # class_id + date; without this composite the planner falls back to the
    # single-column FK index then filters date row-by-row).
    op.create_index(
        "ix_daily_reports_class_date",
        "daily_reports",
        ["class_id", "date"],
        if_not_exists=True,
    )

    # DailyReport: mood faceting (health-flag and mood-trend queries filter on
    # mood alone; the free-text column has no index today).
    op.create_index(
        "ix_daily_reports_mood",
        "daily_reports",
        ["mood"],
        if_not_exists=True,
    )

    # AttendanceLog: date + status aggregation (attendance_series counts
    # present/total per day; the existing leading-child_id indexes are useless
    # when the query is scoped by date+status across all children).
    op.create_index(
        "ix_attendance_date_status",
        "attendance_logs",
        ["date", "status"],
        if_not_exists=True,
    )

    # Incident: child drill-down (the child detail drawer needs
    # child_id + occurred_at; existing indexes are kg-led).
    op.create_index(
        "ix_incidents_child_occurred",
        "incidents",
        ["child_id", "occurred_at"],
        if_not_exists=True,
    )

    # Child: demographic faceting (filter by gender + age band requires the
    # composite; the single-column dob index already exists).
    op.create_index(
        "ix_children_gender_dob",
        "children",
        ["gender", "date_of_birth"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_children_gender_dob", table_name="children", if_exists=True)
    op.drop_index("ix_incidents_child_occurred", table_name="incidents", if_exists=True)
    op.drop_index("ix_attendance_date_status", table_name="attendance_logs", if_exists=True)
    op.drop_index("ix_daily_reports_mood", table_name="daily_reports", if_exists=True)
    op.drop_index("ix_daily_reports_class_date", table_name="daily_reports", if_exists=True)
