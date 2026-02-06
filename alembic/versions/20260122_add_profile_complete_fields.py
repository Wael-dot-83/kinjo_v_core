"""add_profile_complete_fields

Revision ID: 20260122_add_profile_complete_fields
Revises: 20260122_add_daily_report_unique
Create Date: 2026-01-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260122_add_profile_complete_fields"
down_revision: Union[str, None] = "20260122_add_daily_report_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('children', sa.Column('profile_complete', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('children', sa.Column('profile_completed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('parent_profiles', sa.Column('profile_complete', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('parent_profiles', sa.Column('profile_completed_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('parent_profiles', 'profile_completed_at')
    op.drop_column('parent_profiles', 'profile_complete')
    op.drop_column('children', 'profile_completed_at')
    op.drop_column('children', 'profile_complete')