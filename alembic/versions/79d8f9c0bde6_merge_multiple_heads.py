"""Merge multiple heads

Revision ID: 79d8f9c0bde6
Revises: 20250120_unique_email, f3da6d982bac
Create Date: 2026-01-20 10:00:53.917294

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '79d8f9c0bde6'
down_revision: Union[str, None] = ('20250120_unique_email', 'f3da6d982bac')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
