"""add_unique_constraint_kindergarten_name_governorate

Revision ID: d85eadde3694
Revises: 3c56302e2240
Create Date: 2026-01-27 07:26:37.819967

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd85eadde3694'
down_revision: Union[str, None] = '3c56302e2240'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # For SQLite, use a different approach to delete duplicates
    # First, identify duplicates and keep the one with lowest id
    op.execute("""
        DELETE FROM kindergartens 
        WHERE id NOT IN (
            SELECT MIN(id) 
            FROM kindergartens 
            WHERE name_en IS NOT NULL 
            GROUP BY name_en, governorate
        )
    """)
    
    # For SQLite, create the constraint using raw SQL since batch mode might not work
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        # Create a unique index instead of constraint for SQLite
        op.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_kindergarten_name_en_governorate 
            ON kindergartens (name_en, governorate) 
            WHERE name_en IS NOT NULL
        """)
    else:
        # Add unique constraint on (name_en, governorate) where name_en is not null
        op.create_unique_constraint(
            'uq_kindergarten_name_en_governorate',
            'kindergartens',
            ['name_en', 'governorate'],
            schema=None
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("DROP INDEX IF EXISTS uq_kindergarten_name_en_governorate")
    else:
        op.drop_constraint('uq_kindergarten_name_en_governorate', 'kindergartens', type_='unique')
