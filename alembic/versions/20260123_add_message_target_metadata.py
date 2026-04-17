"""Add message targeting metadata fields

Revision ID: 20260123_add_message_target_metadata
Revises: 20260122_add_profile_complete_fields
Create Date: 2026-01-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260123_add_message_target_metadata"
down_revision: Union[str, None] = "20260122_add_profile_complete_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("target_mode", sa.String(length=50), nullable=True))
    op.add_column("messages", sa.Column("target_roles", sa.JSON(), nullable=True))
    op.add_column("messages", sa.Column("target_governorates", sa.JSON(), nullable=True))
    op.add_column("messages", sa.Column("target_kindergarten_ids", sa.JSON(), nullable=True))
    op.add_column("messages", sa.Column("target_search", sa.String(length=255), nullable=True))
    op.add_column("messages", sa.Column("recipient_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "recipient_count")
    op.drop_column("messages", "target_search")
    op.drop_column("messages", "target_kindergarten_ids")
    op.drop_column("messages", "target_governorates")
    op.drop_column("messages", "target_roles")
    op.drop_column("messages", "target_mode")
