"""AI infrastructure tables: recommendations, manager alerts, job logs, features,
model versions, and feedback.

Revision ID: d2e3f4a5b6c7
Revises: e3f4a5b6c7d8
Create Date: 2026-05-01 01:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # -------------------------------------------------------------------------
    # ai_parent_recommendations
    # -------------------------------------------------------------------------
    op.create_table(
        "ai_parent_recommendations",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("child_id", sa.Integer(), sa.ForeignKey("children.id"), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("source_report_id", sa.Integer(), sa.ForeignKey("daily_reports.id"), nullable=True),
        sa.Column("recommendation_type", sa.String(50), nullable=False),
        sa.Column("content_ar", sa.Text(), nullable=True),
        sa.Column("content_en", sa.Text(), nullable=True),
        sa.Column("model_version", sa.String(50), nullable=True),
        sa.Column("prompt_version", sa.String(20), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=True),
        sa.Column("parent_feedback", sa.String(20), nullable=True),
        sa.Column("feedback_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("human_reviewed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_ai_parent_child_date", "ai_parent_recommendations", ["child_id", "report_date"])

    # -------------------------------------------------------------------------
    # ai_manager_alerts
    # -------------------------------------------------------------------------
    op.create_table(
        "ai_manager_alerts",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("kindergarten_id", sa.Integer(), sa.ForeignKey("kindergartens.id"), nullable=False),
        sa.Column("alert_type", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("target_entity_type", sa.String(50), nullable=True),
        sa.Column("target_entity_id", sa.Integer(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("rule_version", sa.String(20), nullable=True),
        sa.Column("acknowledged", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("acknowledged_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_ai_manager_alerts_kg", "ai_manager_alerts", ["kindergarten_id", "created_at"])

    # -------------------------------------------------------------------------
    # ai_job_logs
    # -------------------------------------------------------------------------
    op.create_table(
        "ai_job_logs",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("job_name", sa.String(100), nullable=False),
        sa.Column("job_type", sa.String(50), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("records_in", sa.Integer(), nullable=True),
        sa.Column("records_out", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("model_version", sa.String(50), nullable=True),
        sa.Column("prompt_version", sa.String(20), nullable=True),
        sa.Column("job_metadata", sa.JSON(), nullable=True),
    )
    op.create_index("idx_ai_job_logs_type_started", "ai_job_logs", ["job_type", "started_at"])

    # -------------------------------------------------------------------------
    # ai_features
    # -------------------------------------------------------------------------
    op.create_table(
        "ai_features",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("feature_name", sa.String(100), nullable=False),
        sa.Column("feature_value", sa.Float(), nullable=True),
        sa.Column("feature_json", sa.JSON(), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model_version", sa.String(50), nullable=True),
    )
    op.create_index(
        "idx_ai_features_entity_feature",
        "ai_features",
        ["entity_type", "entity_id", "feature_name"],
        unique=True,
    )

    # -------------------------------------------------------------------------
    # ai_model_versions
    # -------------------------------------------------------------------------
    op.create_table(
        "ai_model_versions",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("version", sa.String(20), nullable=False),
        sa.Column("model_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parameters", sa.JSON(), nullable=True),
        sa.Column("deployed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deployed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.UniqueConstraint("model_name", "version", name="uq_ai_model_version"),
    )

    # -------------------------------------------------------------------------
    # ai_feedback
    # -------------------------------------------------------------------------
    op.create_table(
        "ai_feedback",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("source_table", sa.String(100), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("user_role", sa.String(50), nullable=True),
        sa.Column("feedback_type", sa.String(50), nullable=False),
        sa.Column("feedback_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_ai_feedback_source", "ai_feedback", ["source_table", "source_id"])

    # -------------------------------------------------------------------------
    # PostgreSQL-only: JSONB upgrade + severity check on manager alerts
    # -------------------------------------------------------------------------
    if dialect == "postgresql":
        op.execute("""
            ALTER TABLE ai_parent_recommendations
                ALTER COLUMN evidence_json TYPE JSONB
                USING evidence_json::JSONB
        """)
        op.execute("""
            ALTER TABLE ai_manager_alerts
                ALTER COLUMN details TYPE JSONB
                USING details::JSONB,
                ADD CONSTRAINT ck_ai_manager_alert_severity
                CHECK (severity IN ('LOW','MEDIUM','HIGH','CRITICAL'))
        """)
        op.execute("""
            ALTER TABLE ai_features
                ALTER COLUMN feature_json TYPE JSONB
                USING feature_json::JSONB
        """)
        op.execute("""
            ALTER TABLE ai_model_versions
                ALTER COLUMN parameters TYPE JSONB
                USING parameters::JSONB
        """)
        op.execute("""
            ALTER TABLE ai_job_logs
                ALTER COLUMN job_metadata TYPE JSONB
                USING job_metadata::JSONB
        """)


def downgrade() -> None:
    op.drop_table("ai_feedback")
    op.drop_table("ai_model_versions")
    op.drop_table("ai_features")
    op.drop_table("ai_job_logs")
    op.drop_table("ai_manager_alerts")
    op.drop_table("ai_parent_recommendations")
