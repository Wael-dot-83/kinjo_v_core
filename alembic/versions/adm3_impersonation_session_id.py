"""ADMIN-003: correlate audit rows to an impersonation session

Adds audit_logs.impersonation_session_id plus its index. The column is
stamped by the before_flush listener in database.py on every audit row
written while an admin is impersonating, so a reviewer can replay one
session end to end instead of inferring it from timestamps.

Revision ID: adm3_imp_session_01
Revises: jordan_business_date_all_01
Create Date: 2026-08-20 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "adm3_imp_session_01"
down_revision: Union[str, None] = "jordan_business_date_all_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "audit_logs"
_COLUMN = "impersonation_session_id"
_INDEX = "idx_audit_logs_impersonation_session"


def _has_column(table: str, col: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return any(c["name"] == col for c in insp.get_columns(table))


def _has_index(table: str, name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return any(ix.get("name") == name for ix in insp.get_indexes(table))


def upgrade() -> None:
    if not _has_column(_TABLE, _COLUMN):
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(36), nullable=True))
    if not _has_index(_TABLE, _INDEX):
        op.create_index(_INDEX, _TABLE, [_COLUMN])


def downgrade() -> None:
    if _has_index(_TABLE, _INDEX):
        op.drop_index(_INDEX, table_name=_TABLE)
    if _has_column(_TABLE, _COLUMN):
        op.drop_column(_TABLE, _COLUMN)
