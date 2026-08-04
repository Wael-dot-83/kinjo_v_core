"""
Celery tasks for asynchronous database and file backups.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from celery_app import celery_app
from database import SessionLocal

logger = logging.getLogger(__name__)


def _run_backup(
    backup_type: str,
    include_uploads: bool,
    include_config: bool,
    triggered_by_user_id: Optional[int] = None,
) -> dict:
    """Core backup logic — callable without Celery infrastructure (e.g. in tests)."""
    from backup_manager import backup_manager

    results: dict = {}

    db_backup = backup_manager.create_database_backup(backup_type)
    results["database"] = db_backup

    if include_uploads:
        results["uploads"] = backup_manager.create_uploads_backup(backup_type)

    if include_config:
        results["config"] = backup_manager.create_config_backup(backup_type)

    # Audit inside the task so the event is recorded even for scheduled runs
    if triggered_by_user_id is not None:
        db = SessionLocal()
        try:
            import models
            from admin_security import log_audit_event
            user = db.query(models.User).filter(models.User.id == triggered_by_user_id).first()
            if user:
                log_audit_event(
                    db,
                    "BACKUP_CREATED",
                    user,
                    "Backup",
                    metadata={
                        "backup_type": backup_type,
                        "components": list(results.keys()),
                        "async": True,
                    },
                    sensitivity_level=2,
                )
                db.commit()
        except Exception:
            logger.exception("Failed to log backup audit event")
        finally:
            db.close()

    return results


@celery_app.task(name="backup_tasks.run_backup", bind=True, max_retries=2, default_retry_delay=60)
def run_backup(
    self,
    backup_type: str = "manual",
    include_uploads: bool = True,
    include_config: bool = True,
    triggered_by_user_id: Optional[int] = None,
) -> dict:
    """Async Celery task: create a full or partial backup."""
    from fastapi import HTTPException as _HTTPException
    try:
        return _run_backup(backup_type, include_uploads, include_config, triggered_by_user_id)
    except _HTTPException:
        # Let FastAPI HTTP errors propagate as-is — no retry, status code is preserved.
        raise
    except Exception as exc:
        logger.exception("Backup task failed (attempt %d): %s", self.request.retries + 1, exc)
        raise self.retry(exc=exc)


@celery_app.task(name="backup_tasks.cleanup_old_backups", bind=True, max_retries=2, default_retry_delay=60)
def cleanup_old_backups(self, retention_days: Optional[int] = None) -> dict:
    """Async Celery task: prune automated backups past the retention window.

    ``retention_days=None`` defers to ``settings.BACKUP_RETENTION_DAYS``. Manual
    backups are never auto-deleted (see BackupManager.cleanup_old_backups).
    """
    from backup_manager import backup_manager
    try:
        before = len(backup_manager.list_backups())
        backup_manager.cleanup_old_backups(retention_days)
        after = len(backup_manager.list_backups())
        return {"removed": before - after, "remaining": after}
    except Exception as exc:
        logger.exception("Backup cleanup task failed (attempt %d): %s", self.request.retries + 1, exc)
        raise self.retry(exc=exc)
