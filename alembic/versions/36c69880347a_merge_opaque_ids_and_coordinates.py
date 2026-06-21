"""merge_opaque_ids_and_coordinates

Revision ID: 36c69880347a
Revises: d4e5f6a7b8c9, f6a7b8c9d0e1
Create Date: 2026-06-20 18:42:34.584474

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '36c69880347a'
down_revision: Union[str, None] = ('d4e5f6a7b8c9', 'f6a7b8c9d0e1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
