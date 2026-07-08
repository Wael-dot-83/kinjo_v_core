"""linear head so downgrade -1 is unambiguous past merge

Revision ID: da5ed45da2ec
Revises: ba508b9b2169
Create Date: 2026-07-08 20:00:35.971444

The previous head (ba508b9b2169) is a *merge* migration with two parents
(e7c4d9a1b2f3 + d4a2b8c1f0e9). Running ``alembic downgrade -1`` from a merge
point is ambiguous ("Ambiguous walk") because Alembic cannot choose which of
the two parents to step back to. The CI migrations job runs exactly
``upgrade head -> downgrade -1 -> upgrade head`` as a reversibility smoke test,
which therefore failed at the downgrade step.

This is an empty, no-op migration whose sole purpose is to give the graph a
single linear head above the merge, so ``downgrade -1`` deterministically walks
da5ed45da2ec -> ba508b9b2169 and the re-upgrade restores it. It performs no
schema changes and is safe to apply/revert on any database.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'da5ed45da2ec'
down_revision: Union[str, None] = 'ba508b9b2169'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Intentionally empty — see module docstring (linearizes the merge head).
    pass


def downgrade() -> None:
    # Intentionally empty — see module docstring (linearizes the merge head).
    pass
