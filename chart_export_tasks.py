"""Recurring chart exports.

Beat sweeps hourly and runs whatever is due. Each schedule stores its own
`next_run_at` (UTC, like the rest of beat) rather than recomputing from
`last_run_at`, so a schedule that was paused, edited, or missed while the worker
was down fires once when it comes back instead of trying to catch up.
"""

from __future__ import annotations

import calendar
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


def _add_one_month(moment: datetime) -> datetime:
    """Same day next month, clamped to the month's length.

    A fixed 30 days is not a month: it drifts a day every January and two every
    February, so a "monthly on the 31st" schedule slides backwards through the
    calendar. 31 Jan must land on 28 Feb (29 in a leap year), not 2 March.
    """
    year = moment.year + (1 if moment.month == 12 else 0)
    month = 1 if moment.month == 12 else moment.month + 1
    last_day = calendar.monthrange(year, month)[1]
    return moment.replace(year=year, month=month, day=min(moment.day, last_day))


def compute_next_run(frequency: str, hour_utc: int, after: Optional[datetime] = None) -> datetime:
    """First occurrence of `hour_utc` strictly after `after`."""
    now = after or datetime.now(timezone.utc)
    now = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    slot = now.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
    if frequency == "MONTHLY":
        # Anchored to the day of the month, so the 31st keeps meaning "month
        # end" instead of drifting backwards the way a fixed 30 days would.
        return (slot if slot > now else _add_one_month(slot)).replace(tzinfo=None)
    candidate = slot if slot > now else slot + timedelta(days=1)
    if frequency == "WEEKLY":
        candidate += timedelta(days=6)
    return candidate.replace(tzinfo=None)


def _defuse(value: Any) -> Any:
    """Neutralise spreadsheet formula injection.

    Excel and Sheets execute a cell that opens with = + - @ (or a leading tab or
    carriage return before one), so a kindergarten literally named "=cmd|..."
    would run on open. An apostrophe keeps the text readable and inert.
    """
    dangerous = ("=", "+", "-", "@", chr(9), chr(13))
    if isinstance(value, str) and value[:1] in dangerous:
        return "'" + value
    return value


def _serialise(rows: list[dict[str, Any]], export_format: str) -> tuple[str, str]:
    """Return (text, file extension)."""
    if export_format == "JSON":
        return json.dumps(rows, ensure_ascii=False, indent=2, default=str), "json"
    buffer = io.StringIO()
    if rows:
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _defuse(val) for key, val in row.items()})
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

    from email_service import is_smtp_configured, send_email

    if not is_smtp_configured():
        # The file is still produced, and STORED says plainly that it was not
        # emailed rather than implying a delivery.
        return "STORED"

    try:
        send_email(
            schedule.recipient_email,
            f"KinJo scheduled export: {schedule.source} ({start} → {end})",
            (
                f"Rows: {len(rows)}\n"
                f"Window: {start} → {end}\n"
                f"Format: {schedule.export_format}\n"
                f"Attached: {path.name}\n"
            ),
            attachments=[(path.name, text.encode("utf-8"))],
        )
    except Exception:
        # SENT has to mean the file actually left. Downgrading a failure to
        # STORED would record a delivery that never happened.
        logger.exception("Scheduled export %s: email delivery failed", schedule.id)
        raise

    _prune_exports()
    return "SENT"


def _prune_exports(keep: int = 50) -> None:
    """Bound data/exports so a daily schedule cannot fill the disk."""
    try:
        files = sorted(
            EXPORT_DIR.glob("chart_*"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        for stale in files[keep:]:
            stale.unlink(missing_ok=True)
    except OSError:
        logger.warning("Export retention sweep failed", exc_info=True)


@celery_app.task(name="chart_export_tasks.run_due_exports", bind=True, max_retries=1)
def run_due_exports(self) -> dict:
    """Run every active schedule whose next_run_at has passed."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db = SessionLocal()
    ran, failed = 0, 0
    try:
        query = db.query(models.ScheduledChartExport).filter(
            models.ScheduledChartExport.is_active.is_(True),
            models.ScheduledChartExport.next_run_at.isnot(None),
            models.ScheduledChartExport.next_run_at <= now,
        )
        # Claim the due rows before doing any work. Two workers sweeping in the
        # same minute would otherwise both select the same schedule and email
        # the recipient twice. SKIP LOCKED lets the second worker move on to
        # other rows rather than block; SQLite ignores it and stays
        # single-writer, which is equally safe there.
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        due = query.all()

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
