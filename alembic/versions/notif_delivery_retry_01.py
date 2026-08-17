"""Add durable notification delivery retry and lease state.

Revision ID: notif_delivery_retry_01
Revises: ncfa_snap_01
Create Date: 2026-08-16
"""

from alembic import op
import sqlalchemy as sa


revision = "notif_delivery_retry_01"
down_revision = "ncfa_snap_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "delivery_attempts",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch_op.add_column(sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("dispatch_claimed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("dispatch_claim_token", sa.String(length=64), nullable=True))
        batch_op.create_index(
            "ix_notifications_retry_due",
            ["status", "channel", "next_retry_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.drop_index("ix_notifications_retry_due")
        batch_op.drop_column("dispatch_claim_token")
        batch_op.drop_column("dispatch_claimed_at")
        batch_op.drop_column("next_retry_at")
        batch_op.drop_column("last_attempt_at")
        batch_op.drop_column("delivery_attempts")
