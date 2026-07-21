"""canonicalize the capital governorate: kindergartens/reports.governorate "عمان" -> "العاصمة"

The Amman governorate's official Arabic administrative name is "العاصمة" (The Capital).
"عمان" is the *city* inside it. Historically the ``governorate`` string column stored the
city name "عمان" where the governorate name belonged — a value that is simply wrong, not
merely mis-displayed. That split the data from every layer that already used the correct
"العاصمة" (the canonical services/jordan_locations source, the static
static/data/jordan_admin_divisions.json, config aliases), producing inconsistent filters,
labels and drill-downs.

This migration corrects the persisted value in the **governorate column only**. It does NOT
touch ``district`` or ``area`` — those legitimately hold the city "عمان" and must keep it
(verified in the live dev database: kindergartens.district and .area store "عمان" for the
city and must stay unchanged). This is the scoped, governorate-context-only correction the
task requires, never an unscoped database-wide replacement of "عمان".

Scope verified against data/kinjo.db before writing:
  kindergartens.governorate : 325 rows == "عمان"  -> "العاصمة"
  reports.governorate       : 0 rows (empty)      -> no-op, included for future rows
  kindergartens.district    : 325 rows == "عمان"  -> UNTOUCHED (city)
  kindergartens.area        : "عمان" + address text -> UNTOUCHED (city / free text)

Idempotent: the upgrade filters on the legacy alias set, so a second run matches nothing.
Reversible: downgrade restores the pre-migration city-name form "عمان" for the capital.
Portable: plain UPDATE ... WHERE governorate IN (...) runs identically on PostgreSQL and
SQLite; no enum, no DDL, no dialect-specific SQL.

Revision ID: canon_gov_cap_01
Revises: c7d9e1a4b820
Create Date: 2026-07-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "canon_gov_cap_01"
down_revision: Union[str, None] = "c7d9e1a4b820"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Canonical governorate-context Arabic name for the capital.
_CANONICAL_AR = "العاصمة"

# Legacy stored forms of the capital governorate that must be corrected. The city name
# "عمان" is included here ONLY because it was mis-stored in the governorate column; the
# district/area columns are never touched by this migration, so the city keeps its name.
_LEGACY_FORMS = ("عمان", "عاصمة", "Amman", "amman", "AMMAN")

# Tables whose ``governorate`` string column holds governorate-context values.
_TABLES = ("kindergartens", "reports")


def _table_exists(bind, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def upgrade() -> None:
    bind = op.get_bind()
    for table in _TABLES:
        if not _table_exists(bind, table):
            continue
        bound = sa.text(
            f"UPDATE {table} SET governorate = :canonical WHERE governorate IN :legacy"
        ).bindparams(sa.bindparam("legacy", expanding=True))
        result = bind.execute(bound, {"canonical": _CANONICAL_AR, "legacy": list(_LEGACY_FORMS)})
        print(f"[canonicalize-capital] {table}.governorate: {result.rowcount} row(s) -> '{_CANONICAL_AR}'")


def downgrade() -> None:
    bind = op.get_bind()
    # Restore the pre-migration city-name form for the capital governorate.
    for table in _TABLES:
        if not _table_exists(bind, table):
            continue
        bound = sa.text(
            f"UPDATE {table} SET governorate = :city WHERE governorate = :canonical"
        )
        result = bind.execute(bound, {"city": "عمان", "canonical": _CANONICAL_AR})
        print(f"[canonicalize-capital:down] {table}.governorate: {result.rowcount} row(s) -> 'عمان'")
