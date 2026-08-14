"""merge_heads_for_agency_snapshots

Revision ID: ea7ba800f0d5
Revises: analytics_dashboard_idx_01, sched_chart_exports_01
Create Date: 2026-08-14 09:01:15.205566

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ea7ba800f0d5'
down_revision: Union[str, None] = ('analytics_dashboard_idx_01', 'sched_chart_exports_01')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
