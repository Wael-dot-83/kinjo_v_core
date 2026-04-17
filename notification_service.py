"""
Notification helpers for messaging and daily reports.
"""
import logging
from datetime import date
from typing import Iterable, List, Optional

import models
from config import settings
from notification_tasks import send_email_notification, send_push_notification

logger = logging.getLogger(__name__)


# ==================== Daily Report Notifications ====================

def create_daily_report_notification(
    db,
    report: Optional[models.DailyReport],
    recipient: models.User,
    notification_type: models.NotificationType,
    custom_message: Optional[str] = None
) -> Optional[models.Notification]:
    """
    Create a notification for a daily report event.
    """
    if settings.TESTING:
        return None

    # Build payload based on notification type
    if report:
        child = report.child
        child_name = f"{child.first_name} {child.last_name}"
    else:
        child_name = "غير محدد"

    if notification_type == models.NotificationType.DAILY_REPORT_SENT:
        subject = f"التقرير اليومي لـ {child_name}"
        body = f"تم إرسال التقرير اليومي لطفلك {child_name} بتاريخ {report.date.strftime('%Y-%m-%d')}"
        title = "تقرير يومي جديد"
    elif notification_type == models.NotificationType.DAILY_REPORT_SUBMITTED:
        subject = f"تقرير يومي جديد بانتظار المراجعة"
        body = f"تم إرسال تقرير يومي للطفل {child_name} بانتظار موافقتك"
        title = "تقرير بانتظار المراجعة"
    elif notification_type == models.NotificationType.DAILY_REPORT_REJECTED:
        subject = f"تم رفض التقرير اليومي"
        reason = custom_message or "لم يتم تحديد السبب"
        body = f"تم رفض التقرير اليومي للطفل {child_name}. السبب: {reason}"
        title = "تقرير مرفوض"
    elif notification_type == models.NotificationType.DAILY_REPORT_MISSING:
        subject = "تنبيه: تقارير يومية ناقصة"
        body = custom_message or f"يوجد أطفال بدون تقارير يومية"
        title = "تقارير ناقصة"
    else:
        subject = "إشعار"
        body = custom_message or "لديك إشعار جديد"
        title = "إشعار"

    payload = {"subject": subject, "title": title, "body": body}

    # Determine channels
    channels = []
    if settings.NOTIFICATIONS_EMAIL_ENABLED:
        channels.append(models.NotificationChannel.EMAIL)
    if settings.NOTIFICATIONS_PUSH_ENABLED:
        channels.append(models.NotificationChannel.PUSH)
    # Always add IN_APP for dashboard visibility
    channels.append(models.NotificationChannel.IN_APP)

    if not channels:
        logger.warning("No notification channels enabled")
        return None

    notifications: List[models.Notification] = []

    for channel in channels:
        notification = models.Notification(
            user_id=recipient.id,
            daily_report_id=report.id if report else None,
            notification_type=notification_type,
            channel=channel,
            status=models.NotificationStatus.PENDING,
            payload=payload
        )
        notifications.append(notification)

    db.add_all(notifications)
    db.commit()

    # Queue async tasks for email/push
    for notification in notifications:
        if notification.channel == models.NotificationChannel.EMAIL:
            try:
                send_email_notification.delay(notification.id)
            except Exception as e:
                logger.warning(f"Failed to queue email notification: {e}")
        elif notification.channel == models.NotificationChannel.PUSH:
            try:
                send_push_notification.delay(notification.id)
            except Exception as e:
                logger.warning(f"Failed to queue push notification: {e}")

    return notifications[0] if notifications else None


def notify_parent_daily_report(db, report: models.DailyReport) -> bool:
    """
    Notify parent when daily report is sent to them.
    """
    child = report.child
    if not child or not child.parent_id:
        logger.warning(f"Cannot notify parent for report {report.id}: no parent linked")
        return False

    # Get parent user
    parent_profile = db.query(models.ParentProfile).filter(
        models.ParentProfile.id == child.parent_id
    ).first()

    if not parent_profile:
        logger.warning(f"Parent profile not found for child {child.id}")
        return False

    parent_user = db.query(models.User).filter(
        models.User.id == parent_profile.user_id
    ).first()

    if not parent_user:
        logger.warning(f"Parent user not found for profile {parent_profile.id}")
        return False

    create_daily_report_notification(
        db,
        report,
        parent_user,
        models.NotificationType.DAILY_REPORT_SENT
    )
    return True


