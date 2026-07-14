"""Deployment tests for c7d9e1a4b820 — the columns models.py declares but no migration made.

These deliberately drive **Alembic**, not `Base.metadata.create_all()`. The whole bug class
this file guards against is invisible to the rest of the suite precisely because conftest
builds its schema with `create_all`: every declared column simply exists there, so a column
that no migration creates still passes every normal test and only fails on a freshly
migrated deployment.

Covered:
  * fresh database, base -> head
  * an existing pre-migration database with rows, upgraded to head (the backfill path)
  * the exact queries live code runs against the drifted columns
  * upgrade -> downgrade -> upgrade
  * `alembic check` reports no add_table/add_column/add_constraint drift
"""
from __future__ import annotations

import subprocess
import sqlite3
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_PREV_REV = "1417f512f696"


def _alembic(db: Path, *args: str) -> subprocess.CompletedProcess:
    """Run alembic against an isolated sqlite file."""
    import os

    env = dict(os.environ, DATABASE_URL=f"sqlite:///{db.as_posix()}")
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=_ROOT, env=env, capture_output=True, text=True, timeout=600,
    )


def _cols(db: Path, table: str) -> set[str]:
    con = sqlite3.connect(db)
    try:
        return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
    finally:
        con.close()


@pytest.fixture
def fresh_db(tmp_path: Path) -> Path:
    db = tmp_path / "fresh.db"
    r = _alembic(db, "upgrade", "head")
    assert r.returncode == 0, f"base -> head failed:\n{r.stderr[-2000:]}"
    return db


def test_fresh_database_has_the_drifted_columns(fresh_db: Path) -> None:
    """base -> head must produce every column models.py declares."""
    incidents = _cols(fresh_db, "incidents")
    reports = _cols(fresh_db, "reports")
    assert "status" in incidents, "incidents.status missing from a chain-built DB"
    assert "owner_id" in incidents, "incidents.owner_id missing from a chain-built DB"
    assert "district" in reports, "reports.district missing from a chain-built DB"
    assert "area" in reports, "reports.area missing from a chain-built DB"


def test_live_queries_work_on_a_chain_built_database(fresh_db: Path) -> None:
    """The real reads/writes: list filter, owner assignment, status transition, history."""
    con = sqlite3.connect(fresh_db)
    try:
        con.execute("SELECT id FROM incidents WHERE status = 'OPEN'").fetchall()
        con.execute("UPDATE incidents SET owner_id = 1 WHERE id = -1")
        con.execute("UPDATE incidents SET status = 'RESOLVED' WHERE id = -1")
        # incident_history records both transitions
        con.execute(
            "SELECT status_from, status_to, owner_from_id, owner_to_id "
            "FROM incident_history WHERE incident_id = -1"
        ).fetchall()
        con.execute(
            "SELECT id FROM reports WHERE district = 'x' AND area = 'y'"
        ).fetchall()
    finally:
        con.rollback()
        con.close()


def test_existing_database_upgrades_and_backfills_status(tmp_path: Path) -> None:
    """A pre-migration DB **with rows** must upgrade, and every row must get a status.

    status is NOT NULL with no server default, so if the backfill were wrong the ALTER
    would fail here. It also pins the enum representation: SQLAlchemy stores the member
    NAME ('OPEN'), not its value ('Open') — backfilling the value would break this.
    """
    db = tmp_path / "existing.db"
    r = _alembic(db, "upgrade", _PREV_REV)
    assert r.returncode == 0, f"upgrade to {_PREV_REV} failed:\n{r.stderr[-2000:]}"
    assert "status" not in _cols(db, "incidents"), (
        "incidents.status already exists at the previous revision — the premise of this "
        "test (and of the migration) is wrong"
    )

    con = sqlite3.connect(db)
    try:
        con.execute(
            "INSERT INTO kindergartens (name_ar,governorate,district,area,address_line,"
            "contact_phone,status) VALUES ('ح','عمان','ماركا','a','a','07','ACTIVE')"
        )
        kg = con.execute("SELECT id FROM kindergartens LIMIT 1").fetchone()[0]
        con.execute(
            "INSERT INTO users (username,email,hashed_password,role,status,"
            "must_change_password,mfa_enabled,failed_login_count) "
            "VALUES ('u1','u1@t.co','x','ADMIN','ACTIVE',0,0,0)"
        )
        uid = con.execute("SELECT id FROM users LIMIT 1").fetchone()[0]
        con.execute(
            "INSERT INTO children (parent_id,first_name,last_name,gender,date_of_birth,"
            "father_name,mother_first_name,mother_last_name,mother_nationality,"
            "media_consent,correspondence_flag,profile_complete,has_special_needs,"
            "has_medical_condition) VALUES (?,'a','b','MALE','2022-01-01','f','m','l',"
            "'JO',0,0,0,0,0)",
            (uid,),
        )
        child = con.execute("SELECT id FROM children LIMIT 1").fetchone()[0]
        for _ in range(3):
            con.execute(
                "INSERT INTO incidents (child_id,kindergarten_id,type,severity_level,"
                "description,occurred_at,followup_required_flag,parent_informed,"
                "reported_by) VALUES (?,?,'INJURY','LOW','d','2026-07-01 10:00:00',0,0,?)",
                (child, kg, uid),
            )
        con.commit()
    finally:
        con.close()

    r = _alembic(db, "upgrade", "head")
    assert r.returncode == 0, f"existing DB -> head failed:\n{r.stderr[-2000:]}"

    con = sqlite3.connect(db)
    try:
        assert con.execute(
            "SELECT COUNT(*) FROM incidents WHERE status IS NULL"
        ).fetchone()[0] == 0, "backfill left NULLs — NOT NULL cannot hold"
        assert con.execute(
            "SELECT DISTINCT status FROM incidents"
        ).fetchall() == [("OPEN",)], "pre-existing rows must backfill to the enum NAME 'OPEN'"
        assert con.execute(
            "SELECT COUNT(*) FROM incidents WHERE owner_id IS NULL"
        ).fetchone()[0] == 3, "existing rows must keep owner_id NULL, not be invented"
    finally:
        con.close()


def test_upgrade_downgrade_upgrade_is_clean(fresh_db: Path) -> None:
    r = _alembic(fresh_db, "downgrade", "-1")
    assert r.returncode == 0, f"downgrade failed:\n{r.stderr[-2000:]}"
    assert "status" not in _cols(fresh_db, "incidents"), "downgrade left incidents.status"
    assert "district" not in _cols(fresh_db, "reports"), "downgrade left reports.district"

    r = _alembic(fresh_db, "upgrade", "head")
    assert r.returncode == 0, f"re-upgrade failed:\n{r.stderr[-2000:]}"
    assert "status" in _cols(fresh_db, "incidents")


def test_alembic_check_reports_no_missing_schema(fresh_db: Path) -> None:
    """No add_* drift: nothing models.py declares may be absent from the chain.

    remove_table/remove_index are tolerated — those are tables present in the DB but not
    in models.py, which is the harmless direction (orphaned schema, not a crash).
    """
    out = _alembic(fresh_db, "check")
    blob = out.stdout + out.stderr
    for op in ("'add_table'", "'add_column'", "'add_constraint'"):
        assert op not in blob, (
            f"{op} drift is back: models.py declares schema no migration creates, which "
            f"fails on a fresh deployment.\n{blob[-1500:]}"
        )
