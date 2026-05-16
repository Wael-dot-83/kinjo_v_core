"""
Daily report scheduler — triggers timed background tasks.

Schedule:
  - 3:45 PM  → send_daily_report_reminder  (15-minute warning)
  - 4:00 PM  → check_daily_report_compliance (deadline enforcement + escalation)

In production these run via Celery Beat.  The scheduler object below is
used by main.py to start/stop the beat entries programmatically when
Celery Beat is not available (e.g. single-process dev mode).
"""
import logging
import threading
from datetime import datetime, time, timedelta

logger = logging.getLogger(__name__)

REMINDER_TIME = time(15, 45)   # 3:45 PM
DEADLINE_TIME = time(16, 0)    # 4:00 PM


class DailyReportScheduler:
    """Lightweight in-process scheduler that fires Celery tasks at the
    configured wall-clock times.  For production use Celery Beat instead.
    """

    def __init__(self):
        self._timers: list[threading.Timer] = []
        self._running = False

    # ------------------------------------------------------------------ #
    def start_scheduler(self) -> None:
        if self._running:
            return
        self._running = True
        self._schedule_next()
        logger.info("DailyReportScheduler started (reminder=%s, deadline=%s)",
                     REMINDER_TIME.strftime("%H:%M"), DEADLINE_TIME.strftime("%H:%M"))

    def stop_scheduler(self) -> None:
        self._running = False
        for t in self._timers:
            t.cancel()
        self._timers.clear()
        logger.info("DailyReportScheduler stopped")

    # ------------------------------------------------------------------ #
    def _schedule_next(self) -> None:
        if not self._running:
            return
        now = datetime.now()
        events = [
            (REMINDER_TIME, self._fire_reminder),
            (DEADLINE_TIME, self._fire_compliance),
        ]
        for target_time, callback in events:
            target_dt = datetime.combine(now.date(), target_time)
            if target_dt <= now:
                # Already past today → schedule for tomorrow
                target_dt += timedelta(days=1)
            delay_seconds = (target_dt - now).total_seconds()
            timer = threading.Timer(delay_seconds, callback)
            timer.daemon = True
            timer.start()
            self._timers.append(timer)

    def _fire_reminder(self) -> None:
        logger.info("Firing 3:45 PM daily-report reminder")
        try:
            from notification_tasks import send_daily_report_reminder
            send_daily_report_reminder.delay()
        except (ImportError, RuntimeError, AttributeError, TypeError) as exc:
            logger.error("Failed to queue reminder task: %s", exc)
        self._reschedule()

    def _fire_compliance(self) -> None:
        logger.info("Firing 4:00 PM daily-report compliance check")
        try:
            from notification_tasks import check_daily_report_compliance
            check_daily_report_compliance.delay()
        except (ImportError, RuntimeError, AttributeError, TypeError) as exc:
            logger.error("Failed to queue compliance task: %s", exc)
        self._reschedule()

    def _reschedule(self) -> None:
        # Clean finished timers and schedule for tomorrow
        self._timers = [t for t in self._timers if t.is_alive()]
        self._schedule_next()


daily_report_scheduler = DailyReportScheduler()
