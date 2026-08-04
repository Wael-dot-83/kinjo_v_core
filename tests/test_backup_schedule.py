"""D-3: automatic backups are wired to Celery beat and honour the BACKUP_* settings.

Before this batch, ``BACKUP_SCHEDULE_HOUR`` / ``BACKUP_CLEANUP_HOUR`` were read by
nothing and the beat schedule had no backup or cleanup entry, so no automatic backup
ever ran. These tests assert the schedule now exists, is driven by the settings, and
that the cleanup task actually prunes expired *automated* backups while sparing manual
ones.
"""
import os
from datetime import datetime, timedelta, timezone

from config import settings


def _beat():
    from celery_app import celery_app
    return celery_app.conf.beat_schedule


def test_daily_backup_entry_registered_and_driven_by_setting():
    entry = _beat().get("run-daily-backup")
    assert entry is not None, "run-daily-backup beat entry is missing"
    assert entry["task"] == "backup_tasks.run_backup"
    # crontab.hour is a set of matching hours; it must equal the configured hour.
    assert entry["schedule"].hour == {settings.BACKUP_SCHEDULE_HOUR}
    # Scheduled runs must be tagged "automated" so the retention sweep can prune them.
    assert entry.get("kwargs", {}).get("backup_type") == "automated"


def test_cleanup_entry_registered_and_driven_by_setting():
    entry = _beat().get("cleanup-old-backups")
    assert entry is not None, "cleanup-old-backups beat entry is missing"
    assert entry["task"] == "backup_tasks.cleanup_old_backups"
    assert entry["schedule"].hour == {settings.BACKUP_CLEANUP_HOUR}


def test_both_backup_tasks_are_registered_with_celery():
    from celery_app import celery_app
    import backup_tasks  # noqa: F401 — registers the tasks

    assert "backup_tasks.run_backup" in celery_app.tasks
    assert "backup_tasks.cleanup_old_backups" in celery_app.tasks


def _seed_backup(manager, name, *, backup_type, age_days, backup_dir):
    """Create a real file plus a metadata entry with a controlled age."""
    path = os.path.join(backup_dir, name)
    with open(path, "wb") as f:
        f.write(b"x")
    created = (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat()
    manager.metadata[name] = {
        "name": name,
        "type": "database",
        "backup_type": backup_type,
        "backup_path": path,
        "size_bytes": 1,
        "created_at": created,
        "checksum": "deadbeef",
    }


def test_cleanup_task_prunes_expired_automated_but_spares_manual(tmp_path, monkeypatch):
    import backup_manager as bm

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    monkeypatch.setattr(bm, "_BACKUP_DIR", str(backup_dir))

    fresh = bm.BackupManager()
    fresh.metadata = {}
    _seed_backup(fresh, "db_automated_old.sqlite3", backup_type="automated", age_days=999, backup_dir=str(backup_dir))
    _seed_backup(fresh, "db_manual_old.sqlite3", backup_type="manual", age_days=999, backup_dir=str(backup_dir))
    _seed_backup(fresh, "db_automated_fresh.sqlite3", backup_type="automated", age_days=0, backup_dir=str(backup_dir))
    fresh._save_metadata()

    # The task resolves the module-level singleton at call time; swap in our fresh one.
    monkeypatch.setattr(bm, "backup_manager", fresh)

    from backup_tasks import cleanup_old_backups

    result = cleanup_old_backups.apply(kwargs={"retention_days": 30}).get()

    assert result["removed"] == 1, result
    remaining = {b["name"] for b in fresh.list_backups()}
    assert "db_automated_old.sqlite3" not in remaining  # expired automated -> pruned
    assert "db_manual_old.sqlite3" in remaining          # manual -> spared even when old
    assert "db_automated_fresh.sqlite3" in remaining     # within retention -> kept
    assert not os.path.exists(os.path.join(str(backup_dir), "db_automated_old.sqlite3"))


def test_cleanup_task_defaults_retention_to_setting(tmp_path, monkeypatch):
    """retention_days=None must defer to settings.BACKUP_RETENTION_DAYS."""
    import backup_manager as bm

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    monkeypatch.setattr(bm, "_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(settings, "BACKUP_RETENTION_DAYS", 7)

    fresh = bm.BackupManager()
    fresh.metadata = {}
    # 10 days old > 7-day retention -> pruned only if the setting is honoured.
    _seed_backup(fresh, "db_automated_10d.sqlite3", backup_type="automated", age_days=10, backup_dir=str(backup_dir))
    fresh._save_metadata()
    monkeypatch.setattr(bm, "backup_manager", fresh)

    from backup_tasks import cleanup_old_backups

    result = cleanup_old_backups.apply(kwargs={}).get()

    assert result["removed"] == 1, result
    assert fresh.list_backups() == []
