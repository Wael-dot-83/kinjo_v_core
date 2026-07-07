"""add composite indexes on supervisor_assignments (D2)

Revision ID: d4a2c1b8e6f0
Revises: c3f1a7d9e2b0
Create Date: 2026-07-07 13:30:00.000000

Active-assignment lookups filter on (class_id, deleted_at) and
(supervisor_id, deleted_at) — see routers/manager.py. Before this the table
only had its primary-key index, so those filters were sequential scans. Adds
two composite indexes matching the query patterns (D2). AttendanceLog already
carries the equivalent composite indexes (D3), so no change is needed there.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "d4a2c1b8e6f0"
down_revision: Union[str, None] = "c3f1a7d9e2b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_INDEXES = (
    ("ix_supervisor_assignments_class_deleted", ["class_id", "deleted_at"]),
    ("ix_supervisor_assignments_supervisor_deleted", ["supervisor_id", "deleted_at"]),
)


def upgrade() -> None:
    existing = {ix["name"] for ix in inspect(op.get_bind()).get_indexes("supervisor_assignments")}
    for name, cols in _INDEXES:
        if name not in existing:
            op.create_index(name, "supervisor_assignments", cols)


def downgrade() -> None:
    existing = {ix["name"] for ix in inspect(op.get_bind()).get_indexes("supervisor_assignments")}
    for name, _cols in _INDEXES:
        if name in existing:
            op.drop_index(name, table_name="supervisor_assignments")
