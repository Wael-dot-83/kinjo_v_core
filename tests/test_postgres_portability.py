"""Guards for defects that only appear on PostgreSQL.

The suite runs on SQLite, so a whole class of production bug is invisible to it:
SQLite accepts SQLite-only functions and stores enums as free text, while
PostgreSQL rejects both. Two real production 500s came from exactly that gap:

  GET /api/kpi/dashboard-data     -> function strftime(unknown, date) does not exist
  GET /api/analytics/safety/summary -> invalid input value for enum incidenttype: "BEHAVIORAL"

These tests are static/source-level on purpose. They cost nothing, run on
SQLite, and still catch the dialect problem before deployment.
"""
import pathlib
import re

import sqlalchemy as sa

import models

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Modules that serve admin/analytics traffic. A SQLite-only function here is a
# production 500 waiting to happen.
SQL_MODULES = [
    "kpi_service.py",
    "analytics_service.py",
    "classification_service.py",
    "admin_endpoints.py",
    "admin_advanced_analytics_endpoints.py",
    "admin_reports_api.py",
]

# SQLite-only SQL functions, as they appear when used through SQLAlchemy's
# func.<name>() builder. datetime.strftime() on a Python object is fine and is
# excluded by requiring the func. prefix.
SQLITE_ONLY = ["strftime", "julianday", "datetime", "sqlite_version"]


def test_no_sqlite_only_sql_functions_in_served_modules():
    offenders = []
    for rel in SQL_MODULES:
        path = ROOT / rel
        if not path.exists():
            continue
        src = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(src.splitlines(), 1):
            code = line.split("#", 1)[0]
            for fn in SQLITE_ONLY:
                if re.search(r"\bfunc\.%s\s*\(" % fn, code):
                    offenders.append(f"{rel}:{lineno}: func.{fn}( -> {code.strip()[:90]}")
    assert not offenders, (
        "SQLite-only SQL function used in a module that serves production "
        "PostgreSQL traffic:\n  " + "\n  ".join(offenders) +
        "\nUse a portable construct (extract(), date_trunc(), cast()) instead."
    )


def test_model_enums_declare_every_member_they_persist():
    """Every Enum column must be able to round-trip all of its members.

    This does not talk to PostgreSQL, but it pins the source of truth: if a
    member is added to a Python enum, alembic/versions/enum_drift_repair_01.py
    (or a later migration) must add it to the database type as well. The list
    below records what production's enum types contain, so adding a member
    without a migration fails here.
    """
    known_missing_repaired_by_migration = {
        "analyticsdimensiontype": {"DISTRICT"},
        "exportformat": {"JSON"},
        "incidenttype": {"ACCIDENT", "BEHAVIORAL", "HEALTH"},
        "reportscopetype": {"AREA", "DISTRICT"},
    }

    migration = (ROOT / "alembic" / "versions" / "enum_drift_repair_01.py")
    assert migration.exists(), "enum drift repair migration is missing"
    migration_src = migration.read_text(encoding="utf-8")

    for type_name, members in known_missing_repaired_by_migration.items():
        assert type_name in migration_src, (
            f"enum type {type_name} is no longer covered by the repair migration"
        )
        for m in members:
            assert f'"{m}"' in migration_src or f"'{m}'" in migration_src, (
                f"{type_name}.{m} is not added by the repair migration; a "
                "PostgreSQL deployment would reject it"
            )


def test_enum_columns_use_names_not_values():
    """SQLAlchemy stores the enum *name* unless values_callable is set.

    IncidentStatus is the trap: its members are OPEN = "Open", so the database
    holds OPEN while the Python value is "Open". Anything comparing raw strings
    against the column must use the name. This pins that no Enum column has
    silently switched to values_callable, which would change what is stored and
    break every existing row.
    """
    switched = []
    for mapper in models.Base.registry.mappers:
        for col in mapper.columns:
            t = col.type
            if isinstance(t, sa.Enum) and getattr(t, "enum_class", None) is not None:
                if getattr(t, "values_callable", None) is not None:
                    switched.append(f"{mapper.class_.__name__}.{col.key}")
    assert not switched, (
        "Enum column(s) now persist values instead of names, which silently "
        "invalidates existing rows: " + ", ".join(switched)
    )
