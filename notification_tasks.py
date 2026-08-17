"""
Background tasks for sending notifications.
"""
import logging
from datetime import datetime, timezone, timedelta
import uuid

_JORDAN_TZ = timezone(timedelta(hours=3))
from utils.time_utils import today_amman as _today
import smtplib
from email.mime.text import MIMEText

import httpx

import models
from celery_app import celery_app
from config import settings
from database import SessionLocal
from sqlalchemy import or_

logger = logging.getLogger(__name__)

MAX_NOTIFICATION_DELIVERY_ATTEMPTS = 5
NOTIFICATION_RETRY_BATCH_SIZE = 100
NOTIFICATION_RETRY_DELAY_SECONDS = 60
NOTIFICATION_DISPATCH_LEASE_SECONDS = 300
_DELIVERABLE_CHANNELS = (
    models.NotificationChannel.EMAIL,
    models.NotificationChannel.PUSH,
)
_PUBLISH_RETRY_POLICY = {
    "max_retries": 3,
    "interval_start": 0,
    "interval_step": 0.5,
    "interval_max": 1,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _claim_notification_for_delivery(
    db,
    notification_id: int,
    *,
    claim_token: str | None = None,
    now: datetime | None = None,
) -> models.Notification | None:
    """Atomically claim one PENDING row, or validate a sweeper-issued claim."""
    now = now or _utcnow()
    lease_cutoff = now - timedelta(seconds=NOTIFICATION_DISPATCH_LEASE_SECONDS)

    if claim_token:
        return db.query(models.Notification).filter(
            models.Notification.id == notification_id,
            models.Notification.status == models.NotificationStatus.PENDING,
            models.Notification.dispatch_claim_token == claim_token,
            models.Notification.dispatch_claimed_at > lease_cutoff,
        ).first()

    claim_token = uuid.uuid4().hex
    updated = db.query(models.Notification).filter(
        models.Notification.id == notification_id,
        models.Notification.status == models.NotificationStatus.PENDING,
        models.Notification.channel.in_(_DELIVERABLE_CHANNELS),
        models.Notification.delivery_attempts < MAX_NOTIFICATION_DELIVERY_ATTEMPTS,
        or_(
            models.Notification.next_retry_at.is_(None),
            models.Notification.next_retry_at <= now,
        ),
        or_(
            models.Notification.dispatch_claimed_at.is_(None),
            models.Notification.dispatch_claimed_at <= lease_cutoff,
        ),
    ).update(
        {
            models.Notification.delivery_attempts: models.Notification.delivery_attempts + 1,
            models.Notification.last_attempt_at: now,
            models.Notification.next_retry_at: now + timedelta(seconds=NOTIFICATION_RETRY_DELAY_SECONDS),
            models.Notification.dispatch_claimed_at: now,
            models.Notification.dispatch_claim_token: claim_token,
            models.Notification.error_message: None,
        },
        synchronize_session=False,
    )
    db.commit()
    if updated != 1:
        return None
    return db.query(models.Notification).filter(
        models.Notification.id == notification_id,
        models.Notification.status == models.NotificationStatus.PENDING,
        models.Notification.dispatch_claim_token == claim_token,
    ).first()


def _finish_delivery(
    db,
    notification: models.Notification,
    *,
    status: models.NotificationStatus,
    error_message: str | None = None,
) -> None:
    values = {
        models.Notification.status: status,
        models.Notification.error_message: error_message[:1000] if error_message else None,
        models.Notification.dispatch_claimed_at: None,
        models.Notification.dispatch_claim_token: None,
        models.Notification.next_retry_at: None,
    }
    if status == models.NotificationStatus.SENT:
        values[models.Notification.sent_at] = datetime.now(_JORDAN_TZ)
    db.query(models.Notification).filter(
        models.Notification.id == notification.id,
        models.Notification.status == models.NotificationStatus.PENDING,
        models.Notification.dispatch_claim_token == notification.dispatch_claim_token,
    ).update(values, synchronize_session=False)
    db.commit()


def _release_publish_claim(db, notification: models.Notification, exc: Exception) -> None:
    """Release a broker-failed claim and schedule its bounded next attempt."""
    exhausted = notification.delivery_attempts >= MAX_NOTIFICATION_DELIVERY_ATTEMPTS
    db.query(models.Notification).filter(
        models.Notification.id == notification.id,
        models.Notification.status == models.NotificationStatus.PENDING,
        models.Notification.dispatch_claim_token == notification.dispatch_claim_token,
    ).update(
        {
            models.Notification.status: (
                models.NotificationStatus.FAILED
                if exhausted
                else models.NotificationStatus.PENDING
            ),
            models.Notification.error_message: (
                f"Broker publish failed ({type(exc).__name__}); "
                + ("retry budget exhausted" if exhausted else "pending retry")
            ),
            models.Notification.dispatch_claimed_at: None,
            models.Notification.dispatch_claim_token: None,
            models.Notification.next_retry_at: None if exhausted else notification.next_retry_at,
        },
        synchronize_session=False,
    )
    db.commit()


def _publish_claimed_notification(notification: models.Notification) -> None:
    task = (
        send_email_notification
        if notification.channel == models.NotificationChannel.EMAIL
        else send_push_notification
    )
    task.apply_async(
        args=[notification.id, notification.dispatch_claim_token],
        retry=True,
        retry_policy=_PUBLISH_RETRY_POLICY,
    )


def redispatch_stale_pending_notifications_now(
    *,
    db=None,
    batch_size: int = NOTIFICATION_RETRY_BATCH_SIZE,
    stale_after_seconds: int = NOTIFICATION_RETRY_DELAY_SECONDS,
) -> int:
    """Claim and republish one bounded batch of stale external notifications.

    Conditional UPDATE claims make concurrent beat instances safe. A claim is
    retained after a successful broker publish and must match inside the worker;
    a crashed/lost task becomes eligible again only after the lease expires.
    """
    owns_session = db is None
    db = db or SessionLocal()
    now = _utcnow()
    lease_cutoff = now - timedelta(seconds=NOTIFICATION_DISPATCH_LEASE_SECONDS)
    stale_before = now - timedelta(seconds=max(0, stale_after_seconds))
    limit = min(max(int(batch_size), 1), NOTIFICATION_RETRY_BATCH_SIZE)
    published = 0
    try:
        # Exhausted lost-message leases must terminate instead of remaining
        # invisible PENDING rows forever.
        db.query(models.Notification).filter(
            models.Notification.status == models.NotificationStatus.PENDING,
            models.Notification.channel.in_(_DELIVERABLE_CHANNELS),
            models.Notification.delivery_attempts >= MAX_NOTIFICATION_DELIVERY_ATTEMPTS,
            or_(
                models.Notification.dispatch_claimed_at.is_(None),
                models.Notification.dispatch_claimed_at <= lease_cutoff,
            ),
        ).update(
            {
                models.Notification.status: models.NotificationStatus.FAILED,
                models.Notification.error_message: "Notification delivery retry budget exhausted",
                models.Notification.dispatch_claimed_at: None,
                models.Notification.dispatch_claim_token: None,
                models.Notification.next_retry_at: None,
            },
            synchronize_session=False,
        )
        db.commit()

        candidate_ids = [
            row[0]
            for row in db.query(models.Notification.id).filter(
                models.Notification.status == models.NotificationStatus.PENDING,
                models.Notification.channel.in_(_DELIVERABLE_CHANNELS),
                models.Notification.delivery_attempts < MAX_NOTIFICATION_DELIVERY_ATTEMPTS,
                models.Notification.created_at <= stale_before,
                or_(
                    models.Notification.next_retry_at.is_(None),
                    models.Notification.next_retry_at <= now,
                ),
                or_(
                    models.Notification.dispatch_claimed_at.is_(None),
                    models.Notification.dispatch_claimed_at <= lease_cutoff,
                ),
            ).order_by(models.Notification.created_at, models.Notification.id).limit(limit).all()
        ]

        for notification_id in candidate_ids:
            notification = _claim_notification_for_delivery(
                db,
                notification_id,
                now=now,
            )
            if notification is None:
                continue
            try:
                _publish_claimed_notification(notification)
            except Exception as exc:
                _release_publish_claim(db, notification, exc)
                logger.warning(
                    "Notification broker publish failed id=%s attempt=%s error_type=%s",
                    notification.id,
                    notification.delivery_attempts,
                    type(exc).__name__,
                )
            else:
                published += 1
        return published
    finally:
        if owns_session:
            db.close()


@celery_app.task
def redispatch_stale_pending_notifications() -> int:
    return redispatch_stale_pending_notifications_now()


def _push_to_ws(notification: models.Notification) -> None:
    """Fire-and-forget: publish the in-app notification to the user's WS channel."""
    try:
        from realtime_service import publish_notification
        publish_notification(
            notification.user_id,
            {
                "type": "notification",
                "notification_id": notification.id,
                "notification_type": notification.notification_type.value,
                "payload": notification.payload,
            },
        )
    except Exception:
        logger.warning("Failed to push WS notification for user %d", notification.user_id)


def get_supervisor_classes(db: SessionLocal, supervisor_id: int) -> list[int]:
    """Get class IDs assigned to supervisor for current date"""
    from datetime import date
    today = _today()
    assignments = db.query(models.SupervisorAssignment).filter(
        models.SupervisorAssignment.supervisor_id == supervisor_id,
        models.SupervisorAssignment.start_date <= today,
        or_(models.SupervisorAssignment.end_date.is_(None), models.SupervisorAssignment.end_date >= today)
    ).all()
    return [a.class_id for a in assignments]


def _send_email(to_email: str, subject: str, body: str) -> None:
    if not settings.SMTP_HOST or not settings.SMTP_FROM:
        raise RuntimeError("SMTP configuration is missing")

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to_email

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as server:
        server.starttls()
        if settings.SMTP_USERNAME:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.send_message(msg)


def _send_push(token: str, title: str, body: str) -> None:
    if not settings.FCM_SERVER_KEY:
        raise RuntimeError("FCM_SERVER_KEY is not configured")

    payload = {
        "to": token,
        "notification": {"title": title, "body": body},
        "data": {"type": "message"}
    }

    headers = {
        "Authorization": f"key={settings.FCM_SERVER_KEY}",
        "Content-Type": "application/json"
    }

    response = httpx.post("https://fcm.googleapis.com/fcm/send", json=payload, headers=headers, timeout=10.0)
    response.raise_for_status()


@celery_app.task
def send_email_notification(
    notification_id: int,
    dispatch_claim_token: str | None = None,
) -> None:
    db = SessionLocal()
    try:
        notification = _claim_notification_for_delivery(
            db,
            notification_id,
            claim_token=dispatch_claim_token,
        )
        if not notification:
            return
        if not settings.NOTIFICATIONS_EMAIL_ENABLED:
            _finish_delivery(
                db,
                notification,
                status=models.NotificationStatus.FAILED,
                error_message="Email notifications are disabled",
            )
            return

        user = db.query(models.User).filter(models.User.id == notification.user_id).first()
        if not user or not user.email:
            _finish_delivery(
                db,
                notification,
                status=models.NotificationStatus.FAILED,
                error_message="User email not available",
            )
            return

        meta = notification.payload or {}
        subject = meta.get("subject", "New message")
        body = meta.get("body", "You have a new message")

        _send_email(user.email, subject, body)

        _finish_delivery(db, notification, status=models.NotificationStatus.SENT)
    except (smtplib.SMTPException, httpx.HTTPError, OSError, RuntimeError, TypeError, ValueError, AttributeError) as exc:
        if "notification" in locals() and notification:
            _finish_delivery(
                db,
                notification,
                status=models.NotificationStatus.FAILED,
                error_message=str(exc),
            )
    finally:
        db.close()


@celery_app.task
def send_push_notification(
    notification_id: int,
    dispatch_claim_token: str | None = None,
) -> None:
    db = SessionLocal()
    try:
        notification = _claim_notification_for_delivery(
            db,
            notification_id,
            claim_token=dispatch_claim_token,
        )
        if not notification:
            return
        if not settings.NOTIFICATIONS_PUSH_ENABLED:
            _finish_delivery(
                db,
                notification,
                status=models.NotificationStatus.FAILED,
                error_message="Push notifications are disabled",
            )
            return

        meta = notification.payload or {}
        title = meta.get("title", "New message")
        body = meta.get("body", "You have a new message")

        tokens = db.query(models.UserDeviceToken).filter(
            models.UserDeviceToken.user_id == notification.user_id,
            models.UserDeviceToken.is_active.is_(True)
        ).all()

        if not tokens:
            _finish_delivery(
                db,
                notification,
                status=models.NotificationStatus.FAILED,
                error_message="No active device tokens",
            )
            return

        for token in tokens:
            _send_push(token.token, title, body)
            token.last_used_at = datetime.now(_JORDAN_TZ)

        _finish_delivery(db, notification, status=models.NotificationStatus.SENT)
    except (httpx.HTTPError, RuntimeError, OSError, TypeError, ValueError, AttributeError) as exc:
        if "notification" in locals() and notification:
            _finish_delivery(
                db,
                notification,
                status=models.NotificationStatus.FAILED,
                error_message=str(exc),
            )
    finally:
        db.close()

@celery_app.task
def check_daily_report_compliance() -> None:
    """Check daily report compliance at 4:00 PM and notify supervisors of missing reports.
    Also escalates to manager if supervisor has not submitted all reports."""
    from datetime import date

    db = SessionLocal()
    try:
        today = _today()

        # Get all active supervisors
        supervisors = db.query(models.User).filter(
            models.User.role == models.UserRole.SUPERVISOR,
            models.User.status == models.UserStatus.ACTIVE,
        ).all()

        for supervisor in supervisors:
            class_ids = get_supervisor_classes(db, supervisor.id)
            if not class_ids:
                continue

            # Present children in supervisor's classes
            present_children_q = db.query(models.AttendanceLog.child_id).filter(
                models.AttendanceLog.date == today,
                models.AttendanceLog.class_id.in_(class_ids),
                models.AttendanceLog.status == models.AttendanceStatus.PRESENT,
            )
            present_ids = [r[0] for r in present_children_q.all()]
            if not present_ids:
                continue

            # Children with submitted/approved reports
            reported_ids = [r[0] for r in db.query(models.DailyReport.child_id).filter(
                models.DailyReport.date == today,
                models.DailyReport.child_id.in_(present_ids),
                models.DailyReport.status.in_([
                    models.DailyReportStatus.SUBMITTED,
                    models.DailyReportStatus.APPROVED,
                    models.DailyReportStatus.SENT_TO_PARENT,
                ]),
            ).all()]

            missing_ids = [cid for cid in present_ids if cid not in reported_ids]
            if not missing_ids:
                continue

            missing_children = db.query(models.Child).filter(
                models.Child.id.in_(missing_ids)
            ).all()
            missing_names = [f"{c.first_name} {c.last_name}" for c in missing_children]

            # Create notification with correct model fields
            notification = models.Notification(
                user_id=supervisor.id,
                notification_type=models.NotificationType.DAILY_REPORT_MISSING,
                channel=models.NotificationChannel.IN_APP,
                status=models.NotificationStatus.PENDING,
                payload={
                    "subject": "تقارير يومية مفقودة",
                    "title": "تنبيه الموعد النهائي - تقارير مفقودة",
                    "body": (
                        f"لديك {len(missing_ids)} أطفال حاضرين بدون تقارير يومية: "
                        f"{', '.join(missing_names)}"
                    ),
                    "missing_count": len(missing_ids),
                    "total_present": len(present_ids),
                    "reports_completed": len(reported_ids),
                },
            )
            db.add(notification)
            db.commit()
            db.refresh(notification)
            _push_to_ws(notification)

            # Queue delivery tasks
            if settings.NOTIFICATIONS_EMAIL_ENABLED:
                send_email_notification.delay(notification.id)
            if settings.NOTIFICATIONS_PUSH_ENABLED:
                send_push_notification.delay(notification.id)

            # Escalate to manager: flag the supervisor's delay
            if supervisor.kindergarten_id:
                manager = db.query(models.User).filter(
                    models.User.kindergarten_id == supervisor.kindergarten_id,
                    models.User.role == models.UserRole.MANAGER,
                    models.User.status == models.UserStatus.ACTIVE,
                ).first()
                if manager:
                    mgr_notification = models.Notification(
                        user_id=manager.id,
                        notification_type=models.NotificationType.DAILY_REPORT_MISSING,
                        channel=models.NotificationChannel.IN_APP,
                        status=models.NotificationStatus.PENDING,
                        payload={
                            "subject": "تأخر مشرف في تقديم التقارير",
                            "title": "إشعار تأخر - تقارير يومية",
                            "body": (
                                f"المشرف {supervisor.username} لديه {len(missing_ids)} "
                                f"تقارير مفقودة عند الموعد النهائي (4:00 مساءً)."
                            ),
                            "supervisor_id": supervisor.id,
                            "supervisor_name": supervisor.username,
                            "missing_count": len(missing_ids),
                        },
                    )
                    db.add(mgr_notification)
                    db.commit()
                    db.refresh(mgr_notification)
                    _push_to_ws(mgr_notification)

    except (RuntimeError, TypeError, ValueError, AttributeError, OSError) as exc:
        logger.error("Error in daily report compliance check: %s", exc)
    finally:
        db.close()


@celery_app.task
def send_daily_report_reminder() -> None:
    """Send 3:45 PM reminder to supervisors who have present children without reports.
    Must be scheduled 15 minutes before the 4:00 PM deadline."""
    from datetime import date

    db = SessionLocal()
    try:
        today = _today()

        supervisors = db.query(models.User).filter(
            models.User.role == models.UserRole.SUPERVISOR,
            models.User.status == models.UserStatus.ACTIVE,
        ).all()

        for supervisor in supervisors:
            class_ids = get_supervisor_classes(db, supervisor.id)
            if not class_ids:
                continue

            present_ids = [r[0] for r in db.query(models.AttendanceLog.child_id).filter(
                models.AttendanceLog.date == today,
                models.AttendanceLog.class_id.in_(class_ids),
                models.AttendanceLog.status == models.AttendanceStatus.PRESENT,
            ).all()]
            if not present_ids:
                continue

            # Any report status counts (even drafts that haven't been submitted)
            reported_ids = [r[0] for r in db.query(models.DailyReport.child_id).filter(
                models.DailyReport.date == today,
                models.DailyReport.child_id.in_(present_ids),
            ).all()]

            missing_count = len([cid for cid in present_ids if cid not in reported_ids])
            if missing_count == 0:
                continue

            notification = models.Notification(
                user_id=supervisor.id,
                notification_type=models.NotificationType.DAILY_REPORT_MISSING,
                channel=models.NotificationChannel.IN_APP,
                status=models.NotificationStatus.PENDING,
                payload={
                    "subject": "تذكير - الموعد النهائي خلال 15 دقيقة",
                    "title": "تذكير بالموعد النهائي للتقارير",
                    "body": (
                        f"تبقى 15 دقيقة على الموعد النهائي (4:00 مساءً). "
                        f"لديك {missing_count} تقارير لم تُكتب بعد."
                    ),
                    "reminder_type": "pre_deadline",
                    "minutes_remaining": 15,
                    "missing_count": missing_count,
                },
            )
            db.add(notification)
            db.commit()
            db.refresh(notification)
            _push_to_ws(notification)

            if settings.NOTIFICATIONS_PUSH_ENABLED:
                send_push_notification.delay(notification.id)

    except (RuntimeError, TypeError, ValueError, AttributeError, OSError) as exc:
        logger.error("Error in daily report reminder: %s", exc)
    finally:
        db.close()
