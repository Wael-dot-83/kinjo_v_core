"""Merge branches

Revision ID: f38c5803c8e5
Revises: 10965a7ccff4, 20260211_add_governance_daily_reports
Create Date: 2026-02-11 06:52:05.625889

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f38c5803c8e5'
down_revision: Union[str, None] = ('10965a7ccff4', '20260211_add_governance_daily_reports')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
