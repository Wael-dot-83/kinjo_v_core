"""Agency report snapshots and unified metric cache.

Revision ID: ncfa_snap_01
Revises: ea7ba800f0d5
Create Date: 2026-08-14 09:02:00.000000

Adds two tables:

  * agency_report_snapshots — nightly materialized aggregations for agency
    reports, so report loads query pre-computed rows instead of re-joining raw
    tables on every request.

  * unified_metric_cache — a single cache table replacing the three scattered
    overlapping cache tables (advanced_analytics_cache, analytics_dimension_cache,
    kpi_snapshots) with one keyed store that supports cross-invalidation.
"""
from alembic import op
import sqlalchemy as sa

revision = "ncfa_snap_01"
down_revision = "ea7ba800f0d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    json_type = sa.dialects.postgresql.JSONB if is_pg else sa.JSON()

    # 1. agency_report_snapshots
    op.create_table(
        "agency_report_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("agency_code", sa.String(length=20), nullable=False, index=True),
        sa.Column("report_code", sa.String(length=60), nullable=False, index=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False, index=True),
        sa.Column("governorate", sa.String(length=100), nullable=True),
        sa.Column("district", sa.String(length=100), nullable=True),
        sa.Column("gender", sa.String(length=10), nullable=True),
        sa.Column("age_group", sa.String(length=20), nullable=True),
        sa.Column("metric_key", sa.String(length=80), nullable=False),
        sa.Column("metric_value", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("dimension", json_type, server_default="{}"),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "agency_code", "report_code", "snapshot_date",
            "governorate", "district", "gender", "age_group", "metric_key",
            name="uq_agency_report_snapshot",
        ),
    )
    op.create_index(
        "ix_snapshots_agency_report_date",
        "agency_report_snapshots",
        ["agency_code", "report_code", "snapshot_date"],
    )

    # 2. unified_metric_cache
    op.create_table(
        "unified_metric_cache",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("cache_key", sa.String(length=255), nullable=False, unique=True, index=True),
        sa.Column("metric_namespace", sa.String(length=60), nullable=False, index=True),
        sa.Column("agency_code", sa.String(length=20), nullable=True),
        sa.Column("report_code", sa.String(length=60), nullable=True),
        sa.Column("payload", json_type, nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_unified_cache_namespace_agency",
        "unified_metric_cache",
        ["metric_namespace", "agency_code", "report_code"],
    )

    # 3. snapshot_metadata — tracks freshness of each (agency, report) snapshot
    op.create_table(
        "snapshot_metadata",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("agency_code", sa.String(length=20), nullable=False, index=True),
        sa.Column("report_code", sa.String(length=60), nullable=False, index=True),
        sa.Column("last_computed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("snapshot_date", sa.Date(), nullable=True),
        sa.UniqueConstraint("agency_code", "report_code", name="uq_snapshot_metadata"),
    )


def downgrade() -> None:
    op.drop_table("snapshot_metadata")
    op.drop_index("ix_unified_cache_namespace_agency", table_name="unified_metric_cache")
    op.drop_table("unified_metric_cache")
    op.drop_index("ix_snapshots_agency_report_date", table_name="agency_report_snapshots")
    op.drop_table("agency_report_snapshots")
