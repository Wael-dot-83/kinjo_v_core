"""add_enrollment_decision_timestamps

Add accepted_at and rejected_at columns to enrollment_applications,
and add indexes for common enrollment analytics filters.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f8"
down_revision: Union[str, None] = "36c69880347a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "enrollment_applications",
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "enrollment_applications",
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_enrollment_status",
        "enrollment_applications",
        ["status"],
    )
    op.create_index(
        "ix_enrollment_source",
        "enrollment_applications",
        ["source"],
    )
    op.create_index(
        "ix_enrollment_decision_by",
        "enrollment_applications",
        ["decision_by"],
    )
    op.create_index(
        "ix_enrollment_submitted_at",
        "enrollment_applications",
        ["submitted_at"],
    )
    op.create_index(
        "ix_enrollment_decision_at",
        "enrollment_applications",
        ["decision_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_enrollment_decision_at", table_name="enrollment_applications")
    op.drop_index("ix_enrollment_submitted_at", table_name="enrollment_applications")
    op.drop_index("ix_enrollment_decision_by", table_name="enrollment_applications")
    op.drop_index("ix_enrollment_source", table_name="enrollment_applications")
    op.drop_index("ix_enrollment_status", table_name="enrollment_applications")
    op.drop_column("enrollment_applications", "rejected_at")
    op.drop_column("enrollment_applications", "accepted_at")
