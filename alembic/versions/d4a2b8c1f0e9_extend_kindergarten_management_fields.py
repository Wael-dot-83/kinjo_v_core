"""extend kindergarten management fields and DELETED status

Revision ID: d4a2b8c1f0e9
Revises: c3f1a7d9e2b0
Create Date: 2026-07-07 13:40:00.000000

Adds the extended Management-module columns to `kindergartens` and the
`DELETED` value to the KindergartenStatus enum (PostgreSQL native enum only;
SQLite stores the status as VARCHAR with no CHECK constraint).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4a2b8c1f0e9"
down_revision: Union[str, None] = "c3f1a7d9e2b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    with op.batch_alter_table("kindergartens") as batch_op:
        batch_op.add_column(sa.Column("frozen_by", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("deleted_by", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("legal_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("type", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("mobile", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("website", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("manager_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("manager_id", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("manager_phone", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("manager_email", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("owner_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("ownership_type", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("total_capacity", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("current_child_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("number_of_classes", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("teacher_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("working_days", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("age_group", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("registration_fees", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("monthly_fees", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("license_status", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("administrative_notes", sa.Text(), nullable=True))

    if dialect == "postgresql":
        op.execute("ALTER TYPE kindergartenstatus ADD VALUE IF NOT EXISTS 'DELETED'")


def downgrade() -> None:
    with op.batch_alter_table("kindergartens") as batch_op:
        for col in (
            "administrative_notes", "license_status", "monthly_fees", "registration_fees",
            "age_group", "working_days", "teacher_count", "number_of_classes",
            "current_child_count", "total_capacity", "ownership_type", "owner_name",
            "manager_email", "manager_phone", "manager_id", "manager_name", "website",
            "mobile", "type", "legal_name", "deleted_by", "deleted_at", "frozen_by",
        ):
            batch_op.drop_column(col)
    # PostgreSQL cannot easily drop an enum value; 'DELETED' is left in place.
