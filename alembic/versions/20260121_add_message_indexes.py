"""add_message_indexes

Revision ID: 20260121_add_message_indexes
Revises: 20260121_add_message_attachments_notifications
Create Date: 2026-01-21

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260121_add_message_indexes"
down_revision: Union[str, None] = "20260121_add_message_attachments_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_messages_kindergarten_created_at", "messages", ["kindergarten_id", "created_at"], if_not_exists=True)
    op.create_index("ix_messages_sender_id", "messages", ["sender_id"], if_not_exists=True)
    op.create_index("ix_messages_recipient_id", "messages", ["recipient_id"], if_not_exists=True)
    op.create_index("ix_messages_thread_id", "messages", ["thread_id"], if_not_exists=True)
    op.create_index("ix_messages_thread_type", "messages", ["thread_type"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("ix_messages_thread_type", table_name="messages", if_exists=True)
    op.drop_index("ix_messages_thread_id", table_name="messages", if_exists=True)
    op.drop_index("ix_messages_recipient_id", table_name="messages", if_exists=True)
    op.drop_index("ix_messages_sender_id", table_name="messages", if_exists=True)
    op.drop_index("ix_messages_kindergarten_created_at", table_name="messages", if_exists=True)
