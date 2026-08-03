"""Scheduled regeneration of the heat map indicator dataset.

The `/api/heatmap/*` surface reads a generated CSV. Regenerating it on every GET
would put a dozen aggregate queries on the request path, so generation is a
background job and reads stay cheap.

Runs daily on **Jordan business time** because the dataset is day-based: its `date`
column and its absence window are both calendar-day concepts, and rolling them over
on UTC midnight would file three hours of Jordan activity under the wrong day.
"""
from __future__ import annotations

import logging

from celery_app import celery_app
from database import SessionLocal
from utils.time_utils import now_amman

logger = logging.getLogger(__name__)


@celery_app.task(name="heatmap_tasks.regenerate_daily_indicators")
def regenerate_daily_indicators() -> dict:
    """Rebuild the heat map dataset from authoritative KinJo tables.

    Idempotent: a run for a given day fully replaces that day's dataset, so repeating
    it changes nothing. Concurrency is refused rather than queued — the generator
    holds a non-blocking lock and reports `skipped_locked`, because two identical
    rebuilds racing on the same file is waste, not throughput.
    """
    from heatmap.backend.etl.generate import generate_daily_indicators

    started = now_amman()
    db = SessionLocal()
    try:
        result = generate_daily_indicators(db)
    except Exception as exc:  # noqa: BLE001 - a scheduled task must not die silently
        logger.exception("Scheduled heat map dataset generation raised")
        return {"status": "failed", "error": str(exc), "started_at": started.isoformat()}
    finally:
        db.close()

    if result.status == "success":
        # The API caches the parsed CSV per worker process. This task usually runs in a
        # Celery worker, i.e. a *different* process from the API workers, so it cannot
        # invalidate their caches. Those pick the new file up on restart or via the
        # admin refresh endpoint. Recorded as a known limitation in report 35.
        logger.info(
            "Scheduled heat map dataset generation wrote %d rows for %s",
            result.rows_written, result.snapshot_date,
        )
    else:
        logger.error(
            "Scheduled heat map dataset generation did not install a dataset: status=%s error=%s",
            result.status, result.error,
        )

    payload = result.as_dict()
    payload["started_at"] = started.isoformat()
    payload["trigger"] = "scheduled"
    return payload
