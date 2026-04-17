"""Merge all migration heads for consistency

Revision ID: 7f6b861feff1
Revises: 20260209_add_parent_enrollment_constraints, iam_hardening_001, d85eadde3694
Create Date: 2026-02-10 20:55:17.935896

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f6b861feff1'
down_revision: Union[str, None] = ('20260209_add_parent_enrollment_constraints', 'iam_hardening_001', 'd85eadde3694')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