def notify_manager_report_submitted(db, report: models.DailyReport, kindergarten_id: int) -> bool:
    """
    Notify manager when supervisor submits a report.
    """
    # Get manager for the kindergarten
    manager = db.query(models.User).filter(
        models.User.kindergarten_id == kindergarten_id,
        models.User.role == models.UserRole.MANAGER,
        models.User.status == models.UserStatus.ACTIVE
    ).first()

    if not manager:
        logger.warning(f"No active manager found for kindergarten {kindergarten_id}")
        return False

    create_daily_report_notification(
        db,
        report,
        manager,
        models.NotificationType.DAILY_REPORT_SUBMITTED
    )
    return True


def notify_supervisor_report_rejected(db, report: models.DailyReport, reason: Optional[str] = None) -> bool:
    """
    Notify supervisor when their report is rejected.
    """
    if not report.submitted_by:
        logger.warning(f"Cannot notify supervisor for report {report.id}: no submitter")
        return False

    supervisor = db.query(models.User).filter(
        models.User.id == report.submitted_by
    ).first()

    if not supervisor:
        logger.warning(f"Supervisor not found for report {report.id}")
        return False

    create_daily_report_notification(
        db,
        report,
        supervisor,
        models.NotificationType.DAILY_REPORT_REJECTED,
        custom_message=reason
    )
    return True


def notify_missing_daily_report_alert(
    db,
    user: models.User,
    missing_children: List[dict],
    report_date: date,
    context: str
) -> bool:
    """Notify a user about missing daily reports for the given date."""
    if settings.TESTING or not missing_children:
        return False

    child_preview = ", ".join(c.get("child_name", "") for c in missing_children[:3])
    subject = f"Missing daily reports ({context})"
    title = "Missing Daily Reports"
    body = (
        f"{len(missing_children)} present children still need daily reports for {report_date.isoformat()}. "
        f"{child_preview}"
    )
    payload = {
        "subject": subject,
        "title": title,
        "body": body,
        "missing_count": len(missing_children),
        "report_date": report_date.isoformat(),
        "context": context,
        "children": missing_children[:5]
    }

    channels = []
    if settings.NOTIFICATIONS_EMAIL_ENABLED:
        channels.append(models.NotificationChannel.EMAIL)
    if settings.NOTIFICATIONS_PUSH_ENABLED:
        channels.append(models.NotificationChannel.PUSH)
    channels.append(models.NotificationChannel.IN_APP)

    if not channels:
        logger.warning("No notification channels enabled for missing daily report alert")
        return False

    notifications: List[models.Notification] = []
    for channel in channels:
        notifications.append(models.Notification(
            user_id=user.id,
            notification_type=models.NotificationType.DAILY_REPORT_MISSING,
            channel=channel,
            status=models.NotificationStatus.PENDING,
            payload=payload
        ))

    db.add_all(notifications)
    db.commit()

    _queue_notification_tasks(notifications)
    return True


def _build_notification_payload(message: models.Message) -> dict:
    subject = message.subject or "New message"
    body = message.message_body[:240] if message.message_body else "You have a new message"
    return {"subject": subject, "title": subject, "body": body}


def _queue_notification_tasks(notifications: List[models.Notification]) -> None:
    for notification in notifications:
        if notification.channel == models.NotificationChannel.EMAIL:
            send_email_notification.delay(notification.id)
        elif notification.channel == models.NotificationChannel.PUSH:
            send_push_notification.delay(notification.id)


