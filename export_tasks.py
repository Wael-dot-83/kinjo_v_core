"""
Celery tasks for asynchronous report and KPI exports.

Each task:
  1. Accepts an ExportJob.id created by the triggering endpoint.
  2. Updates ExportJob.status through PROCESSING → COMPLETED/FAILED.
  3. Writes the generated file to disk and records file_path + file_size.
"""
import logging
import os
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from celery_app import celery_app
from database import SessionLocal
import models

logger = logging.getLogger(__name__)

_EXPORT_DIR = os.environ.get("EXPORT_DIR", "/tmp/kinjo_exports")


def _mark_processing(db, job: models.ExportJob) -> None:
    job.status = models.ExportStatus.PROCESSING
    job.started_at = datetime.now(timezone.utc)
    db.commit()


def _mark_completed(db, job: models.ExportJob, file_path: str, file_size: int) -> None:
    job.status = models.ExportStatus.COMPLETED
    job.file_path = file_path
    job.file_size = file_size
    job.completed_at = datetime.now(timezone.utc)
    db.commit()


def _mark_failed(db, job: models.ExportJob, error: str) -> None:
    job.status = models.ExportStatus.FAILED
    job.error_message = error[:1000]
    job.completed_at = datetime.now(timezone.utc)
    db.commit()


@celery_app.task(name="export_tasks.run_export_job", bind=True, max_retries=1, default_retry_delay=30)
def run_export_job(self, export_job_id: int) -> Dict[str, Any]:
    """
    Process an export job identified by ExportJob.id.

    The triggering endpoint must already have created the ExportJob row with
    status=PENDING before enqueuing this task.
    """
    db = SessionLocal()
    job: Optional[models.ExportJob] = None
    try:
        job = db.query(models.ExportJob).filter(models.ExportJob.id == export_job_id).first()
        if job is None:
            logger.error("ExportJob %d not found", export_job_id)
            return {"error": "job_not_found"}

        if job.status != models.ExportStatus.PENDING:
            logger.warning("ExportJob %d is already %s — skipping", export_job_id, job.status)
            return {"status": job.status.value}

        _mark_processing(db, job)

        from export_service import export_service

        user = db.query(models.User).filter(models.User.id == job.user_id).first()
        if user is None:
            _mark_failed(db, job, "user_not_found")
            return {"error": "user_not_found"}

        filters: Dict[str, Any] = job.filters or {}
        report_type = job.report_type
        fmt = job.export_format.value.lower()

        if report_type == "kpi_dashboard":
            result = export_service.export_kpi_dashboard(user, None, fmt)
        else:
            date_from = date.fromisoformat(filters["date_from"]) if "date_from" in filters else date.today()
            date_to = date.fromisoformat(filters["date_to"]) if "date_to" in filters else date.today()
            result = export_service.export_analytics_report(user, report_type, date_from, date_to, fmt)

        os.makedirs(_EXPORT_DIR, exist_ok=True)
        filename = result.get("filename", f"export_{export_job_id}.{fmt}")
        file_path = os.path.join(_EXPORT_DIR, filename)
        content = result.get("content", b"")
        if isinstance(content, str):
            content = content.encode("utf-8")
        with open(file_path, "wb") as fh:
            fh.write(content)

        _mark_completed(db, job, file_path, len(content))
        return {"status": "completed", "file_path": file_path, "file_size": len(content)}

    except Exception as exc:
        logger.exception("ExportJob %d failed: %s", export_job_id, exc)
        if job is not None:
            try:
                _mark_failed(db, job, str(exc))
            except Exception:
                logger.exception("Failed to mark export job as failed")
        raise self.retry(exc=exc)
    finally:
        db.close()
