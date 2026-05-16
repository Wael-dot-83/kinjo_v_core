"""add_parent_notification_language

Revision ID: f4b7a9c2d613
Revises: e2b15dd3c429
Create Date: 2026-04-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4b7a9c2d613"
down_revision: Union[str, None] = "e2b15dd3c429"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "parent_profiles",
        sa.Column("notification_language", sa.String(length=10), nullable=False, server_default="ar"),
    )


def downgrade() -> None:
    op.drop_column("parent_profiles", "notification_language")
