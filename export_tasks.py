"""
Celery tasks for asynchronous report and KPI exports.

Each task:
  1. Accepts an ExportJob.id created by the triggering endpoint.
  2. Updates ExportJob.status through PROCESSING → COMPLETED/FAILED.
  3. Writes the generated file to disk and records file_path + file_size.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from celery_app import celery_app
from database import SessionLocal
import models
from sqlalchemy import or_

logger = logging.getLogger(__name__)

_ANALYTICS_STALE_AFTER = timedelta(hours=1)


@celery_app.task(
    name="export_tasks.run_analytics_export_job",
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_analytics_export_job(export_job_id: int) -> Dict[str, Any]:
    """Run the idempotent analytics worker from a durable Celery delivery."""
    from analytics_service import process_export_job

    return process_export_job(export_job_id)


@celery_app.task(name="export_tasks.dispatch_pending_analytics_exports")
def dispatch_pending_analytics_exports(batch_size: int = 100) -> Dict[str, int]:
    """Recover committed jobs missed by publish or interrupted worker processes.

    The ExportJob row is the outbox. Duplicate deliveries are safe because the
    worker atomically claims only PENDING rows. A PROCESSING row is eligible for
    recovery only after an hour, preventing ordinary long-running work from
    being dispatched concurrently.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stale_before = now - _ANALYTICS_STALE_AFTER
    db = SessionLocal()
    try:
        query = (
            db.query(models.ExportJob)
            .filter(
                or_(
                    models.ExportJob.status == models.ExportStatus.PENDING,
                    (
                        (models.ExportJob.status == models.ExportStatus.PROCESSING)
                        & (models.ExportJob.started_at < stale_before)
                    ),
                )
            )
            .order_by(models.ExportJob.created_at.asc(), models.ExportJob.id.asc())
            .limit(batch_size)
        )
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        jobs = query.all()
        job_ids = []
        recovered = 0
        for job in jobs:
            if job.status == models.ExportStatus.PROCESSING:
                job.status = models.ExportStatus.PENDING
                job.started_at = None
                recovered += 1
            job_ids.append(job.id)
        db.commit()
    finally:
        db.close()

    published = 0
    for job_id in job_ids:
        try:
            run_analytics_export_job.delay(job_id)
            published += 1
        except Exception:
            logger.exception("Failed to republish analytics export %s", job_id)
    return {"found": len(job_ids), "recovered": recovered, "published": published}


@celery_app.task(
    name="export_tasks.run_export_job",
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_export_job(export_job_id: int) -> Dict[str, Any]:
    """Compatibility task name routed through the canonical durable worker."""
    return run_analytics_export_job.run(export_job_id)
