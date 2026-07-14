"""add incidents.status/owner_id and reports.district/area; rename a stale unique constraint

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

Unique constraints — autogenerate reported six (three, each listed twice). Verified against
a real PostgreSQL 15 database built through this chain: **none of them was missing.** All
three are already enforcing; only their declared shape or name disagreed with models.py.
So this migration adds no unique constraint at all.

  ai_features (entity_type, entity_id, feature_name)
      Enforced since d2e3f4a5b6c7 as a unique INDEX named idx_ai_features_entity_feature.
      models.py declared the same name as a UniqueConstraint. PostgreSQL keeps indexes and
      constraints in ONE relation namespace, so ADD CONSTRAINT under that name aborts with
      `relation "idx_ai_features_entity_feature" already exists`. Fixed in models.py by
      declaring the index it has always been. No DDL.

  governorate (slug)
      Enforced since h1m2026h01, which declared the column unique=True *and* index=True —
      that combination emits a unique INDEX (ix_governorate_slug), not a constraint.
      models.py omitted index=True, so metadata asked for a constraint the database never
      had; adding it would have built a second redundant unique index over one column.
      Fixed in models.py. No DDL.

  imported_kindergartens (name_ar, district, phone)
      Present and enforcing, but under the stale name
      uq_imported_kindergartens_name_city_phone. b2e9a2f60c27 renamed the *column* city to
      district; PostgreSQL silently repoints a constraint at a renamed column but keeps the
      constraint's own name, so the name has said "city" ever since while the definition
      reads UNIQUE (name_ar, district, phone). Same columns — a rename, not an add.

The lesson that cost the most here: **a unique index and a unique constraint enforce
identically, but autogenerate reports one as a missing instance of the other, forever.**
Every `add_constraint` in this drift report was a false positive. Trusting them would have
crashed the deploy outright, which the first PostgreSQL run of this migration duly did.

No data is merged or deleted anywhere in this migration.

Supported upgrade source — databases built through the Alembic revision chain, only.
That is not a preference, it is the contract the code already keeps: database.py's init_db()
refuses to call Base.metadata.create_all() when ENVIRONMENT is production and defers to
Alembic. A schema created directly from models.py metadata would already have these columns
and the corrected constraint name, so ADD COLUMN would fail on it — such a database is not
an upgrade source, and the rename below says so explicitly rather than failing obscurely.
Dev and test databases are create_all-built and disposable; they never take this path.

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


_OLD_IK_CONSTRAINT = "uq_imported_kindergartens_name_city_phone"
_NEW_IK_CONSTRAINT = "uq_imported_kindergartens_name_district_phone"


def _rename_ik_constraint(bind, old: str, new: str) -> None:
    """Rename the imported_kindergartens unique constraint, cheaply where possible.

    PostgreSQL renames the constraint and its backing index in place — no table scan, no
    index rebuild, and uniqueness is never lifted. SQLite has no RENAME CONSTRAINT, so
    batch mode recreates the table there; that is fine for a dev database.

    The name is looked up rather than assumed. This migration targets a database built by
    the Alembic chain (see the module docstring), where the constraint is still called
    `old`; but if it is already called `new` there is nothing to do, and if neither exists
    the database did not come from this chain and we say so plainly instead of failing on a
    confusing `constraint does not exist`.
    """
    names = {c["name"] for c in sa.inspect(bind).get_unique_constraints("imported_kindergartens")}
    if new in names:
        return
    if old not in names:
        raise RuntimeError(
            f"imported_kindergartens has neither {old!r} nor {new!r} (found: {sorted(names)}). "
            f"This migration supports databases built through the Alembic revision chain. A "
            f"schema created directly from models.py metadata is not a supported upgrade "
            f"source — see database.py:init_db(), which never calls create_all() in production."
        )
    if bind.dialect.name == "postgresql":
        op.execute(sa.text(f'ALTER TABLE imported_kindergartens RENAME CONSTRAINT "{old}" TO "{new}"'))
        return
    with op.batch_alter_table("imported_kindergartens", schema=None) as batch_op:
        batch_op.drop_constraint(old, type_="unique")
        batch_op.create_unique_constraint(new, ["name_ar", "district", "phone"])


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

    # --- imported_kindergartens: rename only ------------------------------------------
    # No unique constraint is added anywhere in this migration. ai_features and
    # governorate were reported as missing but are already enforced by unique indexes;
    # see the module docstring. Only this name is stale.
    _rename_ik_constraint(bind, _OLD_IK_CONSTRAINT, _NEW_IK_CONSTRAINT)


def downgrade() -> None:
    bind = op.get_bind()

    _rename_ik_constraint(bind, _NEW_IK_CONSTRAINT, _OLD_IK_CONSTRAINT)

    op.drop_column("reports", "area")
    op.drop_column("reports", "district")

    # drop the FK before the column it constrains
    with op.batch_alter_table("incidents", schema=None) as batch_op:
        batch_op.drop_constraint("fk_incidents_owner_id_users", type_="foreignkey")
        batch_op.drop_column("owner_id")

    op.drop_column("incidents", "status")
