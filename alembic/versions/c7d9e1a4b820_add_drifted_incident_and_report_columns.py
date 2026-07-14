"""add incidents.status/owner_id and reports.district/area + two missing unique constraints

These columns are declared in models.py but no migration ever created them, so a database
built from the migration chain does not have them. This is the same class of fresh-deploy
failure as incident_history (1417f512f696), and it is live code, not speculative:

  incidents.status   — 199 references. Incident list filtering reads it, updates write it,
                       and incident_history records status_from/status_to transitions.
  incidents.owner_id — safety_service.py assigns it on incident update
                       (`incident.owner_id = update_data.owner_id`).
  reports.district   — 40 references.
  reports.area       — 59 references.

It only works in dev because Base.metadata.create_all() makes the columns there.

status is backfilled to 'OPEN', not 'Open'. SQLAlchemy's Enum persists the member NAME,
not its value ("Open"), which the live data confirms: the only value present in
data/kinjo.db is 'OPEN'. Backfilling the value would have failed the NOT NULL step.

status carries no server_default. models.py declares a Python-side
`default=IncidentStatus.OPEN` only, so leaving a server default behind would put the
schema permanently out of step with the model and re-open drift. The default here is
temporary, applied only to fill existing rows, then dropped.

The incidentstatus enum type already exists on PostgreSQL: 1417f512f696 created it while
creating incident_history, which references the same `name='incidentstatus'`. So this
migration must NOT recreate it (create_type=False) — a second CREATE TYPE would abort the
deploy. On SQLite the enum is a VARCHAR + CHECK and the question does not arise.

Unique constraints — investigated individually rather than trusting autogenerate, which
reported six (three, each twice):

  ai_features (entity_type, entity_id, feature_name) — genuinely absent. Added.
  governorate (slug)                                 — genuinely absent. Added.
  imported_kindergartens (name_ar, district, phone)  — NOT missing. It is already there and
      already enforcing, but under the stale name `uq_imported_kindergartens_name_city_phone`
      while models.py expects `uq_imported_kindergartens_name_district_phone` — the name was
      never updated when city became district. Same columns, so this is a rename, not an add.

Names matter more than they look: a constraint whose name does not match models.py is
reported as missing forever, which is exactly how imported_kindergartens hid in the drift
list while enforcing correctly the whole time. Both added constraints use the model's own
name for that reason.

The added constraints are duplicate-checked first and abort with the offending keys rather
than destroying rows. No data is merged or deleted automatically.

Revision ID: c7d9e1a4b820
Revises: 1417f512f696
Create Date: 2026-07-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c7d9e1a4b820"
down_revision: Union[str, None] = "1417f512f696"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATUS_LABELS = ("OPEN", "UNDER_INVESTIGATION", "ACTION_REQUIRED", "RESOLVED", "CLOSED")


def _status_type(bind):
    """The incidentstatus enum, reusing the type PostgreSQL already has."""
    if bind.dialect.name == "postgresql":
        return postgresql.ENUM(*_STATUS_LABELS, name="incidentstatus", create_type=False)
    return sa.Enum(*_STATUS_LABELS, name="incidentstatus")


def _abort_on_duplicates(bind, table: str, columns: str) -> None:
    """Refuse to add a unique constraint over data that violates it."""
    rows = bind.execute(
        sa.text(
            f"SELECT {columns}, COUNT(*) AS n FROM {table} "
            f"GROUP BY {columns} HAVING COUNT(*) > 1"
        )
    ).fetchall()
    if rows:
        keys = "; ".join(str(tuple(r[:-1])) for r in rows[:10])
        raise RuntimeError(
            f"Cannot add a unique constraint on {table}({columns}): "
            f"{len(rows)} duplicate group(s) exist. Resolve them deliberately — this "
            f"migration will not merge or delete rows. Offending keys: {keys}"
        )


def upgrade() -> None:
    bind = op.get_bind()

    # --- incidents.status: add nullable, backfill, then enforce NOT NULL ---------------
    op.add_column("incidents", sa.Column("status", _status_type(bind), nullable=True))
    op.execute(sa.text("UPDATE incidents SET status = 'OPEN' WHERE status IS NULL"))
    with op.batch_alter_table("incidents", schema=None) as batch_op:
        batch_op.alter_column(
            "status", existing_type=_status_type(bind), nullable=False
        )

    # --- incidents.owner_id: nullable FK, existing rows stay NULL ---------------------
    with op.batch_alter_table("incidents", schema=None) as batch_op:
        batch_op.add_column(sa.Column("owner_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_incidents_owner_id_users", "users", ["owner_id"], ["id"]
        )

    # --- reports.district / reports.area: nullable, no backfill ------------------------
    # Report scope cannot be derived reliably for existing rows, so they stay NULL rather
    # than being guessed at.
    op.add_column("reports", sa.Column("district", sa.String(length=100), nullable=True))
    op.add_column("reports", sa.Column("area", sa.String(length=100), nullable=True))

    # --- the two genuinely-missing unique constraints ----------------------------------
    # Names must match models.py exactly, or autogenerate keeps reporting drift for a
    # constraint that is actually present — which is how imported_kindergartens below
    # ended up looking "missing" for months.
    _abort_on_duplicates(bind, "ai_features", "entity_type, entity_id, feature_name")
    with op.batch_alter_table("ai_features", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "idx_ai_features_entity_feature", ["entity_type", "entity_id", "feature_name"]
        )

    _abort_on_duplicates(bind, "governorate", "slug")
    with op.batch_alter_table("governorate", schema=None) as batch_op:
        batch_op.create_unique_constraint("uq_governorate_slug", ["slug"])

    # --- imported_kindergartens: rename, do not re-add --------------------------------
    # The constraint is present and correct; only its name is stale — it still says
    # "city" after the city->district rename, while models.py expects "district". Same
    # columns, so this is a rename, and dropping/recreating it under batch mode keeps the
    # uniqueness guarantee for the whole operation.
    with op.batch_alter_table("imported_kindergartens", schema=None) as batch_op:
        batch_op.drop_constraint(
            "uq_imported_kindergartens_name_city_phone", type_="unique"
        )
        batch_op.create_unique_constraint(
            "uq_imported_kindergartens_name_district_phone",
            ["name_ar", "district", "phone"],
        )


def downgrade() -> None:
    with op.batch_alter_table("imported_kindergartens", schema=None) as batch_op:
        batch_op.drop_constraint(
            "uq_imported_kindergartens_name_district_phone", type_="unique"
        )
        batch_op.create_unique_constraint(
            "uq_imported_kindergartens_name_city_phone", ["name_ar", "district", "phone"]
        )

    with op.batch_alter_table("governorate", schema=None) as batch_op:
        batch_op.drop_constraint("uq_governorate_slug", type_="unique")

    with op.batch_alter_table("ai_features", schema=None) as batch_op:
        batch_op.drop_constraint("idx_ai_features_entity_feature", type_="unique")

    op.drop_column("reports", "area")
    op.drop_column("reports", "district")

    # drop the FK before the column it constrains
    with op.batch_alter_table("incidents", schema=None) as batch_op:
        batch_op.drop_constraint("fk_incidents_owner_id_users", type_="foreignkey")
        batch_op.drop_column("owner_id")

    op.drop_column("incidents", "status")
