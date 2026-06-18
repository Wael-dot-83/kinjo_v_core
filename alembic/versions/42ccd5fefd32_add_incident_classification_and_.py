"""add_incident_classification_and_supervisor_fields

Revision ID: 42ccd5fefd32
Revises: 592f14b25b35
Create Date: 2026-06-16 03:45:35.612060

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = '42ccd5fefd32'
down_revision: Union[str, None] = '592f14b25b35'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    with op.batch_alter_table("incidents") as batch_op:
        if not _column_exists("incidents", "supervisor_id"):
            batch_op.add_column(sa.Column("supervisor_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                "fk_incidents_supervisor_id_users", "users", ["supervisor_id"], ["id"]
            )
        if not _column_exists("incidents", "classification"):
            batch_op.add_column(sa.Column("classification", sa.String(length=100), nullable=True))
        if not _column_exists("incidents", "parent_response"):
            batch_op.add_column(sa.Column("parent_response", sa.Text(), nullable=True))
        if not _column_exists("incidents", "parent_not_informed_reason"):
            batch_op.add_column(sa.Column("parent_not_informed_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("incidents") as batch_op:
        if _column_exists("incidents", "parent_not_informed_reason"):
            batch_op.drop_column("parent_not_informed_reason")
        if _column_exists("incidents", "parent_response"):
            batch_op.drop_column("parent_response")
        if _column_exists("incidents", "classification"):
            batch_op.drop_column("classification")
        if _column_exists("incidents", "supervisor_id"):
            batch_op.drop_column("supervisor_id")
