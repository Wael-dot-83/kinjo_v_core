"""Jordan Heat Map — daily snapshot tables.

Revision ID: h1m2026h01
Revises: d2e3f4a5b6c7
Create Date: 2026-06-13 23:00:00.000000

Adds the seven tables required by the Jordan Heat Map feature, per
docs/JORDAN_HEAT_MAP_TECHNICAL_SPECIFICATION.md §4:

  * map_indicator_snapshot     — one row per (date, gov, main_indicator)
  * map_sub_indicator_value   — one row per (date, gov, sub_indicator)
  * map_correlation_snapshot  — Pearson / Spearman / Kendall τ-b matrix
  * map_regression_snapshot   — standardized OLS coefficients + VIF
  * map_risk_snapshot         — composite risk score + level + drivers
  * map_alert_history         — append-only alert ledger
  * map_daily_run_log         — ETL pipeline run audit
  * governorate               — 12 Jordan governorates (normalized seed data)

Differences from the SQL script in
`heatmap/scripts/init_map_snapshot_schema.sql`:
  - Alembic-managed (revision, down_revision, upgrade, downgrade)
  - Dialect-aware types where possible
  - Reversible downgrade()
"""
from alembic import op
import sqlalchemy as sa

revision = "h1m2026h01"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    # 1. Indicator snapshot
    op.create_table(
        "map_indicator_snapshot",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False, index=True),
        sa.Column("governorate_code", sa.String(length=8), nullable=False, index=True),
        sa.Column("main_indicator", sa.String(length=40), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("previous_value", sa.Float(), nullable=True),
        sa.Column("trend_pct", sa.Float(), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("snapshot_date", "governorate_code", "main_indicator", name="uq_mis"),
        sa.CheckConstraint("value BETWEEN 0 AND 100", name="ck_mis_value_range"),
    )
    op.create_index("idx_mis_latest", "map_indicator_snapshot", ["snapshot_date", "governorate_code"])
    op.create_index("idx_mis_history", "map_indicator_snapshot", ["governorate_code", "main_indicator", "snapshot_date"])

    # 2. Sub-indicator value
    op.create_table(
        "map_sub_indicator_value",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False, index=True),
        sa.Column("governorate_code", sa.String(length=8), nullable=False, index=True),
        sa.Column("sub_indicator", sa.String(length=40), nullable=False),
        sa.Column("raw_value", sa.Float(), nullable=False),
        sa.Column("threshold_high", sa.Float(), nullable=True),
        sa.Column("threshold_low", sa.Float(), nullable=True),
        sa.Column("above_threshold", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("snapshot_date", "governorate_code", "sub_indicator", name="uq_ssiv"),
    )
    op.create_index("idx_ssiv_gov", "map_sub_indicator_value", ["snapshot_date", "governorate_code"])

    # 3. Correlation snapshot
    op.create_table(
        "map_correlation_snapshot",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False, index=True),
        sa.Column("main_indicator", sa.String(length=40), nullable=False),
        sa.Column("sub_indicator", sa.String(length=40), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("coefficient", sa.Float(), nullable=True),
        sa.Column("p_value", sa.Float(), nullable=True),
        sa.Column("n_samples", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("strength", sa.String(length=15), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("snapshot_date", "main_indicator", "sub_indicator", "method", name="uq_corr"),
    )
    op.create_index("idx_corr_latest", "map_correlation_snapshot", ["snapshot_date"])
    op.create_index("idx_corr_pair", "map_correlation_snapshot", ["main_indicator", "sub_indicator", "snapshot_date"])

    # 4. Regression snapshot
    op.create_table(
        "map_regression_snapshot",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False, index=True),
        sa.Column("main_indicator", sa.String(length=40), nullable=False),
        sa.Column("sub_indicator", sa.String(length=40), nullable=False),
        sa.Column("beta_std", sa.Float(), nullable=False),
        sa.Column("std_error", sa.Float(), nullable=True),
        sa.Column("t_stat", sa.Float(), nullable=True),
        sa.Column("p_value", sa.Float(), nullable=True),
        sa.Column("r_squared", sa.Float(), nullable=True),
        sa.Column("adj_r_squared", sa.Float(), nullable=True),
        sa.Column("high_impact", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("vif", sa.Float(), nullable=True),
        sa.Column("vif_flag", sa.String(length=10), nullable=False, server_default="ok"),
        sa.Column("n_samples", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ridge_used", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("fit_warning", sa.String(length=40), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("snapshot_date", "main_indicator", "sub_indicator", name="uq_reg"),
    )
    op.create_index("idx_reg_latest", "map_regression_snapshot", ["snapshot_date"])
    op.create_index("idx_reg_main", "map_regression_snapshot", ["main_indicator", "snapshot_date"])

    # 5. Risk snapshot
    op.create_table(
        "map_risk_snapshot",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False, index=True),
        sa.Column("governorate_code", sa.String(length=8), nullable=False, index=True),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("risk_level", sa.String(length=10), nullable=False),
        sa.Column("top_driver_sub", sa.String(length=40), nullable=True),
        sa.Column("top_driver_beta", sa.Float(), nullable=True),
        sa.Column("trend_pct", sa.Float(), nullable=True),
        sa.Column("contributing_subs", sa.JSON(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("snapshot_date", "governorate_code", name="uq_risk"),
        sa.CheckConstraint("risk_score BETWEEN 0 AND 100", name="ck_risk_range"),
        sa.CheckConstraint(
            "risk_level IN ('low','medium','high','critical')", name="ck_risk_level"
        ),
    )
    op.create_index("idx_risk_latest", "map_risk_snapshot", ["snapshot_date"])

    # 6. Alert history
    op.create_table(
        "map_alert_history",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False, index=True),
        sa.Column("governorate_code", sa.String(length=8), nullable=True, index=True),
        sa.Column("sub_indicator", sa.String(length=40), nullable=False, index=True),
        sa.Column("rule", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("current_value", sa.Float(), nullable=True),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.UniqueConstraint("snapshot_date", "governorate_code", "sub_indicator", "rule", name="uq_alert"),
        sa.CheckConstraint(
            "severity IN ('low','medium','high','critical')", name="ck_alert_severity"
        ),
    )
    op.create_index("idx_alert_gov", "map_alert_history", ["governorate_code", "snapshot_date"])

    # 7. Daily run log
    op.create_table(
        "map_daily_run_log",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("run_id", sa.String(length=36), nullable=False, unique=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("rows_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("governorates", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "status IN ('running','success','failed','partial')", name="ck_run_status"
        ),
    )

    # 8. Governorate (12 Jordan governorates)
    op.create_table(
        "governorate",
        sa.Column("code", sa.String(length=8), primary_key=True),
        sa.Column("slug", sa.String(length=20), nullable=False, unique=True, index=True),
        sa.Column("name_en", sa.String(length=40), nullable=False),
        sa.Column("name_ar", sa.String(length=40), nullable=False),
        sa.Column("center_lon", sa.Float(), nullable=False),
        sa.Column("center_lat", sa.Float(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

    # Seed the 12 governorates
    governorates = [
        ("JO-AM", "amman",   "Amman",   "عمان",     35.95, 31.95,  1),
        ("JO-IR", "irbid",   "Irbid",   "إربد",     35.85, 32.55,  2),
        ("JO-ZA", "zarqa",   "Zarqa",   "الزرقاء",  36.10, 32.07,  3),
        ("JO-MA", "mafraq",  "Mafraq",  "المفرق",   36.20, 32.34,  4),
        ("JO-JA", "jerash",  "Jerash",  "جرش",     35.90, 32.28,  5),
        ("JO-AJ", "ajloun",  "Ajloun",  "عجلون",   35.75, 32.33,  6),
        ("JO-BA", "balqa",   "Balqa",   "البلقاء",  35.78, 32.04,  7),
        ("JO-MD", "madaba",  "Madaba",  "مادبا",   35.79, 31.72,  8),
        ("JO-KA", "karak",   "Karak",   "الكرك",   35.70, 31.18,  9),
        ("JO-TA", "tafileh", "Tafileh", "الطفيلة",  35.60, 30.83, 10),
        ("JO-MN", "maan",    "Ma'an",   "معان",     35.73, 30.20, 11),
        ("JO-AQ", "aqaba",   "Aqaba",   "العقبة",  35.00, 29.53, 12),
    ]
    for code, slug, name_en, name_ar, lon, lat, order in governorates:
        op.execute(
            sa.text(
                "INSERT INTO governorate (code, slug, name_en, name_ar, center_lon, center_lat, display_order) "
                "VALUES (:code, :slug, :name_en, :name_ar, :lon, :lat, :order) "
                "ON CONFLICT (code) DO UPDATE SET "
                "  slug = EXCLUDED.slug, name_en = EXCLUDED.name_en, name_ar = EXCLUDED.name_ar, "
                "  center_lon = EXCLUDED.center_lon, center_lat = EXCLUDED.center_lat, "
                "  display_order = EXCLUDED.display_order"
            ).bindparams(
                code=code, slug=slug, name_en=name_en, name_ar=name_ar, lon=lon, lat=lat, order=order
            )
        )


def downgrade() -> None:
    op.drop_table("map_daily_run_log")
    op.drop_table("map_alert_history")
    op.drop_table("map_risk_snapshot")
    op.drop_table("map_regression_snapshot")
    op.drop_table("map_correlation_snapshot")
    op.drop_table("map_sub_indicator_value")
    op.drop_table("map_indicator_snapshot")
    op.drop_table("governorate")
