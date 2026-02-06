"""add_message_attachments_notifications

Revision ID: 20260121_add_message_attachments_notifications
Revises: 20260121_add_message_thread_fields
Create Date: 2026-01-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260121_add_message_attachments_notifications"
down_revision: Union[str, None] = "20260121_add_message_thread_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "message_attachments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_id", sa.Integer(), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("storage_provider", sa.String(length=50), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_message_attachments_message_id", "message_attachments", ["message_id"])
    op.create_index("ix_message_attachments_uploaded_by", "message_attachments", ["uploaded_by_id"])

    op.create_table(
        "user_device_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(length=500), nullable=False),
        sa.Column("platform", sa.Enum("IOS", "ANDROID", "WEB", name="deviceplatform"), nullable=False),
        sa.Column("device_name", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )
    op.create_index("ix_user_device_tokens_user_id", "user_device_tokens", ["user_id"])
    op.create_index("ix_user_device_tokens_platform", "user_device_tokens", ["platform"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("channel", sa.Enum("EMAIL", "PUSH", "IN_APP", name="notificationchannel"), nullable=False),
        sa.Column("status", sa.Enum("PENDING", "SENT", "FAILED", name="notificationstatus"), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_user_status", "notifications", ["user_id", "status"])
    op.create_index("ix_notifications_message", "notifications", ["message_id"])
    op.create_index("ix_notifications_channel", "notifications", ["channel"])


def downgrade() -> None:
    op.drop_index("ix_notifications_channel", table_name="notifications")
    op.drop_index("ix_notifications_message", table_name="notifications")
    op.drop_index("ix_notifications_user_status", table_name="notifications")
    op.drop_table("notifications")

    op.drop_index("ix_user_device_tokens_platform", table_name="user_device_tokens")
    op.drop_index("ix_user_device_tokens_user_id", table_name="user_device_tokens")
    op.drop_table("user_device_tokens")

    op.drop_index("ix_message_attachments_uploaded_by", table_name="message_attachments")
    op.drop_index("ix_message_attachments_message_id", table_name="message_attachments")
    op.drop_table("message_attachments")
