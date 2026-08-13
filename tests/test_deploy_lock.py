"""The canonical deploy wrapper must serialise the whole mutation window.

Two agents running `docker compose` concurrently took production down twice on
2026-08-12. The wrapper exists so a second deploy refuses instead of racing.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "deploy_locked.sh"


def _src() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_wrapper_exists():
    assert SCRIPT.is_file()


def test_lock_is_non_blocking():
    """A queued second deploy is as dangerous as a racing one: it would fire the
    moment the first finished, against code the operator no longer expects."""
    src = _src()
    assert "flock -n 9" in src
    assert "exec 9>" in src


def test_busy_lock_exits_without_touching_production():
    src = _src()
    busy = src.split("if ! flock -n 9; then", 1)[1].split("fi", 1)[0]
    assert "exit 75" in busy
    assert "DEPLOY_LOCK_BUSY" in busy
    # Nothing destructive may appear in the refusal path.
    for forbidden in ("docker compose", "tar xf", "pg_dump", "alembic upgrade"):
        assert forbidden not in busy


def test_lock_is_acquired_before_every_mutation():
    """Ordering is the whole point: backup, extraction, build, migration and
    health check must all sit inside the lock."""
    src = _src()
    lock_at = src.index("flock -n 9")
    for step in ("tar xf", "docker compose -f", "alembic upgrade", "pg_dump", "docker tag"):
        assert src.index(step) > lock_at, f"{step} happens before the lock is held"


def test_health_verification_is_inside_the_lock():
    """Releasing the lock before the health check would let a second deploy
    start against a half-verified release."""
    src = _src()
    # The lock is held until process exit; assert the health gate precedes the
    # final success line rather than being deferred.
    assert src.index("HEALTHY") < src.index("DEPLOY_OK")


def test_lock_records_owner_metadata():
    src = _src()
    assert "pid=%s" in src and "started=%s" in src
    assert 'cat "$LOCK_FILE"' in src


def test_env_is_preserved_across_extraction():
    """.env is not in the archive; a deploy that silently replaced it would take
    the database and SMTP credentials with it."""
    src = _src()
    assert "ENV_BEFORE" in src and "ENV_AFTER" in src
    assert 'die ".env changed during extraction' in src


def test_backup_is_verified_non_empty():
    src = _src()
    assert "refusing to continue" in src
    assert "-s " in src or "[[ -s" in src


def test_backups_are_bounded():
    """~850MB per dump would fill the disk within days."""
    src = _src()
    assert "KEEP_BACKUPS" in src
    assert "rm -f" in src


def test_backup_runs_when_a_migration_is_pending():
    src = _src()
    assert "MIGRATION_PENDING" in src
    assert "alembic current" in src and "alembic heads" in src


def test_rollback_image_is_tagged_before_the_build():
    src = _src()
    assert src.index("rollback-$TS") < src.index("docker compose -f")


def test_failure_aborts_rather_than_continuing():
    assert "set -euo pipefail" in _src()


def test_obsolete_root_deploy_script_is_marked():
    """scripts/deploy.sh at the root targets /srv/kinjo, a venv and systemd
    units that do not exist here; running it would fail confusingly."""
    assert "obsolete" in _src().lower()
