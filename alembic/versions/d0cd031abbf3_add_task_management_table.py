"""add_task_management_table

Revision ID: d0cd031abbf3
Revises: 7d792f81c264
Create Date: 2026-01-14 07:56:59.200587

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd0cd031abbf3'
down_revision: Union[str, None] = '7d792f81c264'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create tasks table
    # Note: SQLAlchemy will handle enum types differently for SQLite vs PostgreSQL
    op.create_table('tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),  # SQLite uses VARCHAR instead of ENUM
        sa.Column('priority', sa.String(length=20), nullable=False),  # SQLite uses VARCHAR instead of ENUM
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('assigned_to_id', sa.Integer(), nullable=True),
        sa.Column('kindergarten_id', sa.Integer(), nullable=True),
        sa.Column('child_id', sa.Integer(), nullable=True),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("completed_at IS NULL OR status = 'COMPLETED'", name='ck_completed_at_requires_completed_status'),
        sa.ForeignKeyConstraint(['assigned_to_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['child_id'], ['children.id'], ),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['kindergarten_id'], ['kindergartens.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes
    op.create_index(op.f('ix_tasks_id'), 'tasks', ['id'], unique=False)
    op.create_index('idx_task_status_priority', 'tasks', ['status', 'priority'], unique=False)
    op.create_index('idx_task_assigned_to', 'tasks', ['assigned_to_id', 'status'], unique=False)
    op.create_index('idx_task_due_date', 'tasks', ['due_date'], unique=False)
    op.create_index('idx_task_kindergarten', 'tasks', ['kindergarten_id', 'status'], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_task_kindergarten', table_name='tasks')
    op.drop_index('idx_task_due_date', table_name='tasks')
    op.drop_index('idx_task_assigned_to', table_name='tasks')
    op.drop_index('idx_task_status_priority', table_name='tasks')
    op.drop_index(op.f('ix_tasks_id'), table_name='tasks')

    # Drop table
    op.drop_table('tasks')
