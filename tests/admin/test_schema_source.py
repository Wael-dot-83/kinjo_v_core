"""#97 — the Postgres test schema must come from Alembic, not create_all.

A performance test is only worth the electricity if it measures the schema that
ships. Before this guard, every test database was built by
``Base.metadata.create_all``: 87 tables and 378 indexes against production's 95
and 436. Seventy-nine real indexes existed in production and in no test
database, so an index migration could land and no test would ever see it.

These tests fail loudly if that regresses. They skip on SQLite, which is the
default path and is not expected to carry the migration-built schema.
"""

import os

import pytest
from sqlalchemy import text

from conftest import _IS_POSTGRES, engine

pytestmark = pytest.mark.skipif(
    not _IS_POSTGRES,
    reason="schema-source guard applies to the TEST_DATABASE_URL Postgres path",
)

# Declared only in alembic/versions/g1h2i3j4k5l6_performance_indexes.py and in
# no models.py __table_args__. create_all cannot produce it, so its presence is
# proof the schema came from the migration chain.
MIGRATION_ONLY_INDEX = "ix_enrollment_applications_kg_status"


def _index_names() -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
        )
        return {r[0] for r in rows}


def _table_names() -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        return {r[0] for r in rows}


class TestSchemaSource:
    def test_schema_was_built_by_alembic(self):
        """alembic_version exists and names a revision."""
        with engine.connect() as conn:
            revision = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar()

        assert revision, "alembic_version is empty — schema did not come from Alembic"

    def test_a_migration_only_index_is_present(self):
        """The load-bearing assertion.

        create_all cannot create this index, because no model declares it. If
        it is missing, the schema was built by create_all and every
        index-sensitive measurement taken against it is meaningless.
        """
        names = _index_names()

        assert MIGRATION_ONLY_INDEX in names, (
            f"{MIGRATION_ONLY_INDEX} is absent, so this database was not built "
            "by `alembic upgrade head`. See #97 — a performance measurement "
            "against a create_all schema measures a database that exists nowhere."
        )

    def test_migration_only_tables_are_present(self):
        """Eight tables live in the migration chain and not in models.py."""
        tables = _table_names()

        assert len(tables) >= 95, (
            f"only {len(tables)} tables present; the Alembic schema has 95. "
            "A create_all schema has 87."
        )

    def test_the_phase_3c_composites_exist(self):
        """The indexes ADMIN-PERF-001 added must actually be in the database."""
        names = _index_names()

        for expected in (
            "ix_enrollment_kg_status_class",
            "ix_daily_reports_kg_date_desc",
            "ix_supervisor_assignments_active_lookup",
        ):
            assert expected in names, f"{expected} missing from the test schema"

    def test_the_reconciled_names_are_canonical(self):
        """#97's three divergent pairs resolved to one name each."""
        names = _index_names()

        for stale in (
            "idx_kindergartens_governorate_city",
            "ix_incidents_kg_occurred_at",
            "ix_daily_reports_kg_date_status",
        ):
            assert stale not in names, f"{stale} should have been reconciled away"

        for canonical in (
            "idx_kindergartens_governorate_district",
            "idx_incidents_kg_occurred",
            "ix_daily_reports_kg_date_child_status",
        ):
            assert canonical in names, f"{canonical} missing"

    def test_the_partial_index_predicate_has_no_current_date(self):
        """CURRENT_DATE is STABLE; Postgres rejects it in an index predicate.

        If this ever comes back, the migration will not apply at all — but the
        assertion documents why the predicate looks the way it does.
        """
        with engine.connect() as conn:
            ddl = conn.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE indexname = 'ix_supervisor_assignments_active_lookup'"
                )
            ).scalar()

        assert ddl is not None
        assert "deleted_at IS NULL" in ddl
        assert "CURRENT_DATE" not in ddl.upper()


class TestGuardCanFail:
    """A guard that cannot fail proves nothing."""

    def test_the_index_probe_detects_an_absent_index(self):
        names = _index_names()

        assert "ix_this_index_does_not_exist" not in names


class TestAuditLogBulkWrite:
    """#98 — audit_logs.request_id must accept a batched insert.

    models.py declared String(36) while production PostgreSQL has `uuid`, so
    SQLAlchemy bound an explicit ::VARCHAR cast and every executemany of two or
    more audit rows failed with DatatypeMismatch. Single-row inserts adapted
    fine, which is why one-row-per-request traffic never surfaced it.

    This is the regression test. It is meaningless on SQLite, which has no uuid
    type and never had the mismatch, so it lives here with the other
    Postgres-only schema guards.
    """

    def test_five_audit_rows_in_one_flush(self, test_db):
        import models

        for _ in range(5):
            test_db.add(
                models.AuditLog(action="BULK_PROBE", entity_type="User", entity_id=1)
            )
        test_db.commit()  # one executemany, not five inserts

        written = (
            test_db.query(models.AuditLog)
            .filter(models.AuditLog.action == "BULK_PROBE")
            .count()
        )
        assert written == 5

    def test_request_id_round_trips_as_a_string(self, test_db):
        """as_uuid=False keeps the Python-side value a plain dashed string."""
        import models

        value = "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"
        rows = [
            models.AuditLog(
                action="UUID_PROBE", entity_type="User", entity_id=1, request_id=value
            )
            for _ in range(3)
        ]
        for row in rows:
            test_db.add(row)
        test_db.commit()

        stored = (
            test_db.query(models.AuditLog)
            .filter(models.AuditLog.action == "UUID_PROBE")
            .first()
        )
        assert stored.request_id == value
        assert isinstance(stored.request_id, str)
