"""add_incident_resolution_fields

Revision ID: 4056ab4bc0ed
Revises: a1b2c3d4e5f7
Create Date: 2026-05-30 23:14:36.338740

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = '4056ab4bc0ed'
down_revision: Union[str, None] = 'a1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    with op.batch_alter_table('incidents') as batch_op:
        if not _column_exists('incidents', 'parent_informed'):
            batch_op.add_column(sa.Column('parent_informed', sa.Boolean(), nullable=False, server_default='0'))
        if not _column_exists('incidents', 'resolution_notes'):
            batch_op.add_column(sa.Column('resolution_notes', sa.Text(), nullable=True))
        if not _column_exists('incidents', 'attachment_url'):
            batch_op.add_column(sa.Column('attachment_url', sa.String(500), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('incidents') as batch_op:
        if _column_exists('incidents', 'attachment_url'):
            batch_op.drop_column('attachment_url')
        if _column_exists('incidents', 'resolution_notes'):
            batch_op.drop_column('resolution_notes')
