"""add_message_user_states

Revision ID: 20260121_add_message_user_states
Revises: 91dc496f6a91
Create Date: 2026-01-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260121_add_message_user_states"
down_revision: Union[str, None] = "91dc496f6a91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "message_user_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "user_id", name="uq_message_user_state"),
    )
    op.create_index("ix_message_user_states_message_id", "message_user_states", ["message_id"])
    op.create_index("ix_message_user_states_user_id", "message_user_states", ["user_id"])
    op.create_index("ix_message_user_state_user_read", "message_user_states", ["user_id", "read_at"])
    op.create_index("ix_message_user_state_user_archived", "message_user_states", ["user_id", "archived_at"])
    op.create_index("ix_message_user_state_user_deleted", "message_user_states", ["user_id", "deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_message_user_state_user_deleted", table_name="message_user_states")
    op.drop_index("ix_message_user_state_user_archived", table_name="message_user_states")
    op.drop_index("ix_message_user_state_user_read", table_name="message_user_states")
    op.drop_index("ix_message_user_states_user_id", table_name="message_user_states")
    op.drop_index("ix_message_user_states_message_id", table_name="message_user_states")
    op.drop_table("message_user_states")
