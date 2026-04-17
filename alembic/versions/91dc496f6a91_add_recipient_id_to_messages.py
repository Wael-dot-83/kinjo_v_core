"""Add recipient_id to messages and enforce FK where supported.

Revision ID: 91dc496f6a91
Revises: f60ea34b032b
Create Date: 2026-01-20 23:42:36.904187
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "91dc496f6a91"
down_revision: Union[str, None] = "f60ea34b032b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(col.get("name") == column_name for col in inspector.get_columns(table_name))


def _recipient_fk_exists() -> bool:
    inspector = sa.inspect(op.get_bind())
    for fk in inspector.get_foreign_keys("messages"):
        constrained = fk.get("constrained_columns") or []
        referred_table = fk.get("referred_table")
        if constrained == ["recipient_id"] and referred_table == "users":
            return True
    return False


def upgrade() -> None:
    if not _column_exists("messages", "recipient_id"):
        op.add_column("messages", sa.Column("recipient_id", sa.Integer(), nullable=True))

    # SQLite cannot add FK constraints to an existing table without full rebuild.
    if op.get_bind().dialect.name != "sqlite" and not _recipient_fk_exists():
        op.create_foreign_key(
            "fk_messages_recipient_id_users",
            "messages",
            "users",
            ["recipient_id"],
            ["id"],
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite" and _recipient_fk_exists():
        op.drop_constraint("fk_messages_recipient_id_users", "messages", type_="foreignkey")

    if _column_exists("messages", "recipient_id"):
        if op.get_bind().dialect.name == "sqlite":
            with op.batch_alter_table("messages", recreate="always") as batch_op:
                batch_op.drop_column("recipient_id")
        else:
            op.drop_column("messages", "recipient_id")

