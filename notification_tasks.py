"""
Background tasks for sending notifications.
"""
import logging
from datetime import datetime, timezone, timedelta
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

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
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
def send_email_notification(notification_id: int) -> None:
    db = SessionLocal()
    try:
        notification = db.query(models.Notification).filter(models.Notification.id == notification_id).first()
        if not notification or notification.status != models.NotificationStatus.PENDING:
            return
        if not settings.NOTIFICATIONS_EMAIL_ENABLED:
            notification.status = models.NotificationStatus.FAILED
            notification.error_message = "Email notifications are disabled"
            db.commit()
            return

        user = db.query(models.User).filter(models.User.id == notification.user_id).first()
        if not user or not user.email:
            notification.status = models.NotificationStatus.FAILED
            notification.error_message = "User email not available"
            db.commit()
            return

        meta = notification.payload or {}
        subject = meta.get("subject", "New message")
        body = meta.get("body", "You have a new message")

        _send_email(user.email, subject, body)

        notification.status = models.NotificationStatus.SENT
        notification.sent_at = datetime.now(_JORDAN_TZ)
        db.commit()
    except (smtplib.SMTPException, httpx.HTTPError, OSError, RuntimeError, TypeError, ValueError, AttributeError) as exc:
        notification = db.query(models.Notification).filter(models.Notification.id == notification_id).first()
        if notification:
            notification.status = models.NotificationStatus.FAILED
            notification.error_message = str(exc)
            db.commit()
    finally:
        db.close()


@celery_app.task
def send_push_notification(notification_id: int) -> None:
    db = SessionLocal()
    try:
        notification = db.query(models.Notification).filter(models.Notification.id == notification_id).first()
        if not notification or notification.status != models.NotificationStatus.PENDING:
            return
        if not settings.NOTIFICATIONS_PUSH_ENABLED:
            notification.status = models.NotificationStatus.FAILED
            notification.error_message = "Push notifications are disabled"
            db.commit()
            return

        meta = notification.payload or {}
        title = meta.get("title", "New message")
        body = meta.get("body", "You have a new message")

        tokens = db.query(models.UserDeviceToken).filter(
            models.UserDeviceToken.user_id == notification.user_id,
            models.UserDeviceToken.is_active.is_(True)
        ).all()

        if not tokens:
            notification.status = models.NotificationStatus.FAILED
            notification.error_message = "No active device tokens"
            db.commit()
            return

        for token in tokens:
            _send_push(token.token, title, body)
            token.last_used_at = datetime.now(_JORDAN_TZ)

        notification.status = models.NotificationStatus.SENT
        notification.sent_at = datetime.now(_JORDAN_TZ)
        db.commit()
    except (httpx.HTTPError, RuntimeError, OSError, TypeError, ValueError, AttributeError) as exc:
        notification = db.query(models.Notification).filter(models.Notification.id == notification_id).first()
        if notification:
            notification.status = models.NotificationStatus.FAILED
            notification.error_message = str(exc)
            db.commit()
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
