"""create incident_history — declared in models.py, never created by any migration

GET /api/incidents/{incident_id}/history runs db.query(models.IncidentHistory)
(safety_service.py, router mounted in main.py), but no migration ever created the table.
On any freshly migrated deployment that endpoint fails with
"relation incident_history does not exist". It only works in dev because
Base.metadata.create_all() makes the table there — which is exactly what hides this class
of bug until deploy.

Scope: this creates the one table the application actually queries. telemetry_events,
web_vital_metrics and client_error_reports had the same drift but were dead schema —
telemetry_service.py keeps everything in memory and never touched them — so their models
are deleted in this change instead of adding tables with no lifecycle or retention owner.

Additive only, deliberately. Autogenerate also proposed dropping accessibility_audits,
financial_records, individualized_learning_plans, communication_events and others, and
rewriting foreign keys on users: those exist in the database but not in models.py, which
is the harmless direction of drift. Dropping them would destroy live data, so none of it
is included here.

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
