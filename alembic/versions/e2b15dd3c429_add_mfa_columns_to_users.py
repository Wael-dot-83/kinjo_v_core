"""add_mfa_columns_to_users

Revision ID: e2b15dd3c429
Revises: db828d82089e
Create Date: 2026-04-25 12:01:33.063008

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2b15dd3c429'
down_revision: Union[str, None] = 'db828d82089e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use dialect-agnostic false() so this works on both SQLite ('0') and PostgreSQL ('false').
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'mfa_enabled',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ))
        batch_op.add_column(sa.Column(
            'mfa_secret',
            sa.String(length=255),
            nullable=True,
        ))
        batch_op.add_column(sa.Column(
            'mfa_enrolled_at',
            sa.DateTime(timezone=True),
            nullable=True,
        ))
        batch_op.add_column(sa.Column(
            'mfa_last_verified_at',
            sa.DateTime(timezone=True),
            nullable=True,
        ))


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('mfa_last_verified_at')
        batch_op.drop_column('mfa_enrolled_at')
        batch_op.drop_column('mfa_secret')
        batch_op.drop_column('mfa_enabled')
