"""Make contact_email optional for kindergartens

Revision ID: 20260117111707
Revises: d0cd031abbf3
Create Date: 2026-01-17 11:17:07.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260117111707'
down_revision = 'd0cd031abbf3'
branch_labels = None
depends_on = None


def upgrade():
    """
    Make contact_email column nullable in kindergartens table.
    This allows kindergartens to be created without an email address.
    """
    # SQLite doesn't support ALTER COLUMN directly, so we need to check the dialect
    bind = op.get_bind()
    
    if bind.dialect.name == 'sqlite':
        # SQLite: Recreate table (more complex, but safer)
        # For development/testing with SQLite, we'll use a workaround
        # Note: This approach preserves existing data
        
        # Step 1: Add a temporary column
        with op.batch_alter_table('kindergartens', schema=None) as batch_op:
            batch_op.alter_column('contact_email',
                                  existing_type=sa.String(length=255),
                                  nullable=True,
                                  existing_nullable=False)
    else:
        # PostgreSQL/MySQL: Direct ALTER COLUMN
        op.alter_column('kindergartens', 'contact_email',
                        existing_type=sa.String(255),
                        nullable=True,
                        existing_nullable=False)


def downgrade():
    """
    Revert contact_email to NOT NULL.
    WARNING: This will fail if NULL values exist in the column.
    """
    bind = op.get_bind()
    
    # Before reverting, set empty string for NULL values to prevent constraint violation
    op.execute("UPDATE kindergartens SET contact_email = '' WHERE contact_email IS NULL")
    
    if bind.dialect.name == 'sqlite':
        with op.batch_alter_table('kindergartens', schema=None) as batch_op:
            batch_op.alter_column('contact_email',
                                  existing_type=sa.String(length=255),
                                  nullable=False,
                                  existing_nullable=True)
    else:
        op.alter_column('kindergartens', 'contact_email',
                        existing_type=sa.String(255),
                        nullable=False,
                        existing_nullable=True)
