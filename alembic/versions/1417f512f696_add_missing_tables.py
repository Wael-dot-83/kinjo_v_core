"""add missing tables: incident_history, telemetry_events, web_vital_metrics, client_error_reports

All four are declared in models.py but no migration ever created them, so a database
built from the migration chain does not have them.

incident_history is the urgent one: GET /api/incidents/{incident_id}/history queries it
(safety_service.py), so on any freshly migrated deployment that endpoint fails with
"relation incident_history does not exist". The other three are dead schema today —
telemetry_service.py imports the models but keeps everything in memory and never reads
or writes them — but they are created here too so models.py and the chain agree and
`alembic check` comes back clean.

Additive only, on purpose. Autogenerate also wanted to drop accessibility_audits,
financial_records, individualized_learning_plans, communication_events and more, and to
rewrite foreign keys on users: those tables exist in the database but not in models.py,
which is the harmless direction of drift. Dropping them would destroy live data, so none
of it is included here.

Revision ID: 1417f512f696
Revises: a9c3d4e5f607
Create Date: 2026-07-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1417f512f696"
down_revision: Union[str, None] = "a9c3d4e5f607"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('telemetry_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('event_id', sa.String(length=36), nullable=False),
    sa.Column('session_id', sa.String(length=64), nullable=False),
    sa.Column('event_type', sa.Enum('PAGE_VIEW', 'INTERACTION', 'API_CALL', 'ERROR', name='telemetryeventtype'), nullable=False),
    sa.Column('page', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(length=50), nullable=True),
    sa.Column('lang', sa.String(length=10), nullable=False),
    sa.Column('direction', sa.String(length=10), nullable=False),
    sa.Column('timestamp_ms', sa.BigInteger(), nullable=False),
    sa.Column('duration_ms', sa.Float(), nullable=True),
    sa.Column('payload', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('event_id', name='uq_telemetry_event_id')
    )
    with op.batch_alter_table('telemetry_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_telemetry_events_id'), ['id'], unique=False)
        batch_op.create_index('ix_telemetry_events_page', ['page'], unique=False)
        batch_op.create_index('ix_telemetry_events_role', ['role'], unique=False)
        batch_op.create_index('ix_telemetry_events_session', ['session_id'], unique=False)
        batch_op.create_index('ix_telemetry_events_timestamp', ['timestamp_ms'], unique=False)
        batch_op.create_index('ix_telemetry_events_type', ['event_type'], unique=False)

    op.create_table('web_vital_metrics',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.String(length=64), nullable=False),
    sa.Column('page', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(length=50), nullable=True),
    sa.Column('lang', sa.String(length=10), nullable=False),
    sa.Column('direction', sa.String(length=10), nullable=False),
    sa.Column('metric_name', sa.Enum('LCP', 'FID', 'CLS', name='webvitaltype'), nullable=False),
    sa.Column('value', sa.Float(), nullable=False),
    sa.Column('rating', sa.Enum('GOOD', 'NEEDS_IMPROVEMENT', 'POOR', name='vitalrating'), nullable=False),
    sa.Column('timestamp_ms', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('web_vital_metrics', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_web_vital_metrics_id'), ['id'], unique=False)
        batch_op.create_index('ix_web_vitals_metric', ['metric_name'], unique=False)
        batch_op.create_index('ix_web_vitals_page', ['page'], unique=False)
        batch_op.create_index('ix_web_vitals_session', ['session_id'], unique=False)
        batch_op.create_index('ix_web_vitals_timestamp', ['timestamp_ms'], unique=False)

    op.create_table('client_error_reports',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.String(length=64), nullable=False),
    sa.Column('page', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(length=50), nullable=True),
    sa.Column('error_type', sa.String(length=50), nullable=False),
    sa.Column('message', sa.String(length=500), nullable=False),
    sa.Column('stack_hash', sa.String(length=16), nullable=True),
    sa.Column('timestamp_ms', sa.BigInteger(), nullable=False),
    sa.Column('is_acknowledged', sa.Boolean(), nullable=False),
    sa.Column('acknowledged_by', sa.Integer(), nullable=True),
    sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.ForeignKeyConstraint(['acknowledged_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('client_error_reports', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_client_error_reports_id'), ['id'], unique=False)
        batch_op.create_index('ix_client_errors_page', ['page'], unique=False)
        batch_op.create_index('ix_client_errors_session', ['session_id'], unique=False)
        batch_op.create_index('ix_client_errors_stack_hash', ['stack_hash'], unique=False)
        batch_op.create_index('ix_client_errors_timestamp', ['timestamp_ms'], unique=False)

    op.create_table('incident_history',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('incident_id', sa.Integer(), nullable=False),
    sa.Column('changed_by', sa.Integer(), nullable=False),
    sa.Column('status_from', sa.Enum('OPEN', 'UNDER_INVESTIGATION', 'ACTION_REQUIRED', 'RESOLVED', 'CLOSED', name='incidentstatus'), nullable=True),
    sa.Column('status_to', sa.Enum('OPEN', 'UNDER_INVESTIGATION', 'ACTION_REQUIRED', 'RESOLVED', 'CLOSED', name='incidentstatus'), nullable=True),
    sa.Column('owner_from_id', sa.Integer(), nullable=True),
    sa.Column('owner_to_id', sa.Integer(), nullable=True),
    sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['changed_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['incident_id'], ['incidents.id'], ),
    sa.ForeignKeyConstraint(['owner_from_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['owner_to_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('incident_history', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_incident_history_id'), ['id'], unique=False)
        batch_op.create_index('ix_incident_history_incident_id', ['incident_id'], unique=False)

def downgrade() -> None:
    op.drop_table("incident_history")
    op.drop_table("client_error_reports")
    op.drop_table("web_vital_metrics")
    op.drop_table("telemetry_events")
