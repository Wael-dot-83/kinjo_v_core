"""merge heads: curriculum outcomes, performance indexes, jordan heat map

Revision ID: 592f14b25b35
Revises: c4d5e6f7a8b9, g1h2i3j4k5l6, h1m2026h01
Create Date: 2026-06-16 03:23:07.016125

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '592f14b25b35'
down_revision: Union[str, None] = ('c4d5e6f7a8b9', 'g1h2i3j4k5l6', 'h1m2026h01')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
