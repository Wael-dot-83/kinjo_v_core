"""Add announcement messaging with recipient fanout support.

Revision ID: 8f3cc3e78b4f
Revises: 20260121_add_message_indexes
Create Date: 2026-01-22 00:32:25.387145
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8f3cc3e78b4f"
down_revision: Union[str, None] = "20260121_add_message_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(col.get("name") == column_name for col in inspector.get_columns(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    inspector = sa.inspect(op.get_bind())
    return any(ix.get("name") == index_name for ix in inspector.get_indexes(table_name))


def upgrade() -> None:
    if not _table_exists("message_recipients"):
        op.create_table(
            "message_recipients",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("message_id", sa.Integer(), nullable=False),
            sa.Column("recipient_user_id", sa.Integer(), nullable=False),
            sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
            sa.ForeignKeyConstraint(["message_id"], ["messages.id"]),
            sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("message_id", "recipient_user_id", name="uq_message_recipient"),
        )

    op.create_index("ix_message_recipients_id", "message_recipients", ["id"], unique=False, if_not_exists=True)
    op.create_index("ix_message_recipients_message_id", "message_recipients", ["message_id"], unique=False, if_not_exists=True)
    op.create_index(
        "ix_message_recipients_recipient_user_id",
        "message_recipients",
        ["recipient_user_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index("ix_message_recipients_status", "message_recipients", ["status"], unique=False, if_not_exists=True)

    if not _column_exists("messages", "allow_replies"):
        op.add_column(
            "messages",
            sa.Column(
                "allow_replies",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
        )

    # SQLite cannot alter enum types directly; keep the existing VARCHAR there.
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column(
            "messages",
            "thread_type",
            existing_type=sa.VARCHAR(length=9),
            type_=sa.Enum("DIRECT", "ANNOUNCEMENT", "CLASS", "BROADCAST", name="messagethreadtype"),
            existing_nullable=False,
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column(
            "messages",
            "thread_type",
            existing_type=sa.Enum("DIRECT", "ANNOUNCEMENT", "CLASS", "BROADCAST", name="messagethreadtype"),
            type_=sa.VARCHAR(length=9),
            existing_nullable=False,
        )

    if _column_exists("messages", "allow_replies"):
        op.drop_column("messages", "allow_replies")

    op.drop_index("ix_message_recipients_status", table_name="message_recipients", if_exists=True)
    op.drop_index("ix_message_recipients_recipient_user_id", table_name="message_recipients", if_exists=True)
    op.drop_index("ix_message_recipients_message_id", table_name="message_recipients", if_exists=True)
    op.drop_index("ix_message_recipients_id", table_name="message_recipients", if_exists=True)
    if _table_exists("message_recipients"):
        op.drop_table("message_recipients")
