"""Add analytics enhancements tables.

Revision ID: 20260206_add_analytics_enhancements
Revises: 20260206_add_child_age_constraints
Create Date: 2026-02-06
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260206_add_analytics_enhancements"
down_revision = "20260206_add_child_age_constraints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "predictive_models",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("metric_type", sa.String(length=100), nullable=False),
        sa.Column("scope_type", sa.String(length=50), nullable=False),
        sa.Column("scope_id", sa.String(length=100), nullable=True),
        sa.Column("model_version", sa.String(length=50), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("training_start", sa.Date(), nullable=True),
        sa.Column("training_end", sa.Date(), nullable=True),
        sa.Column("parameters", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_predictive_models_metric_scope", "predictive_models", ["metric_type", "scope_type", "scope_id"], unique=False)
    op.create_index("ix_predictive_models_trained_at", "predictive_models", ["trained_at"], unique=False)

    op.create_table(
        "prediction_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("metric_type", sa.String(length=100), nullable=False),
        sa.Column("scope_type", sa.String(length=50), nullable=False),
        sa.Column("scope_id", sa.String(length=100), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("params_hash", sa.String(length=128), nullable=False),
        sa.Column("points", sa.JSON(), nullable=False),
        sa.Column("forecast_points", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.JSON(), nullable=False),
        sa.Column("model_meta", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prediction_cache_lookup", "prediction_cache", ["metric_type", "scope_type", "scope_id", "params_hash"], unique=True)
    op.create_index("ix_prediction_cache_created_at", "prediction_cache", ["created_at"], unique=False)

    op.create_table(
        "anomaly_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("metric_type", sa.String(length=100), nullable=False),
        sa.Column("scope_type", sa.String(length=50), nullable=False),
        sa.Column("scope_id", sa.String(length=100), nullable=True),
        sa.Column("detected_at", sa.Date(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("message", sa.String(length=255), nullable=False),
        sa.Column("is_acknowledged", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("acknowledged_by", sa.Integer(), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["acknowledged_by"], ["users.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_anomaly_alerts_metric_scope", "anomaly_alerts", ["metric_type", "scope_type", "scope_id"], unique=False)
    op.create_index("ix_anomaly_alerts_detected_at", "anomaly_alerts", ["detected_at"], unique=False)
    op.create_index("ix_anomaly_alerts_ack", "anomaly_alerts", ["is_acknowledged"], unique=False)

    op.create_table(
        "drilldown_paths",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("scope_type", sa.String(length=50), nullable=False),
        sa.Column("scope_id", sa.String(length=100), nullable=True),
        sa.Column("visited_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_drilldown_paths_user_ts", "drilldown_paths", ["user_id", "visited_at"], unique=False)

    op.create_table(
        "alert_thresholds",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("metric_type", sa.String(length=100), nullable=False),
        sa.Column("scope_type", sa.String(length=50), nullable=False),
        sa.Column("scope_id", sa.String(length=100), nullable=True),
        sa.Column("operator", sa.String(length=10), nullable=False),
        sa.Column("threshold_value", sa.Float(), nullable=False),
        sa.Column("window_days", sa.Integer(), nullable=False, server_default=sa.text("30")),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_thresholds_scope", "alert_thresholds", ["metric_type", "scope_type", "scope_id"], unique=False)
    op.create_index("ix_alert_thresholds_active", "alert_thresholds", ["is_active"], unique=False)

    op.create_table(
        "active_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("threshold_id", sa.Integer(), nullable=False),
        sa.Column("metric_type", sa.String(length=100), nullable=False),
        sa.Column("scope_type", sa.String(length=50), nullable=False),
        sa.Column("scope_id", sa.String(length=100), nullable=True),
        sa.Column("current_value", sa.Float(), nullable=False),
        sa.Column("message", sa.String(length=255), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_by", sa.Integer(), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["acknowledged_by"], ["users.id"], ),
        sa.ForeignKeyConstraint(["threshold_id"], ["alert_thresholds.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_active_alerts_status", "active_alerts", ["status"], unique=False)
    op.create_index("ix_active_alerts_scope", "active_alerts", ["metric_type", "scope_type", "scope_id"], unique=False)

    op.create_table(
        "performance_targets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("metric_type", sa.String(length=100), nullable=False),
        sa.Column("scope_type", sa.String(length=50), nullable=False),
        sa.Column("scope_id", sa.String(length=100), nullable=True),
        sa.Column("target_value", sa.Float(), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_performance_targets_lookup", "performance_targets", ["metric_type", "scope_type", "scope_id", "effective_date"], unique=False)

    op.create_table(
        "benchmark_data",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("metric_type", sa.String(length=100), nullable=False),
        sa.Column("scope_type", sa.String(length=50), nullable=False),
        sa.Column("scope_id", sa.String(length=100), nullable=True),
        sa.Column("comparison_group", sa.String(length=50), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_benchmark_data_scope", "benchmark_data", ["metric_type", "scope_type", "scope_id"], unique=False)
    op.create_index("ix_benchmark_data_period", "benchmark_data", ["period_start", "period_end"], unique=False)

    op.create_table(
        "recommendations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kindergarten_id", sa.Integer(), nullable=True),
        sa.Column("scope_type", sa.String(length=50), nullable=False),
        sa.Column("scope_id", sa.String(length=100), nullable=True),
        sa.Column("metric_type", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("recommended_actions", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ),
        sa.ForeignKeyConstraint(["kindergarten_id"], ["kindergartens.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recommendations_scope", "recommendations", ["scope_type", "scope_id"], unique=False)
    op.create_index("ix_recommendations_kindergarten", "recommendations", ["kindergarten_id"], unique=False)

    op.create_table(
        "action_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recommendation_id", sa.Integer(), nullable=True),
        sa.Column("kindergarten_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("assigned_to", sa.Integer(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["assigned_to"], ["users.id"], ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ),
        sa.ForeignKeyConstraint(["kindergarten_id"], ["kindergartens.id"], ),
        sa.ForeignKeyConstraint(["recommendation_id"], ["recommendations.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_action_plans_status", "action_plans", ["status"], unique=False)
    op.create_index("ix_action_plans_kindergarten", "action_plans", ["kindergarten_id"], unique=False)

    op.create_table(
        "data_quality_metrics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=True),
        sa.Column("completeness_percent", sa.Float(), nullable=False),
        sa.Column("accuracy_score", sa.Float(), nullable=False),
        sa.Column("timeliness_score", sa.Float(), nullable=False),
        sa.Column("consistency_score", sa.Float(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_data_quality_entity", "data_quality_metrics", ["entity_type", "entity_id"], unique=False)
    op.create_index("ix_data_quality_evaluated_at", "data_quality_metrics", ["evaluated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_data_quality_evaluated_at", table_name="data_quality_metrics")
    op.drop_index("ix_data_quality_entity", table_name="data_quality_metrics")
    op.drop_table("data_quality_metrics")

    op.drop_index("ix_action_plans_kindergarten", table_name="action_plans")
    op.drop_index("ix_action_plans_status", table_name="action_plans")
    op.drop_table("action_plans")

    op.drop_index("ix_recommendations_kindergarten", table_name="recommendations")
    op.drop_index("ix_recommendations_scope", table_name="recommendations")
    op.drop_table("recommendations")

    op.drop_index("ix_benchmark_data_period", table_name="benchmark_data")
    op.drop_index("ix_benchmark_data_scope", table_name="benchmark_data")
    op.drop_table("benchmark_data")

    op.drop_index("ix_performance_targets_lookup", table_name="performance_targets")
    op.drop_table("performance_targets")

    op.drop_index("ix_active_alerts_scope", table_name="active_alerts")
    op.drop_index("ix_active_alerts_status", table_name="active_alerts")
    op.drop_table("active_alerts")

    op.drop_index("ix_alert_thresholds_active", table_name="alert_thresholds")
    op.drop_index("ix_alert_thresholds_scope", table_name="alert_thresholds")
    op.drop_table("alert_thresholds")

    op.drop_index("ix_drilldown_paths_user_ts", table_name="drilldown_paths")
    op.drop_table("drilldown_paths")

    op.drop_index("ix_anomaly_alerts_ack", table_name="anomaly_alerts")
    op.drop_index("ix_anomaly_alerts_detected_at", table_name="anomaly_alerts")
    op.drop_index("ix_anomaly_alerts_metric_scope", table_name="anomaly_alerts")
    op.drop_table("anomaly_alerts")

    op.drop_index("ix_prediction_cache_created_at", table_name="prediction_cache")
    op.drop_index("ix_prediction_cache_lookup", table_name="prediction_cache")
    op.drop_table("prediction_cache")

    op.drop_index("ix_predictive_models_trained_at", table_name="predictive_models")
    op.drop_index("ix_predictive_models_metric_scope", table_name="predictive_models")
    op.drop_table("predictive_models")
