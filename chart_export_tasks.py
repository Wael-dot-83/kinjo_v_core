"""Recurring chart exports.

Beat sweeps hourly and runs whatever is due. Each schedule stores its own
`next_run_at` (UTC, like the rest of beat) rather than recomputing from
`last_run_at`, so a schedule that was paused, edited, or missed while the worker
was down fires once when it comes back instead of trying to catch up.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from celery_app import celery_app
from database import SessionLocal
import models

logger = logging.getLogger(__name__)

EXPORT_DIR = Path("data/exports")

# Jordan is UTC+3; operational windows are expressed in Jordan dates even though
# the schedule itself fires on a UTC hour.
_JORDAN_TZ = timezone(timedelta(hours=3))


def _jordan_today() -> date:
    return datetime.now(_JORDAN_TZ).date()


def resolve_window(preset: str) -> tuple[date, date]:
    """Translate a stored preset into a concrete Jordan date range."""
    today = _jordan_today()
    if preset == "today":
        return today, today
    if preset == "last_7":
        return today - timedelta(days=6), today
    if preset == "this_month":
        return today.replace(day=1), today
    if preset == "last_month":
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        return last_prev.replace(day=1), last_prev
    # last_30 is the documented default everywhere else in the explorer.
    return today - timedelta(days=29), today


def compute_next_run(frequency: str, hour_utc: int, after: Optional[datetime] = None) -> datetime:
    """First occurrence of `hour_utc` strictly after `after`."""
    now = after or datetime.now(timezone.utc)
    now = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    candidate = now.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    if frequency == "WEEKLY":
        candidate += timedelta(days=(7 - 1))
    elif frequency == "MONTHLY":
        candidate += timedelta(days=(30 - 1))
    return candidate.replace(tzinfo=None)


def _serialise(rows: list[dict[str, Any]], export_format: str) -> tuple[str, str]:
    """Return (text, file extension)."""
    if export_format == "JSON":
        return json.dumps(rows, ensure_ascii=False, indent=2, default=str), "json"
    buffer = io.StringIO()
    if rows:
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    # Excel needs the BOM to read Arabic columns as UTF-8 rather than mojibake.
    return "﻿" + buffer.getvalue(), "csv"


def _fetch_rows(db, schedule: models.ScheduledChartExport, start: date, end: date) -> list[dict]:
    """Pull the same series the explorer would draw for this schedule."""
    # Imported late: charts.service pulls in pandas, which is expensive to load
    # in a worker that may never run an export.
    from charts.schemas import ChartRequest
    from charts.service import ChartService

    req = ChartRequest(
        source=schedule.source,
        chart_type=schedule.chart_type or None,
        date_from=start.isoformat(),
        date_to=end.isoformat(),
        governorate=schedule.governorate,
        lang="ar",
    )
    # allow_offload=False: this *is* the background job, so handing the work to
    # another queued task would return a task id instead of the rows.
    response = ChartService().render(db, req, allow_offload=False)
    series = getattr(response, "series", None)
    if series is None and isinstance(response, dict):
        series = response.get("series")
    return list(series or [])


def run_one(db, schedule: models.ScheduledChartExport) -> str:
    start, end = resolve_window(schedule.date_preset)
    rows = _fetch_rows(db, schedule, start, end)
    text, ext = _serialise(rows, schedule.export_format)

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = EXPORT_DIR / f"chart_{schedule.source}_{schedule.id}_{stamp}.{ext}"
    path.write_text(text, encoding="utf-8")

    # email_service.send_email has no attachment support, so the message carries
    # the summary and the file stays on disk for retrieval.
    try:
        from email_service import is_smtp_configured, send_email

        if is_smtp_configured():
            send_email(
                schedule.recipient_email,
                f"KinJo scheduled export: {schedule.source} ({start} → {end})",
                (
                    f"Rows: {len(rows)}\n"
                    f"Window: {start} → {end}\n"
                    f"Format: {schedule.export_format}\n"
                    f"File: {path.name}\n"
                ),
            )
            return "SENT"
        return "STORED"      # no SMTP configured: the file is still produced
    except Exception:
        logger.exception("Scheduled export %s: email delivery failed", schedule.id)
        return "STORED"


@celery_app.task(name="chart_export_tasks.run_due_exports", bind=True, max_retries=1)
def run_due_exports(self) -> dict:
    """Run every active schedule whose next_run_at has passed."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db = SessionLocal()
    ran, failed = 0, 0
    try:
        due = (
            db.query(models.ScheduledChartExport)
            .filter(
                models.ScheduledChartExport.is_active.is_(True),
                models.ScheduledChartExport.next_run_at.isnot(None),
                models.ScheduledChartExport.next_run_at <= now,
            )
            .all()
        )
        for schedule in due:
            try:
                schedule.last_status = run_one(db, schedule)
                schedule.last_error = None
                ran += 1
            except Exception as exc:                      # one bad schedule must
                logger.exception("Scheduled export %s failed", schedule.id)
                schedule.last_status = "FAILED"           # not stop the others
                schedule.last_error = str(exc)[:2000]
                failed += 1
            schedule.last_run_at = now
            # Advance from now, never from the missed slot, so a worker outage
            # cannot queue up a burst of catch-up runs.
            schedule.next_run_at = compute_next_run(schedule.frequency, schedule.hour_utc)
            db.commit()
        return {"due": len(due), "ran": ran, "failed": failed}
    finally:
        db.close()
