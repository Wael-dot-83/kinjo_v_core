"""Add enum values that exist in the models but were never added to PostgreSQL.

The Python enums gained members without a matching migration, so PostgreSQL's
enum types fell behind. Any query or insert using one of the missing members
fails with InvalidTextRepresentation and surfaces as a 500 — this is what broke
GET /api/analytics/safety/summary in production, which filters incidents by
IncidentType.BEHAVIORAL.

The test suite could not catch this: tests run on SQLite, which stores enums as
plain text and accepts any member.

SQLAlchemy persists the enum *name*, so these are names, not values. Additive
only: no value is renamed or removed, so the migration is safe to re-run and
safe to roll back by simply leaving the values in place (PostgreSQL cannot drop
an enum value, hence the no-op downgrade).

Revision ID: enum_drift_repair_01
Revises: meal_times_late_reason_01
"""
from alembic import op
import sqlalchemy as sa

revision = "enum_drift_repair_01"
down_revision = "meal_times_late_reason_01"
branch_labels = None
depends_on = None


# enum type -> member names that must exist
MISSING = {
    "analyticsdimensiontype": ["DISTRICT"],
    "exportformat": ["JSON"],
    "incidenttype": ["ACCIDENT", "BEHAVIORAL", "HEALTH"],
    "reportscopetype": ["AREA", "DISTRICT"],
}


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite has no enum types; nothing to repair.
        return

    for type_name, members in MISSING.items():
        exists = bind.execute(
            sa.text("SELECT 1 FROM pg_type WHERE typname = :t"), {"t": type_name}
        ).scalar()
        if not exists:
            continue
        for member in members:
            # IF NOT EXISTS keeps this idempotent; PostgreSQL 12+ allows
            # ADD VALUE inside a transaction as long as the new value is not
            # used in that same transaction, which it is not here.
            op.execute(
                sa.text(
                    f"ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS '{member}'"
                )
            )


def downgrade() -> None:
    # PostgreSQL cannot remove a value from an enum type. Leaving the added
    # members in place is harmless: nothing references them after a downgrade.
    pass
