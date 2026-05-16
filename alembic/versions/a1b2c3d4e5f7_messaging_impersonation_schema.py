"""messaging_impersonation_schema

Adds:
- messages.scheduled_at / messages.queue_status  (scheduled sending)
- message_recipients table                        (per-recipient delivery + read tracking)
- audit_logs.impersonated_by / impersonation_reason

Revision ID: a1b2c3d4e5f7
Revises: f4b7a9c2d613
Create Date: 2026-05-15 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, None] = "a0b1c2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # ── messages: scheduled sending ──────────────────────────────────────────
    # Use direct ADD COLUMN — avoids batch-mode table recreation and the
    # "Constraint must have a name" error that SQLite raises when batch mode
    # introspects unnamed FK constraints on the existing messages table.
    op.add_column("messages", sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("messages", sa.Column("queue_status", sa.String(20), nullable=True, server_default="SENT"))

    # ── message_recipients ───────────────────────────────────────────────────
    op.create_table(
        "message_recipients",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("message_id", sa.Integer, sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recipient_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("message_id", "recipient_id", name="uq_message_recipient"),
    )
    op.create_index("ix_message_recipients_message", "message_recipients", ["message_id"])
    op.create_index("ix_message_recipients_recipient", "message_recipients", ["recipient_id"])

    # ── audit_logs: impersonation ────────────────────────────────────────────
    # Direct ADD COLUMN — no constraint changes, so no batch mode needed.
    op.add_column("audit_logs", sa.Column("impersonated_by", sa.Integer, nullable=True))
    op.add_column("audit_logs", sa.Column("impersonation_reason", sa.String(255), nullable=True))

    # PostgreSQL: add the FK constraint separately (SQLite ignores FK constraints)
    if dialect == "postgresql":
        op.create_foreign_key(
            "fk_audit_logs_impersonated_by",
            "audit_logs", "users",
            ["impersonated_by"], ["id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.drop_constraint("fk_audit_logs_impersonated_by", "audit_logs", type_="foreignkey")

    op.drop_column("audit_logs", "impersonation_reason")
    op.drop_column("audit_logs", "impersonated_by")

    op.drop_index("ix_message_recipients_recipient", table_name="message_recipients")
    op.drop_index("ix_message_recipients_message", table_name="message_recipients")
    op.drop_table("message_recipients")

    op.drop_column("messages", "queue_status")
    op.drop_column("messages", "scheduled_at")
