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


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return False
    return any(idx.get("name") == index_name for idx in inspector.get_indexes(table_name))


def _fk_exists(table_name: str, fk_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return False
    return any(fk.get("name") == fk_name for fk in inspector.get_foreign_keys(table_name))


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return False
    return any(col.get("name") == column_name for col in inspector.get_columns(table_name))


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
    if _index_exists("messages", "ix_messages_reply_to_id"):
        op.drop_index("ix_messages_reply_to_id", table_name="messages")
    if _index_exists("messages", "ix_messages_thread_id"):
        op.drop_index("ix_messages_thread_id", table_name="messages")

    with op.batch_alter_table("messages") as batch_op:
        if _fk_exists("messages", "fk_messages_reply_to_id"):
            batch_op.drop_constraint("fk_messages_reply_to_id", type_="foreignkey")
        if _fk_exists("messages", "fk_messages_thread_id"):
            batch_op.drop_constraint("fk_messages_thread_id", type_="foreignkey")
        if _column_exists("messages", "reply_to_id"):
            batch_op.drop_column("reply_to_id")
        if _column_exists("messages", "thread_id"):
            batch_op.drop_column("thread_id")
