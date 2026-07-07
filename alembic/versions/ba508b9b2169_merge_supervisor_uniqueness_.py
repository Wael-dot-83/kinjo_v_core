"""merge supervisor-uniqueness + kindergarten-mgmt heads

Revision ID: ba508b9b2169
Revises: e7c4d9a1b2f3, d4a2b8c1f0e9
Create Date: 2026-07-07 21:57:59.701439

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ba508b9b2169'
down_revision: Union[str, None] = ('e7c4d9a1b2f3', 'd4a2b8c1f0e9')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
