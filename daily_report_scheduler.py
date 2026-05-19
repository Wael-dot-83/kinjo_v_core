"""
Daily report scheduler — triggers timed background tasks.

Schedule:
  - 3:45 PM  → send_daily_report_reminder  (15-minute warning)
  - 4:00 PM  → check_daily_report_compliance (deadline enforcement + escalation)
  - Every 15 min → expire_waitlist_offers (waitlist offer expiry + auto-promotion)

In production these run via Celery Beat.  The scheduler object below is
used by main.py to start/stop the beat entries programmatically when
Celery Beat is not available (e.g. single-process dev mode).
"""
import logging
import threading
from datetime import datetime, time, timedelta, timezone

logger = logging.getLogger(__name__)

REMINDER_TIME = time(15, 45)   # 3:45 PM
DEADLINE_TIME = time(16, 0)    # 4:00 PM
WAITLIST_EXPIRY_INTERVAL = 15 * 60  # 15 minutes in seconds


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


# =============================================================================
# Waitlist Expiry Scheduler
# =============================================================================

def _expire_waitlist_offers_job() -> None:
    """
    Expire OFFERED waitlist entries past their offer_expiry_at deadline, then
    auto-promote the next highest-priority WAITLISTED candidate for the same
    kindergarten.

    Runs every 15 minutes via WaitlistExpiryScheduler (or Celery Beat in prod).
    """
    from database import SessionLocal
    import models as m

    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        expired_entries = (
            db.query(m.WaitlistEntry)
            .filter(
                m.WaitlistEntry.status == m.WaitlistStatus.OFFERED,
                m.WaitlistEntry.offer_expiry_at < now,
            )
            .all()
        )

        for entry in expired_entries:
            entry.status = m.WaitlistStatus.EXPIRED
            logger.info(
                "Waitlist entry %d expired (child_id=%s)",
                entry.id,
                getattr(entry, "child_id", None),
            )

            # Determine the kindergarten from the linked enrollment
            enrollment = db.query(m.EnrollmentApplication).filter(
                m.EnrollmentApplication.id == entry.enrollment_id
            ).first() if entry.enrollment_id else None

            if enrollment:
                next_entry = (
                    db.query(m.WaitlistEntry)
                    .join(
                        m.EnrollmentApplication,
                        m.WaitlistEntry.enrollment_id == m.EnrollmentApplication.id,
                    )
                    .filter(
                        m.WaitlistEntry.status == m.WaitlistStatus.WAITLISTED,
                        m.EnrollmentApplication.kindergarten_id == enrollment.kindergarten_id,
                    )
                    .order_by(
                        m.WaitlistEntry.priority_score.desc(),
                        m.WaitlistEntry.created_at,
                    )
                    .first()
                )
                if next_entry:
                    next_entry.status = m.WaitlistStatus.OFFERED
                    next_entry.offer_sent_at = now
                    next_entry.offer_expiry_at = now + timedelta(days=7)
                    logger.info(
                        "Promoted waitlist entry %d to OFFERED (kindergarten_id=%d)",
                        next_entry.id,
                        enrollment.kindergarten_id,
                    )

        db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.error("Error in expire_waitlist_offers job: %s", exc)
        db.rollback()
    finally:
        db.close()


class WaitlistExpiryScheduler:
    """Runs _expire_waitlist_offers_job every WAITLIST_EXPIRY_INTERVAL seconds."""

    def __init__(self):
        self._timer: threading.Timer | None = None
        self._running = False

    def start_scheduler(self) -> None:
        if self._running:
            return
        self._running = True
        self._schedule_next()
        logger.info(
            "WaitlistExpiryScheduler started (interval=%ds)", WAITLIST_EXPIRY_INTERVAL
        )

    def stop_scheduler(self) -> None:
        self._running = False
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        logger.info("WaitlistExpiryScheduler stopped")

    def _schedule_next(self) -> None:
        if not self._running:
            return
        self._timer = threading.Timer(WAITLIST_EXPIRY_INTERVAL, self._fire)
        self._timer.daemon = True
        self._timer.start()

    def _fire(self) -> None:
        logger.info("Firing waitlist expiry job")
        try:
            _expire_waitlist_offers_job()
        except Exception as exc:  # noqa: BLE001
            logger.error("Waitlist expiry job raised: %s", exc)
        self._schedule_next()


waitlist_expiry_scheduler = WaitlistExpiryScheduler()