def create_message_notifications(
    db,
    message: models.Message,
    recipients: Iterable[models.User]
) -> bool:
    if settings.TESTING:
        return False

    channels = []
    if settings.NOTIFICATIONS_EMAIL_ENABLED:
        channels.append(models.NotificationChannel.EMAIL)
    if settings.NOTIFICATIONS_PUSH_ENABLED:
        channels.append(models.NotificationChannel.PUSH)

    if not channels:
        logger.warning("Notifications disabled for message %s", message.id)
        return False

    payload = _build_notification_payload(message)
    notifications: List[models.Notification] = []

    for user in recipients:
        for channel in channels:
            notifications.append(models.Notification(
                user_id=user.id,
                message_id=message.id,
                channel=channel,
                status=models.NotificationStatus.PENDING,
                payload=payload
            ))

    if not notifications:
        return False

    db.add_all(notifications)
    db.commit()

    _queue_notification_tasks(notifications)

    return True


__all__ = [
    "create_message_notifications",
    "create_daily_report_notification",
    "notify_parent_daily_report",
    "notify_manager_report_submitted",
    "notify_supervisor_report_rejected",
    "notify_manager_absence_request",
    "notify_absence_approved",
    "notify_absence_rejected",
    "notify_attendance_corrected",
    "notify_supervisor_absence_approved",
]


# ==================== Absence Request Notifications ====================

def _create_absence_notification(
    db,
    recipient: models.User,
    notification_type: models.NotificationType,
    absence_request_id: int,
    payload: dict,
) -> Optional[models.Notification]:
    """Low-level helper: create Notification records for all enabled channels."""
    if settings.TESTING:
        return None

    channels: List[models.NotificationChannel] = []
    if settings.NOTIFICATIONS_EMAIL_ENABLED:
        channels.append(models.NotificationChannel.EMAIL)
    if settings.NOTIFICATIONS_PUSH_ENABLED:
        channels.append(models.NotificationChannel.PUSH)
    channels.append(models.NotificationChannel.IN_APP)

    if not channels:
        logger.warning("No notification channels enabled")
        return None

    notifications: List[models.Notification] = []
    for channel in channels:
        notifications.append(models.Notification(
            user_id=recipient.id,
            absence_request_id=absence_request_id,
            notification_type=notification_type,
            channel=channel,
            status=models.NotificationStatus.PENDING,
            payload=payload,
        ))

    db.add_all(notifications)
    db.commit()

    _queue_notification_tasks(notifications)
    return notifications[0] if notifications else None


def notify_manager_absence_request(
    db,
    absence_request: models.AbsenceRequest,
    child_name: str,
    parent_name: str,
) -> bool:
    """Notify kindergarten manager that a parent submitted an absence request."""
    manager = db.query(models.User).filter(
        models.User.kindergarten_id == absence_request.kindergarten_id,
        models.User.role == models.UserRole.MANAGER,
        models.User.status == models.UserStatus.ACTIVE,
    ).first()

    if not manager:
        logger.warning(
            "No active manager found for kindergarten %s",
            absence_request.kindergarten_id,
        )
        return False

    start = absence_request.start_date.strftime("%Y-%m-%d")
    end = absence_request.end_date.strftime("%Y-%m-%d")

    payload = {
        "subject": "طلب غياب جديد",
        "title": "طلب غياب جديد",
        "body": (
            f"قدم ولي الأمر {parent_name} طلب غياب للطفل {child_name} "
            f"من {start} إلى {end}. السبب: {absence_request.reason}"
        ),
    }

    _create_absence_notification(
        db,
        manager,
        models.NotificationType.ABSENCE_REQUEST_SUBMITTED,
        absence_request.id,
        payload,
    )
    return True


def notify_absence_approved(
    db,
    absence_request: models.AbsenceRequest,
    child_name: str,
    parent_user: models.User,
) -> bool:
    """Notify parent that their absence request was approved."""
    start = absence_request.start_date.strftime("%Y-%m-%d")
    end = absence_request.end_date.strftime("%Y-%m-%d")
    note = absence_request.decision_note or ""
    note_line = f" ملاحظة: {note}" if note else ""

    payload = {
        "subject": "تمت الموافقة على طلب الغياب",
        "title": "طلب الغياب - موافقة",
        "body": (
            f"تمت الموافقة على طلب غياب {child_name} "
            f"من {start} إلى {end}.{note_line}"
        ),
    }

    _create_absence_notification(
        db,
        parent_user,
        models.NotificationType.ABSENCE_REQUEST_APPROVED,
        absence_request.id,
        payload,
    )
    return True


