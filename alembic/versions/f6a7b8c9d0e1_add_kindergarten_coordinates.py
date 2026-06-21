"""add kindergarten coordinates

Revision ID: f6a7b8c9d0e1
Revises: a1b2c3d4e5f6
Create Date: 2026-06-20 01:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return any(c["name"] == column for c in insp.get_columns(table))


def _index_exists(table: str, index_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return any(ix["name"] == index_name for ix in insp.get_indexes(table))


def upgrade() -> None:
    if not _column_exists("kindergartens", "latitude"):
        op.add_column("kindergartens", sa.Column("latitude", sa.Float(), nullable=True))
    if not _column_exists("kindergartens", "longitude"):
        op.add_column("kindergartens", sa.Column("longitude", sa.Float(), nullable=True))

    if not _index_exists("kindergartens", "idx_kindergartens_governorate_city"):
        op.create_index("idx_kindergartens_governorate_city", "kindergartens", ["governorate", "city"])
    if not _index_exists("kindergartens", "idx_kindergartens_latitude"):
        op.create_index("idx_kindergartens_latitude", "kindergartens", ["latitude"])
    if not _index_exists("kindergartens", "idx_kindergartens_longitude"):
        op.create_index("idx_kindergartens_longitude", "kindergartens", ["longitude"])


def downgrade() -> None:
    for index_name in ("idx_kindergartens_longitude", "idx_kindergartens_latitude", "idx_kindergartens_governorate_city"):
        if _index_exists("kindergartens", index_name):
            op.drop_index(index_name, table_name="kindergartens")

    for column_name in ("longitude", "latitude"):
        if _column_exists("kindergartens", column_name):
            op.drop_column("kindergartens", column_name)
