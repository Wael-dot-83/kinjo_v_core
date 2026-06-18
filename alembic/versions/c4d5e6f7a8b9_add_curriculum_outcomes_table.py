"""add_curriculum_outcomes_table

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-06-16 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table: str) -> bool:
    return table in inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _has_table("curriculum_outcomes"):
        return
    op.create_table(
        "curriculum_outcomes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "domain",
            sa.Enum(
                "SOCIAL_EMOTIONAL", "COGNITIVE", "PHYSICAL", "LANGUAGE",
                name="learningdomain",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("age_band_min_months", sa.Integer(), nullable=False),
        sa.Column("age_band_max_months", sa.Integer(), nullable=False),
        sa.Column("indicator_code", sa.String(length=50), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "idx_curriculum_outcomes_domain_age",
        "curriculum_outcomes",
        ["domain", "age_band_min_months"],
    )


def downgrade() -> None:
    if not _has_table("curriculum_outcomes"):
        return
    op.drop_index("idx_curriculum_outcomes_domain_age", table_name="curriculum_outcomes")
    op.drop_table("curriculum_outcomes")
