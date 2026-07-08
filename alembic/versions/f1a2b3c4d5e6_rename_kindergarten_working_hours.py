"""rename kindergarten operating_hours_* to working_hours_*

Revision ID: f1a2b3c4d5e6
Revises: ba508b9b2169
Create Date: 2026-07-08 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'ba508b9b2169'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('kindergartens') as batch_op:
        batch_op.alter_column('operating_hours_start', new_column_name='working_hours_start')
        batch_op.alter_column('operating_hours_end', new_column_name='working_hours_end')


def downgrade() -> None:
    with op.batch_alter_table('kindergartens') as batch_op:
        batch_op.alter_column('working_hours_start', new_column_name='operating_hours_start')
        batch_op.alter_column('working_hours_end', new_column_name='operating_hours_end')
