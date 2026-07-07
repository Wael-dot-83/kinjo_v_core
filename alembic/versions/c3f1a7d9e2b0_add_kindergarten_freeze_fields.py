"""add kindergarten freeze fields and FROZEN status

Revision ID: c3f1a7d9e2b0
Revises: b2e9a2f60c27
Create Date: 2026-07-07 12:10:00.000000

Adds the reversible-freeze support for the Kindergarten Management module
(FRD §1.4):
  - kindergartens.frozen_at      (marker of record for a freeze)
  - kindergartens.frozen_reason  (optional admin justification)
  - KindergartenStatus enum gains 'FROZEN' (PostgreSQL native enum only;
    SQLite stores the status as VARCHAR with no CHECK constraint so no
    schema change is required there).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3f1a7d9e2b0"
down_revision: Union[str, None] = "b2e9a2f60c27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    with op.batch_alter_table("kindergartens") as batch_op:
        batch_op.add_column(sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("frozen_reason", sa.String(length=255), nullable=True))

    # PostgreSQL uses a native enum type; add the new value. SQLite/others
    # store the status as a plain string, so nothing else is needed.
    if dialect == "postgresql":
        op.execute("ALTER TYPE kindergartenstatus ADD VALUE IF NOT EXISTS 'FROZEN'")


def downgrade() -> None:
    with op.batch_alter_table("kindergartens") as batch_op:
        batch_op.drop_column("frozen_reason")
        batch_op.drop_column("frozen_at")
    # Note: PostgreSQL cannot easily drop a value from an enum type; the
    # 'FROZEN' label is left in place on downgrade (harmless).
