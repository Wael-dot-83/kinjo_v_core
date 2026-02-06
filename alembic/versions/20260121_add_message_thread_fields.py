"""add_message_thread_fields

Revision ID: 20260121_add_message_thread_fields
Revises: 20260121_add_message_user_states
Create Date: 2026-01-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260121_add_message_thread_fields"
down_revision: Union[str, None] = "20260121_add_message_user_states"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.add_column(sa.Column("thread_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("reply_to_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_messages_thread_id", "messages", ["thread_id"], ["id"])
        batch_op.create_foreign_key("fk_messages_reply_to_id", "messages", ["reply_to_id"], ["id"])

    op.execute("UPDATE messages SET thread_id = id WHERE thread_id IS NULL")

    op.create_index("ix_messages_thread_id", "messages", ["thread_id"])
    op.create_index("ix_messages_reply_to_id", "messages", ["reply_to_id"])


def downgrade() -> None:
    op.drop_index("ix_messages_reply_to_id", table_name="messages")
    op.drop_index("ix_messages_thread_id", table_name="messages")

    with op.batch_alter_table("messages") as batch_op:
        batch_op.drop_constraint("fk_messages_reply_to_id", type_="foreignkey")
        batch_op.drop_constraint("fk_messages_thread_id", type_="foreignkey")
        batch_op.drop_column("reply_to_id")
        batch_op.drop_column("thread_id")
