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
    # Use op.add_column directly — works on both SQLite (ALTER TABLE ADD COLUMN)
    # and PostgreSQL without batch_alter_table, which triggers a SQLite circular
    # dependency error on large tables. sa.false() is dialect-agnostic: emits
    # DEFAULT false on PostgreSQL and DEFAULT 0 on SQLite.
    op.add_column('users', sa.Column(
        'mfa_enabled',
        sa.Boolean(),
        nullable=False,
        server_default=sa.false(),
    ))
    op.add_column('users', sa.Column(
        'mfa_secret',
        sa.String(length=255),
        nullable=True,
    ))
    op.add_column('users', sa.Column(
        'mfa_enrolled_at',
        sa.DateTime(timezone=True),
        nullable=True,
    ))
    op.add_column('users', sa.Column(
        'mfa_last_verified_at',
        sa.DateTime(timezone=True),
        nullable=True,
    ))


def downgrade() -> None:
    op.drop_column('users', 'mfa_last_verified_at')
    op.drop_column('users', 'mfa_enrolled_at')
    op.drop_column('users', 'mfa_secret')
    op.drop_column('users', 'mfa_enabled')
