"""Add child DOB safety constraint.

Revision ID: 20260206_add_child_age_constraints
Revises: f60ea34b032b
Create Date: 2026-02-06
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260206_add_child_age_constraints"
down_revision = "f60ea34b032b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.create_check_constraint(
            "ck_children_dob_not_future",
            "children",
            sa.text("date_of_birth <= CURRENT_DATE"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_constraint("ck_children_dob_not_future", "children", type_="check")
