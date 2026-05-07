"""Materialized view mv_development_dashboard for Ministry of Development KPIs.

Revision ID: a9b8c7d6e5f4
Revises: d2e3f4a5b6c7
Create Date: 2026-05-01 02:00:00.000000

The materialized view aggregates national KPIs once per day via:
  REFRESH MATERIALIZED VIEW CONCURRENTLY mv_development_dashboard

APScheduler configuration (in main.py lifespan):
    from government_api import refresh_development_dashboard
    scheduler.add_job(refresh_development_dashboard, "cron", hour=3, minute=0,
                      id="refresh_dev_dashboard")

pg_cron alternative (requires pg_cron extension):
    SELECT cron.schedule(
        'refresh-dev-dashboard',
        '0 3 * * *',
        $$ REFRESH MATERIALIZED VIEW CONCURRENTLY mv_development_dashboard $$
    );

Note: SQLite (test) databases skip both CREATE and DROP — all DDL is guarded by
a dialect check so that `alembic upgrade head` succeeds in all environments.
"""
from typing import Union

from alembic import op
from sqlalchemy import text

revision: str = "a9b8c7d6e5f4"
down_revision: Union[str, None] = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect != "postgresql":
        # SQLite and other non-PostgreSQL databases do not support materialized
        # views. Skip gracefully so that tests can run `alembic upgrade head`.
        return

    # Create a unique index support column so CONCURRENTLY refresh works.
    # The view is created WITH NO DATA and populated on the first daily refresh.
    bind.execute(text("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS mv_development_dashboard AS
        SELECT
            (SELECT COUNT(*) FROM kindergartens WHERE status = 'ACTIVE')
                                                        AS total_nurseries,
            (SELECT COUNT(*) FROM children WHERE deleted_at IS NULL)
                                                        AS total_children,
            ROUND(
                100.0 * (
                    SELECT COUNT(*)
                    FROM attendance_logs al2
                    WHERE al2.date BETWEEN CURRENT_DATE - 30 AND CURRENT_DATE
                      AND al2.deleted_at IS NULL
                )::numeric / NULLIF((
                    SELECT SUM(expected_child_days)
                    FROM (
                        SELECT
                            COUNT(DISTINCT ea2.child_id) *
                            (
                                SELECT COUNT(*)
                                FROM operating_calendar oc2
                                WHERE oc2.is_open = TRUE
                                  AND oc2.date BETWEEN CURRENT_DATE - 30 AND CURRENT_DATE
                                  AND oc2.kindergarten_id = ea2.kindergarten_id
                            ) AS expected_child_days
                        FROM enrollment_applications ea2
                        WHERE ea2.status IN ('ACTIVE', 'ACCEPTED')
                          AND ea2.deleted_at IS NULL
                        GROUP BY ea2.kindergarten_id
                    ) expected_attendance
                ), 0), 1
            )                                           AS avg_attendance_pct,
            (
                SELECT json_agg(t ORDER BY t.week_start)
                FROM (
                    SELECT
                        DATE_TRUNC('week', occurred_at)::date AS week_start,
                        COUNT(*)                              AS incident_count
                    FROM incidents
                    WHERE occurred_at >= CURRENT_DATE - 56
                      AND deleted_at IS NULL
                    GROUP BY DATE_TRUNC('week', occurred_at)
                ) t
            )                                           AS incident_trend,
            (
                SELECT json_agg(d ORDER BY d.enrolled_children DESC)
                FROM (
                    SELECT
                        k.area,
                        k.governorate,
                        COUNT(DISTINCT k.id)         AS nursery_count,
                        COUNT(DISTINCT ea.child_id)  AS enrolled_children,
                        ROUND(
                            COUNT(DISTINCT ea.child_id)::numeric
                            / NULLIF(COUNT(DISTINCT k.id), 0), 1
                        )                            AS children_per_nursery
                    FROM kindergartens k
                    LEFT JOIN enrollment_applications ea
                           ON ea.kindergarten_id = k.id
                          AND ea.status IN ('ACTIVE', 'ACCEPTED')
                          AND ea.deleted_at IS NULL
                    WHERE k.status = 'ACTIVE'
                    GROUP BY k.area, k.governorate
                    ORDER BY enrolled_children DESC
                    LIMIT 5
                ) d
            )                                           AS top5_density_areas,
            NOW()                                       AS refreshed_at
        WITH NO DATA
    """))

    # A unique index is required for CONCURRENTLY refresh (PostgreSQL requirement).
    # We use a single-row view so we create a partial index on a constant expression.
    bind.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uidx_mv_development_dashboard_singleton
        ON mv_development_dashboard ((refreshed_at IS NOT NULL))
    """))


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect != "postgresql":
        return

    bind.execute(text(
        "DROP INDEX IF EXISTS uidx_mv_development_dashboard_singleton"
    ))
    bind.execute(text(
        "DROP MATERIALIZED VIEW IF EXISTS mv_development_dashboard"
    ))
