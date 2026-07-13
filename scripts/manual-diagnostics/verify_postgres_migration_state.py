"""Verify semantic invariants that Alembic must establish on PostgreSQL."""

from __future__ import annotations

import os
import sys
from collections import defaultdict

import sqlalchemy as sa


EXPECTED_DELETE_RULES = {
    ("users", ("deleted_by",), "users", ("id",)): "SET NULL",
    ("parent_profiles", ("deleted_by",), "users", ("id",)): "SET NULL",
    ("children", ("deleted_by",), "users", ("id",)): "SET NULL",
    ("parent_profiles", ("user_id",), "users", ("id",)): "CASCADE",
    ("password_reset_tokens", ("user_id",), "users", ("id",)): "CASCADE",
    ("user_dashboard_preferences", ("user_id",), "users", ("id",)): "CASCADE",
    ("user_filter_preferences", ("user_id",), "users", ("id",)): "CASCADE",
    ("supervisor_profiles", ("user_id",), "users", ("id",)): "CASCADE",
    ("supervisor_profiles", ("kindergarten_id",), "kindergartens", ("id",)): "CASCADE",
}


def main() -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is required", file=sys.stderr)
        return 2

    engine = sa.create_engine(database_url)
    if engine.dialect.name != "postgresql":
        print("This verifier must run against PostgreSQL", file=sys.stderr)
        return 2

    grouped: dict[tuple, list[dict]] = defaultdict(list)
    with engine.connect() as connection:
        inspector = sa.inspect(connection)
        for table in inspector.get_table_names(schema="public"):
            for foreign_key in inspector.get_foreign_keys(table, schema="public"):
                key = (
                    table,
                    tuple(foreign_key["constrained_columns"]),
                    foreign_key["referred_table"],
                    tuple(foreign_key["referred_columns"]),
                )
                grouped[key].append(foreign_key)

    errors: list[str] = []
    for key, foreign_keys in grouped.items():
        if len(foreign_keys) > 1:
            names = ", ".join(str(item.get("name")) for item in foreign_keys)
            errors.append(f"duplicate equivalent foreign keys for {key}: {names}")

    for key, expected_rule in EXPECTED_DELETE_RULES.items():
        foreign_keys = grouped.get(key, [])
        if len(foreign_keys) != 1:
            errors.append(f"expected exactly one foreign key for {key}, found {len(foreign_keys)}")
            continue
        actual_rule = (foreign_keys[0].get("options") or {}).get("ondelete")
        if (actual_rule or "NO ACTION").upper() != expected_rule:
            errors.append(
                f"wrong ON DELETE rule for {key}: expected {expected_rule}, got {actual_rule or 'NO ACTION'}"
            )

    if errors:
        print("PostgreSQL migration semantic checks failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("PostgreSQL migration semantic checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
