"""national immunization schedule table

Revision ID: f7a1c2e9b3d0
Revises: da5ed45da2ec
Create Date: 2026-07-12 06:20:00.000000

Adds ``national_immunization_schedule`` — the admin-uploaded MOH vaccine schedule
(vaccine name, due age value + unit) that powers the ``vaccination_due_children``
agency report. Aggregated-only; holds no per-child data.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7a1c2e9b3d0'
down_revision: Union[str, None] = 'da5ed45da2ec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "national_immunization_schedule",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("vaccine_name", sa.String(length=200), nullable=False),
        sa.Column("age_value", sa.Integer(), nullable=False),
        sa.Column("age_unit", sa.Enum("DAY", "MONTH", "YEAR", name="immunizationageunit"), nullable=False),
        sa.Column("due_age_days", sa.Integer(), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("uploaded_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.CheckConstraint("age_value >= 0", name="ck_immunization_age_value_nonneg"),
        sa.CheckConstraint("due_age_days >= 0", name="ck_immunization_due_age_days_nonneg"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_immunization_due_age_days", "national_immunization_schedule", ["due_age_days"])
    op.create_index(op.f("ix_national_immunization_schedule_id"), "national_immunization_schedule", ["id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_national_immunization_schedule_id"), table_name="national_immunization_schedule")
    op.drop_index("ix_immunization_due_age_days", table_name="national_immunization_schedule")
    op.drop_table("national_immunization_schedule")
    # PostgreSQL keeps the ENUM type after the table is dropped; without this an
    # upgrade->downgrade->upgrade cycle (the CI reversibility smoke test) fails
    # with 'type "immunizationageunit" already exists'. SQLite has no such type.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS immunizationageunit")
