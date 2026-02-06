"""add_composite_index_message_recipients

Revision ID: 3c56302e2240
Revises: 20260123_add_message_target_metadata
Create Date: 2026-01-25 07:19:14.095700

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3c56302e2240'
down_revision: Union[str, None] = '20260123_add_message_target_metadata'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_message_recipients_message_recipient", "message_recipients", ["message_id", "recipient_user_id"])


def downgrade() -> None:
    op.drop_index("ix_message_recipients_message_recipient", table_name="message_recipients")
