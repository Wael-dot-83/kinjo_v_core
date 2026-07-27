"""add ix_incidents_occurred_at for network-wide analytics range scans

The incidents table carries two composite indexes, both led by ``kindergarten_id``:

    ix_incidents_kg_occurred_at  (kindergarten_id, occurred_at)
    ix_incidents_kg_severity     (kindergarten_id, severity_level)

Every network-wide analytics query — the default view of the Guided Analytics Explorer
and of the legacy charts explorer — filters on ``occurred_at`` and ``deleted_at`` with no
kindergarten bound. The leading column is therefore unconstrained, neither composite is
usable, and the planner falls back to a full table scan:

    EXPLAIN QUERY PLAN
      SCAN incidents
      USE TEMP B-TREE FOR GROUP BY

Measured on a 300,000-row incidents table (SQLite, best of 7 runs):

    window      before      after
    7 days      50.5 ms     0.0 ms
    30 days     50.2 ms     0.0 ms
    90 days     49.0 ms    11.3 ms
    365 days    56.9 ms   133.3 ms     <- the explorer's default period, 11% of the table

Note on wide ranges: past roughly a 10% selectivity SQLite keeps choosing this index where
a sequential scan would win, even after ANALYZE, so a year-wide window measures slower with
it than without. Production runs PostgreSQL — config.validate_production_settings() refuses
to start on SQLite — and its cost-based planner reverts to a sequential scan once a range
stops being selective, so the regression does not apply there. The index is retained because
it is decisive for the narrow windows operators drill into (7/30/90 days), which dominate
interaction after the initial load. The explorer additionally caps a period at 3653 days.

Purely additive and reversible: one index created, no data touched, no DDL on columns.

Revision ID: analytics_idx_01
Revises: canon_gov_cap_01
Create Date: 2026-07-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "analytics_idx_01"
down_revision: Union[str, None] = "canon_gov_cap_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX_NAME = "ix_incidents_occurred_at"
_TABLE = "incidents"


def _index_exists(bind) -> bool:
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return False
    return any(ix["name"] == _INDEX_NAME for ix in inspector.get_indexes(_TABLE))


def upgrade() -> None:
    bind = op.get_bind()
    # Idempotent: a create_all-built development database already has this index,
    # because it is declared on the model.
    if _index_exists(bind):
        return
    op.create_index(_INDEX_NAME, _TABLE, ["occurred_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if _index_exists(bind):
        op.drop_index(_INDEX_NAME, table_name=_TABLE)
