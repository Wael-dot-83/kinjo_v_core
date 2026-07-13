"""Regression tests for PostgreSQL-specific Alembic migration behavior."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, call, patch


def test_p2_replaces_all_semantically_equivalent_foreign_keys() -> None:
    migration_path = Path("alembic/versions/p2_fk_cascade_rules.py")
    spec = importlib.util.spec_from_file_location("p2_fk_cascade_rules", migration_path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    inspector = MagicMock()
    inspector.get_foreign_keys.return_value = [
        {
            "name": "fk_users_deleted_by_users",
            "constrained_columns": ["deleted_by"],
            "referred_table": "users",
            "referred_columns": ["id"],
        },
        {
            "name": "users_deleted_by_fkey",
            "constrained_columns": ["deleted_by"],
            "referred_table": "users",
            "referred_columns": ["id"],
        },
        {
            "name": "unrelated_fk",
            "constrained_columns": ["owner_id"],
            "referred_table": "users",
            "referred_columns": ["id"],
        },
    ]

    with (
        patch.object(migration.op, "get_bind", return_value=MagicMock()),
        patch.object(migration.sa, "inspect", return_value=inspector),
        patch.object(migration.op, "drop_constraint") as drop_constraint,
        patch.object(migration.op, "create_foreign_key") as create_foreign_key,
    ):
        migration._recreate_fk(
            "users", "users_deleted_by_fkey", "deleted_by", "users", "id", "SET NULL"
        )

    assert drop_constraint.call_args_list == [
        call("fk_users_deleted_by_users", "users", type_="foreignkey"),
        call("users_deleted_by_fkey", "users", type_="foreignkey"),
    ]
    create_foreign_key.assert_called_once_with(
        "users_deleted_by_fkey",
        "users",
        "users",
        ["deleted_by"],
        ["id"],
        ondelete="SET NULL",
    )


def test_migrations_ci_checks_tip_and_full_chain_reversibility() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert workflow.count("verify_postgres_migration_state.py") == 3
    assert "alembic downgrade -1" in workflow
    assert "alembic downgrade base" in workflow
