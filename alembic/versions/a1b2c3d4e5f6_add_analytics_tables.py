"""add_analytics_tables

Revision ID: a1b2c3d4e5f6
Revises: d0cd031abbf3
Create Date: 2026-01-17 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '20260117111707'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create analytics_dimension_cache table
    op.create_table('analytics_dimension_cache',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('dimension_type', sa.String(length=20), nullable=False),  # NETWORK, GOVERNORATE, KINDERGARTEN, CLASS
        sa.Column('dimension_id', sa.String(length=100), nullable=False),
        sa.Column('period_type', sa.String(length=20), nullable=False),  # DAILY, WEEKLY, MONTHLY, QUARTERLY, YEARLY
        sa.Column('period_date', sa.Date(), nullable=False),

        # Enrollment metrics
        sa.Column('total_capacity', sa.Integer(), nullable=True),
        sa.Column('total_enrolled', sa.Integer(), nullable=True),
        sa.Column('enrollment_rate', sa.Float(), nullable=True),
        sa.Column('pending_applications', sa.Integer(), nullable=True),

        # Attendance metrics
        sa.Column('expected_attendance', sa.Integer(), nullable=True),
        sa.Column('actual_attendance', sa.Integer(), nullable=True),
        sa.Column('attendance_rate', sa.Float(), nullable=True),
        sa.Column('chronic_absence_count', sa.Integer(), nullable=True),

        # Daily reports metrics
        sa.Column('expected_reports', sa.Integer(), nullable=True),
        sa.Column('submitted_reports', sa.Integer(), nullable=True),
        sa.Column('report_completion_rate', sa.Float(), nullable=True),

        # Safety metrics
        sa.Column('total_incidents', sa.Integer(), nullable=True),
        sa.Column('high_severity_incidents', sa.Integer(), nullable=True),
        sa.Column('incident_rate_per_100', sa.Float(), nullable=True),

        # Staffing metrics
        sa.Column('total_staff', sa.Integer(), nullable=True),
        sa.Column('ratio_compliant_minutes', sa.Integer(), nullable=True),
        sa.Column('ratio_total_minutes', sa.Integer(), nullable=True),
        sa.Column('ratio_compliance_rate', sa.Float(), nullable=True),

        # Engagement metrics
        sa.Column('surveys_sent', sa.Integer(), nullable=True),
        sa.Column('survey_responses', sa.Integer(), nullable=True),
        sa.Column('survey_response_rate', sa.Float(), nullable=True),
        sa.Column('nps_score', sa.Float(), nullable=True),

        # Governance scores
        sa.Column('governance_quality_index', sa.Float(), nullable=True),
        sa.Column('child_experience_index', sa.Float(), nullable=True),
        sa.Column('final_governance_score', sa.Float(), nullable=True),

        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for analytics_dimension_cache
    op.create_index(op.f('ix_analytics_dimension_cache_id'), 'analytics_dimension_cache', ['id'], unique=False)
    op.create_index('ix_analytics_cache_dimension', 'analytics_dimension_cache', ['dimension_type', 'dimension_id'], unique=False)
    op.create_index('ix_analytics_cache_period', 'analytics_dimension_cache', ['period_type', 'period_date'], unique=False)
    op.create_index('ix_analytics_cache_lookup', 'analytics_dimension_cache', ['dimension_type', 'dimension_id', 'period_type', 'period_date'], unique=False)

    # Create export_jobs table
    op.create_table('export_jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('export_format', sa.String(length=20), nullable=False),  # CSV, PDF, EXCEL
        sa.Column('report_type', sa.String(length=100), nullable=False),
        sa.Column('filters', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),  # PENDING, PROCESSING, COMPLETED, FAILED
        sa.Column('file_path', sa.String(length=500), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for export_jobs
    op.create_index(op.f('ix_export_jobs_id'), 'export_jobs', ['id'], unique=False)
    op.create_index('ix_export_jobs_user_status', 'export_jobs', ['user_id', 'status'], unique=False)

    # Create additional indexes on existing tables for analytics queries
    op.create_index('ix_attendance_logs_date_child', 'attendance_logs', ['date', 'child_id'], unique=False)
    op.create_index('ix_daily_reports_date_status', 'daily_reports', ['date', 'status'], unique=False)
    op.create_index('ix_incidents_occurred_kg', 'incidents', ['occurred_at', 'kindergarten_id'], unique=False)
    op.create_index('ix_kindergartens_governorate', 'kindergartens', ['governorate', 'status'], unique=False)


def downgrade() -> None:
    # Drop indexes on existing tables
    op.drop_index('ix_kindergartens_governorate', table_name='kindergartens')
    op.drop_index('ix_incidents_occurred_kg', table_name='incidents')
    op.drop_index('ix_daily_reports_date_status', table_name='daily_reports')
    op.drop_index('ix_attendance_logs_date_child', table_name='attendance_logs')

    # Drop export_jobs indexes and table
    op.drop_index('ix_export_jobs_user_status', table_name='export_jobs')
    op.drop_index(op.f('ix_export_jobs_id'), table_name='export_jobs')
    op.drop_table('export_jobs')

    # Drop analytics_dimension_cache indexes and table
    op.drop_index('ix_analytics_cache_lookup', table_name='analytics_dimension_cache')
    op.drop_index('ix_analytics_cache_period', table_name='analytics_dimension_cache')
    op.drop_index('ix_analytics_cache_dimension', table_name='analytics_dimension_cache')
    op.drop_index(op.f('ix_analytics_dimension_cache_id'), table_name='analytics_dimension_cache')
    op.drop_table('analytics_dimension_cache')
