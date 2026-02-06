"""add_recipient_id_to_messages

Revision ID: 91dc496f6a91
Revises: f60ea34b032b
Create Date: 2026-01-20 23:42:36.904187

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '91dc496f6a91'
down_revision: Union[str, None] = 'f60ea34b032b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # For SQLite, we need to recreate the table to add foreign key constraints
    with op.batch_alter_table('messages') as batch_op:
        batch_op.add_column(sa.Column('recipient_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_messages_recipient_id', 'users', ['recipient_id'], ['id'])


def downgrade() -> None:
    # For SQLite, we need to recreate the table to remove foreign key constraints
    with op.batch_alter_table('messages') as batch_op:
        batch_op.drop_constraint('fk_messages_recipient_id', type_='foreignkey')
        batch_op.drop_column('recipient_id')
