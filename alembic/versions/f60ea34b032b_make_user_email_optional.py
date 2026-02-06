"""make_user_email_optional

Revision ID: f60ea34b032b
Revises: 79d8f9c0bde6
Create Date: 2026-01-20 23:02:24.719919

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f60ea34b032b'
down_revision: Union[str, None] = '79d8f9c0bde6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # For SQLite, we need to recreate the table since ALTER COLUMN is limited
    # First, drop the unique indexes on email
    op.drop_index('ix_users_email_unique', table_name='users', if_exists=True)
    op.drop_index('ix_users_email', table_name='users', if_exists=True)

    # Create a new table with nullable email
    op.rename_table('users', 'users_old')

    op.create_table('users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=True),  # Made nullable
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('role', sa.Enum('ADMIN', 'MANAGER', 'SUPERVISOR', 'PARENT', name='userrole'), nullable=False),
        sa.Column('status', sa.Enum('ACTIVE', 'SUSPENDED', 'INACTIVE', name='userstatus'), nullable=False),
        sa.Column('kindergarten_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['kindergarten_id'], ['kindergartens.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # Copy data from old table to new table
    op.execute("""
        INSERT INTO users (id, username, email, hashed_password, role, status, kindergarten_id, created_at, updated_at)
        SELECT id, username, email, hashed_password, role, status, kindergarten_id, created_at, updated_at
        FROM users_old
    """)

    # Drop old table
    op.drop_table('users_old')

    # Recreate indexes (without unique constraint on email)
    op.create_index('idx_user_role_kindergarten', 'users', ['role', 'kindergarten_id'], unique=False)
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)


def downgrade() -> None:
    # For downgrade, we need to make email non-nullable again
    # This is complex in SQLite, so we'll recreate the table again
    op.rename_table('users', 'users_old')

    op.create_table('users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),  # Make non-nullable again
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('role', sa.Enum('ADMIN', 'MANAGER', 'SUPERVISOR', 'PARENT', name='userrole'), nullable=False),
        sa.Column('status', sa.Enum('ACTIVE', 'SUSPENDED', 'INACTIVE', name='userstatus'), nullable=False),
        sa.Column('kindergarten_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['kindergarten_id'], ['kindergartens.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # Copy data, but we need to handle NULL emails - this might fail if there are NULLs
    op.execute("""
        INSERT INTO users (id, username, email, hashed_password, role, status, kindergarten_id, created_at, updated_at)
        SELECT id, username,
               CASE WHEN email IS NULL THEN '' ELSE email END as email,
               hashed_password, role, status, kindergarten_id, created_at, updated_at
        FROM users_old
    """)

    op.drop_table('users_old')

    # Recreate indexes with unique constraint on email
    op.create_index('idx_user_role_kindergarten', 'users', ['role', 'kindergarten_id'], unique=False)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