def notify_absence_rejected(
    db,
    absence_request: models.AbsenceRequest,
    child_name: str,
    parent_user: models.User,
) -> bool:
    """Notify parent that their absence request was rejected."""
    start = absence_request.start_date.strftime("%Y-%m-%d")
    end = absence_request.end_date.strftime("%Y-%m-%d")
    reason = absence_request.decision_note or "لم يتم تحديد السبب"

    payload = {
        "subject": "تم رفض طلب الغياب",
        "title": "طلب الغياب - مرفوض",
        "body": (
            f"تم رفض طلب غياب {child_name} "
            f"من {start} إلى {end}. السبب: {reason}"
        ),
    }

    _create_absence_notification(
        db,
        parent_user,
        models.NotificationType.ABSENCE_REQUEST_REJECTED,
        absence_request.id,
        payload,
    )
    return True


def notify_supervisor_absence_approved(
    db,
    absence_request: models.AbsenceRequest,
    child_name: str,
    records_created: int,
) -> bool:
    """Notify supervisors of the child's class that attendance was auto-marked ABSENT."""
    from missing_endpoints import get_supervisor_classes  # avoid circular

    # Find supervisors assigned to the child's class
    supervisors = db.query(models.User).filter(
        models.User.role == models.UserRole.SUPERVISOR,
        models.User.kindergarten_id == absence_request.kindergarten_id,
        models.User.status == models.UserStatus.ACTIVE,
    ).all()

    notified = 0
    start = absence_request.start_date.strftime("%Y-%m-%d")
    end = absence_request.end_date.strftime("%Y-%m-%d")

    for sup in supervisors:
        sup_classes = get_supervisor_classes(db, sup.id)
        if absence_request.class_id not in sup_classes:
            continue

        payload = {
            "subject": "تم اعتماد غياب طفل",
            "title": "غياب معتمد - حضور تلقائي",
            "body": (
                f"تم اعتماد غياب {child_name} من {start} إلى {end}. "
                f"تم تسجيل {records_created} سجل حضور تلقائياً كغياب."
            ),
        }

        _create_absence_notification(
            db,
            sup,
            models.NotificationType.ABSENCE_REQUEST_APPROVED,
            absence_request.id,
            payload,
        )
        notified += 1

    return notified > 0


def notify_attendance_corrected(
    db,
    attendance_log: models.AttendanceLog,
    child_name: str,
    parent_user: models.User,
    old_status: str,
    new_status: str,
) -> bool:
    """Notify parent when their child's attendance is corrected."""
    att_date = attendance_log.date.strftime("%Y-%m-%d")

    payload = {
        "subject": "تم تعديل سجل الحضور",
        "title": "تعديل حضور",
        "body": (
            f"تم تعديل حالة حضور {child_name} بتاريخ {att_date} "
            f"من {old_status} إلى {new_status}."
        ),
    }

    channels: List[models.NotificationChannel] = []
    if settings.NOTIFICATIONS_EMAIL_ENABLED:
        channels.append(models.NotificationChannel.EMAIL)
    if settings.NOTIFICATIONS_PUSH_ENABLED:
        channels.append(models.NotificationChannel.PUSH)
    channels.append(models.NotificationChannel.IN_APP)

    if not channels:
        return False

    if settings.TESTING:
        return True

    notifications: List[models.Notification] = []
    for channel in channels:
        notifications.append(models.Notification(
            user_id=parent_user.id,
            notification_type=models.NotificationType.ATTENDANCE_CORRECTED,
            channel=channel,
            status=models.NotificationStatus.PENDING,
            payload=payload,
        ))

    db.add_all(notifications)
    db.commit()

    _queue_notification_tasks(notifications)
    return True
