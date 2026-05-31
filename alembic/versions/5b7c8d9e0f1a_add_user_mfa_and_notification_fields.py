"""add_user_mfa_and_notification_fields

Revision ID: 5b7c8d9e0f1a
Revises: 4056ab4bc0ed
Create Date: 2026-05-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = '5b7c8d9e0f1a'
down_revision: Union[str, None] = '4056ab4bc0ed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    with op.batch_alter_table('users') as batch_op:
        if not _column_exists('users', 'totp_secret'):
            batch_op.add_column(sa.Column('totp_secret', sa.String(255), nullable=True))
        if not _column_exists('users', 'notification_preferences'):
            batch_op.add_column(sa.Column('notification_preferences', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('users') as batch_op:
        if _column_exists('users', 'notification_preferences'):
            batch_op.drop_column('notification_preferences')
        if _column_exists('users', 'totp_secret'):
            batch_op.drop_column('totp_secret')
