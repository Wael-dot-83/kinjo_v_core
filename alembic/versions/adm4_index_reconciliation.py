"""ADMIN-PERF-001 / #97: reconcile divergent indexes and add the 3c composites

Two jobs.

1. Reconcile the three index definitions where models.py and the migration
   chain disagreed (#97). Because the test suite builds its schema with
   Base.metadata.create_all and production builds it with Alembic, each
   disagreement meant tests and production ran different indexes.

2. Add the three composite indexes Phase 3c needs, declared in models.py
   __table_args__ as well as here. Double declaration is deliberate and stays
   until #97's schema-source split is closed.

Revision ID: adm4_index_recon_01
Revises: adm3_imp_session_01
Create Date: 2026-08-20 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "adm4_index_recon_01"
down_revision: Union[str, None] = "adm3_imp_session_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_index(table: str, name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    try:
        return any(ix.get("name") == name for ix in insp.get_indexes(table))
    except Exception:
        return False


def _has_table(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    # ── 1. kindergartens: rename, do not recreate ────────────────────────────
    # The chain created idx_kindergartens_governorate_city on a column then
    # named "city". That column was later renamed to "district"; PostgreSQL
    # carried the rename into the index definition but not into its name, so
    # production has an index called "..._city" over (governorate, district).
    # models.py calls it "..._district", which is the honest name. Rename in
    # place -- dropping and recreating would rebuild the index for nothing.
    if _has_index("kindergartens", "idx_kindergartens_governorate_city"):
        if is_pg:
            op.execute(
                "ALTER INDEX idx_kindergartens_governorate_city "
                "RENAME TO idx_kindergartens_governorate_district"
            )
        else:
            op.drop_index("idx_kindergartens_governorate_city", table_name="kindergartens")
    if not _has_index("kindergartens", "idx_kindergartens_governorate_district"):
        op.create_index(
            "idx_kindergartens_governorate_district",
            "kindergartens",
            ["governorate", "district"],
        )

    # ── 2. incidents: drop the models-only ASC twin ──────────────────────────
    # idx_incidents_kg_occurred (DESC) is canonical and already exists in
    # production. ix_incidents_kg_occurred_at only ever existed in create_all
    # databases, so this drop is a no-op on production and cleans up test DBs
    # built before the models.py change.
    if _has_index("incidents", "ix_incidents_kg_occurred_at"):
        op.drop_index("ix_incidents_kg_occurred_at", table_name="incidents")
    if not _has_index("incidents", "idx_incidents_kg_occurred"):
        if is_pg:
            op.execute(
                "CREATE INDEX idx_incidents_kg_occurred "
                "ON incidents (kindergarten_id, occurred_at DESC)"
            )
        else:
            op.create_index(
                "idx_incidents_kg_occurred", "incidents", ["kindergarten_id", "occurred_at"]
            )

    # ── 3. daily_reports: drop the models-only three-column twin ─────────────
    if _has_index("daily_reports", "ix_daily_reports_kg_date_status"):
        op.drop_index("ix_daily_reports_kg_date_status", table_name="daily_reports")
    if not _has_index("daily_reports", "ix_daily_reports_kg_date_child_status"):
        op.create_index(
            "ix_daily_reports_kg_date_child_status",
            "daily_reports",
            ["kindergarten_id", "date", "child_id", "status"],
        )

    # ── 4. Phase 3c composites ───────────────────────────────────────────────
    # enrollment_applications: scope first, then status. The specification
    # ordered this (status, kindergarten_id, class_id); status has a handful of
    # values and most rows are ACTIVE, so leading with it prunes almost
    # nothing, while the kindergarten set is what the admin scope resolves to.
    if not _has_index("enrollment_applications", "ix_enrollment_kg_status_class"):
        op.create_index(
            "ix_enrollment_kg_status_class",
            "enrollment_applications",
            ["kindergarten_id", "status", "class_id"],
        )

    # daily_reports: recency probes read newest-first within a kindergarten set.
    if not _has_index("daily_reports", "ix_daily_reports_kg_date_desc"):
        if is_pg:
            op.execute(
                "CREATE INDEX ix_daily_reports_kg_date_desc "
                "ON daily_reports (kindergarten_id, date DESC)"
            )
        else:
            op.create_index(
                "ix_daily_reports_kg_date_desc", "daily_reports", ["kindergarten_id", "date"]
            )

    # supervisor_assignments: active-assignment lookups.
    #
    # The specification wrote the predicate as
    #   WHERE deleted_at IS NULL AND (end_date IS NULL OR end_date >= CURRENT_DATE)
    # PostgreSQL rejects that: index predicates must be IMMUTABLE and
    # CURRENT_DATE is STABLE ("functions in index predicate must be marked
    # IMMUTABLE"). The date test moves out of the predicate and end_date
    # becomes a trailing column, so the planner still serves it from the index.
    if _has_table("supervisor_assignments") and not _has_index(
        "supervisor_assignments", "ix_supervisor_assignments_active_lookup"
    ):
        op.create_index(
            "ix_supervisor_assignments_active_lookup",
            "supervisor_assignments",
            ["class_id", "supervisor_id", "end_date"],
            postgresql_where=sa.text("deleted_at IS NULL"),
            sqlite_where=sa.text("deleted_at IS NULL"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    for table, name in (
        ("supervisor_assignments", "ix_supervisor_assignments_active_lookup"),
        ("daily_reports", "ix_daily_reports_kg_date_desc"),
        ("enrollment_applications", "ix_enrollment_kg_status_class"),
    ):
        if _has_index(table, name):
            op.drop_index(name, table_name=table)

    # Restore the pre-reconciliation names so downgrade is a real inverse.
    if _has_index("daily_reports", "ix_daily_reports_kg_date_child_status"):
        op.drop_index("ix_daily_reports_kg_date_child_status", table_name="daily_reports")
        op.create_index(
            "ix_daily_reports_kg_date_status",
            "daily_reports",
            ["kindergarten_id", "date", "status"],
        )

    if _has_index("incidents", "idx_incidents_kg_occurred"):
        op.drop_index("idx_incidents_kg_occurred", table_name="incidents")
        op.create_index(
            "ix_incidents_kg_occurred_at", "incidents", ["kindergarten_id", "occurred_at"]
        )

    if _has_index("kindergartens", "idx_kindergartens_governorate_district"):
        if is_pg:
            op.execute(
                "ALTER INDEX idx_kindergartens_governorate_district "
                "RENAME TO idx_kindergartens_governorate_city"
            )
        else:
            op.drop_index("idx_kindergartens_governorate_district", table_name="kindergartens")
            op.create_index(
                "idx_kindergartens_governorate_city",
                "kindergartens",
                ["governorate", "district"],
            )
