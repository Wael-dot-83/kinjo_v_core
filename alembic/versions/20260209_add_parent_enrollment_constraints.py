"""Add enrollment uniqueness and parent identifiers.

Revision ID: 20260209_add_parent_enrollment_constraints
Revises: 20260206_add_analytics_enhancements
Create Date: 2026-02-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = "20260209_add_parent_enrollment_constraints"
down_revision = "20260206_add_analytics_enhancements"
branch_labels = None
depends_on = None


ACTIVE_STATUSES = ("SUBMITTED", "PENDING_REVIEW", "ACCEPTED", "ACTIVE")


def _cleanup_duplicate_parent_national_ids(conn) -> None:
    # Normalize empty strings to NULL.
    conn.execute(text("UPDATE parent_profiles SET national_id = NULL WHERE national_id = ''"))
    rows = conn.execute(text(
        """
        SELECT national_id, MIN(id) AS keep_id
        FROM parent_profiles
        WHERE national_id IS NOT NULL
        GROUP BY national_id
        HAVING COUNT(*) > 1
        """
    )).fetchall()
    for row in rows:
        conn.execute(
            text(
                """
                UPDATE parent_profiles
                SET national_id = NULL
                WHERE national_id = :national_id AND id != :keep_id
                """
            ),
            {"national_id": row.national_id, "keep_id": row.keep_id},
        )


def _cleanup_duplicate_enrollments(conn) -> None:
    rows = conn.execute(text(
        """
        SELECT child_id, kindergarten_id, MAX(id) AS keep_id
        FROM enrollment_applications
        GROUP BY child_id, kindergarten_id
        HAVING COUNT(*) > 1
        """
    )).fetchall()
    for row in rows:
        dup_ids = conn.execute(text(
            """
            SELECT id FROM enrollment_applications
            WHERE child_id = :child_id AND kindergarten_id = :kindergarten_id AND id != :keep_id
            """
        ), {
            "child_id": row.child_id,
            "kindergarten_id": row.kindergarten_id,
            "keep_id": row.keep_id,
        }).fetchall()
        for dup in dup_ids:
            conn.execute(text("DELETE FROM waitlist_entries WHERE enrollment_id = :eid"), {"eid": dup.id})
            conn.execute(text("DELETE FROM enrollment_applications WHERE id = :eid"), {"eid": dup.id})


def _resolve_multiple_active_enrollments(conn) -> None:
    rows = conn.execute(text(
        """
        SELECT child_id, MAX(id) AS keep_id
        FROM enrollment_applications
        WHERE status IN :active_statuses
        GROUP BY child_id
        HAVING COUNT(*) > 1
        """
    ).bindparams(sa.bindparam("active_statuses", expanding=True))
    , {"active_statuses": ACTIVE_STATUSES}).fetchall()

    for row in rows:
        # Mark older active enrollments as withdrawn.
        conn.execute(text(
            """
            UPDATE enrollment_applications
            SET status = 'WITHDRAWN', status_reason = 'Auto-withdrawn to enforce single active enrollment'
            WHERE child_id = :child_id AND id != :keep_id AND status IN :active_statuses
            """
        ).bindparams(sa.bindparam("active_statuses", expanding=True))
        , {
            "child_id": row.child_id,
            "keep_id": row.keep_id,
            "active_statuses": ACTIVE_STATUSES,
        })


def _sync_is_active(conn) -> None:
    # Mark active-like statuses with is_active = 1, others NULL.
    conn.execute(text("UPDATE enrollment_applications SET is_active = NULL"))
    conn.execute(text(
        """
        UPDATE enrollment_applications
        SET is_active = 1
        WHERE status IN :active_statuses
        """
    ).bindparams(sa.bindparam("active_statuses", expanding=True))
    , {"active_statuses": ACTIVE_STATUSES})


def upgrade() -> None:
    conn = op.get_bind()

    # Add is_active column (nullable to allow multiple inactive rows per child).
    op.add_column("enrollment_applications", sa.Column("is_active", sa.Boolean(), nullable=True))

    _cleanup_duplicate_parent_national_ids(conn)
    _cleanup_duplicate_enrollments(conn)
    _resolve_multiple_active_enrollments(conn)
    _sync_is_active(conn)

    with op.batch_alter_table("enrollment_applications") as batch_op:
        batch_op.create_unique_constraint(
            "uq_enrollment_child_kindergarten",
            ["child_id", "kindergarten_id"],
        )
        batch_op.create_index(
            "uq_enrollment_child_active",
            ["child_id", "is_active"],
            unique=True,
        )
        batch_op.create_index("ix_enrollment_child_id", ["child_id"])
        batch_op.create_index("ix_enrollment_child_status", ["child_id", "status"])

    with op.batch_alter_table("parent_profiles") as batch_op:
        batch_op.create_index(
            "uq_parent_profiles_national_id",
            ["national_id"],
            unique=True,
        )
        batch_op.create_index(
            "ix_parent_profiles_phone_number",
            ["phone_number"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("parent_profiles") as batch_op:
        batch_op.drop_index("ix_parent_profiles_phone_number")
        batch_op.drop_index("uq_parent_profiles_national_id")

    with op.batch_alter_table("enrollment_applications") as batch_op:
        batch_op.drop_index("ix_enrollment_child_status")
        batch_op.drop_index("ix_enrollment_child_id")
        batch_op.drop_index("uq_enrollment_child_active")
        batch_op.drop_constraint("uq_enrollment_child_kindergarten", type_="unique")
        batch_op.drop_column("is_active")
