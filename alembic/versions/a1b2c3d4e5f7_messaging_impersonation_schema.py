"""messaging_impersonation_schema

Adds:
- messages.scheduled_at / messages.queue_status  (scheduled sending)
- audit_logs.impersonated_by / impersonation_reason

NOTE: message_recipients table was already created in the initial squash
(db828d82089e) with the correct recipient_user_id column.  This migration
only adds the new columns to messages and audit_logs.

Revision ID: a1b2c3d4e5f7
Revises: a0b1c2d3e4f5
Create Date: 2026-05-15 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, None] = "a0b1c2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, col: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return any(c["name"] == col for c in insp.get_columns(table))


def _has_fk(table: str, name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return any(fk.get("name") == name for fk in insp.get_foreign_keys(table))


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # ── messages: scheduled sending ──────────────────────────────────────────
    if not _has_column("messages", "scheduled_at"):
        op.add_column("messages", sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True))
    if not _has_column("messages", "queue_status"):
        op.add_column("messages", sa.Column("queue_status", sa.String(20), nullable=True, server_default="SENT"))

    # ── audit_logs: impersonation ────────────────────────────────────────────
    if not _has_column("audit_logs", "impersonated_by"):
        op.add_column("audit_logs", sa.Column("impersonated_by", sa.Integer, nullable=True))
    if not _has_column("audit_logs", "impersonation_reason"):
        op.add_column("audit_logs", sa.Column("impersonation_reason", sa.String(255), nullable=True))

    # PostgreSQL: add FK constraint separately (SQLite ignores FK constraints)
    if dialect == "postgresql" and not _has_fk("audit_logs", "fk_audit_logs_impersonated_by"):
        op.create_foreign_key(
            "fk_audit_logs_impersonated_by",
            "audit_logs", "users",
            ["impersonated_by"], ["id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        if _has_fk("audit_logs", "fk_audit_logs_impersonated_by"):
            op.drop_constraint("fk_audit_logs_impersonated_by", "audit_logs", type_="foreignkey")

    if _has_column("audit_logs", "impersonation_reason"):
        op.drop_column("audit_logs", "impersonation_reason")
    if _has_column("audit_logs", "impersonated_by"):
        op.drop_column("audit_logs", "impersonated_by")

    if _has_column("messages", "queue_status"):
        op.drop_column("messages", "queue_status")
    if _has_column("messages", "scheduled_at"):
        op.drop_column("messages", "scheduled_at")
