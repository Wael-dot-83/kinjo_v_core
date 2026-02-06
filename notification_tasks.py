"""
Background tasks for sending notifications.
"""
from datetime import datetime, timezone
import smtplib
from email.mime.text import MIMEText

import httpx

import models
from celery_app import celery_app
from config import settings
from database import SessionLocal


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
        notification.sent_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:
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
            token.last_used_at = datetime.now(timezone.utc)

        notification.status = models.NotificationStatus.SENT
        notification.sent_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:
        notification = db.query(models.Notification).filter(models.Notification.id == notification_id).first()
        if notification:
            notification.status = models.NotificationStatus.FAILED
            notification.error_message = str(exc)
            db.commit()
    finally:
        db.close()
