"""add_user_preferences_tables

Revision ID: 10965a7ccff4
Revises: 7f6b861feff1
Create Date: 2026-02-10 21:44:44.458651

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '10965a7ccff4'
down_revision: Union[str, None] = '7f6b861feff1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create user_dashboard_preferences table
    op.create_table('user_dashboard_preferences',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('widget_config', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    op.create_index('ix_user_dashboard_prefs_user_id', 'user_dashboard_preferences', ['user_id'], unique=False)

    # Create user_filter_preferences table
    op.create_table('user_filter_preferences',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('filter_config', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    op.create_index('ix_user_filter_prefs_user_id', 'user_filter_preferences', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_user_filter_prefs_user_id', table_name='user_filter_preferences')
    op.drop_table('user_filter_preferences')
    op.drop_index('ix_user_dashboard_prefs_user_id', table_name='user_dashboard_preferences')
    op.drop_table('user_dashboard_preferences')
